from DAG2 import initialiseDAG, expandDAG, extractPatterns
from customHash import stateAppend
import matplotlib.pyplot as plt
import numpy as np
from collections import defaultdict
import json
import pickle
import time
import jieba

def patternFreqs(patterns):
    freqs = []
    count1=0
    for k,d in patterns.items():
        for m,d2 in d.items():
            count1+=1
            freqs.append(d2["f"])
    print(f"there are {len(freqs)} patterns")
    return freqs



def freqFilter(patterns,boolFunction):
    patterns2=defaultdict(lambda: defaultdict(lambda: {"f":0}))
    for k,d in patterns.items():
        for m,d2 in d.items():
            if(boolFunction(d2["f"])):
                patterns2[k][m]=d2
    return patterns2




if __name__=="__main__":
    #with open("data/pinru/subs","r") as f:
    #    corpus=f.readlines()
    #with open("pinru.pkl","rb") as f:
    #    hashes=pickle.load(f)
    #with open("data/eng_newscrawl_2018_10K/eng_newscrawl_2018_10K-sentences.txt","r") as f:
    #   corpus=[line.split('\t')[1] for line in f.readlines()]
    #with open("hashish.pkl","rb") as f:
    #    hashes=pickle.load(f)
    with open("data/quran","r") as f:
        corpus=f.readlines()
    with open("quran.pkl","rb") as f:
        hashes=pickle.load(f)
    #hashes=defaultdict(lambda: defaultdict(lambda: {"f":0,"raw":""}))
    #hashes={}
    words=set()
    for line in corpus:
        #for word in jieba.cut(line):#.split(" "):
        for word in line.split(" "):
            words.add(word)
    print(len(words))

    count=0
    patterns=defaultdict(lambda: defaultdict(lambda: {"f":0}))
    for word in words:
        if not hashes.get(stateAppend(0,word),0):
            count+=1
            #print(word , end="|")
            parts=[word]
            while len(word)>3:
                parts.append(word[:3])
                word=word[3:]
            parts.append(word)
            for part in parts:
                h=stateAppend(0,part)
                patterns[h][h]["f"]+=1
    
    print(f"{count}/{len(words)} are not found")
                
    print(f"patterns before dedup: {sum(len(d) for d in patterns.values())}")
    for h,d in list(patterns.items()):
        for sh,d2 in list(d.items()):
            if h in hashes:
                if sh in hashes[h]:
                    del patterns[h][sh]
    print(f"patterns after dedup: {sum(len(d) for d in patterns.values())}")

    hashCount=0
    for h,d in list(patterns.items()):
        for sh,d2 in list(d.items()):
            if h not in hashes:
                hashes[h]={}
            if sh not in hashes[h]:
                hashes[h][sh]=d2
                hashCount+=1
    print(f"hashes has {hashCount} new entries")
    #filename="pinru"
    #filename="hashish"
    filename="quran"
    with open(f"{filename}.pkl", "wb") as f:
        pickle.dump(hashes, f)
    with open(f"{filename}.json", "w") as f:
        json.dump(hashes, f, indent=2)

























else:

    hashCount=0
    itterations=8
    l=0
    for i in range(itterations-1,-1,-1):
        start=time.perf_counter()
        print(f"======== round {itterations - i}/{itterations} ========")
        #patterns=defaultdict(lambda: defaultdict(lambda: {"f":0,"raw":""}))
        patterns=defaultdict(lambda: defaultdict(lambda: {"f":0}))
        count=0
        total=len(corpus)
        for sentence in corpus:
            print(" "*120,end="\r")
            print(" "*50+sentence[:min(len(sentence)-1,80)]+" "+str(count),end="\r")
            
            count+=1
            if not count%2000:
                percentage=100*count//total
                print(f"{count} out of {total} ({percentage}%), time: {time.perf_counter()-start}"+" "*53)
            DAG=initialiseDAG(sentence)
            DAG=expandDAG(DAG,hashes,expand=True,expRound=itterations-i)
            #for h,d in extractPatterns(DAG,r=itterations-1,raw=True).items():
            for h,d in DAG.items():
                for location,d2 in d.items():
                    if d2["masked"]:
                        continue
                    sh=d2["sh"]
                    #patterns[h][sh]["raw"]=d2["raw"]
                    if h==sh:
                        patterns[h][sh]["f"]+=1
                    else:
                        patterns[h][sh]["f"]+=0.1
        
        print(" "*100,end="\r")
        end=time.perf_counter()
        print(f"took {end - start} seconds")
        print("filtering and updating")
        #patterns={k:d for k,d in patterns.items() if k not in hashes}

        print(f"patterns before dedup: {sum(len(d) for d in patterns.values())}")
        for h,d in list(patterns.items()):
            for sh,d2 in list(d.items()):
                if h in hashes:
                    if sh in hashes[h]:
                        del patterns[h][sh]
        print(f"patterns after dedup: {sum(len(d) for d in patterns.values())}")

        freqs=patternFreqs(patterns)
        threshold = np.percentile(freqs, 80)
        patterns=freqFilter(patterns,lambda f: f>(max(3,threshold)))
        print(f"patterns after cull: {sum(len(d) for d in patterns.values())}")
        #for h,d in list(patterns.items())[5:]:
        #    for sh,d2 in list(d.items())[:2]:
        #        print(d2["raw"])
        for h,d in list(patterns.items()):
            for sh,d2 in list(d.items()):
                if h not in hashes:
                    hashes[h]={}
                if sh not in hashes[h]:
                    hashes[h][sh]=d2
                    hashes[h][sh]["round"]=itterations-i
                    hashCount+=1
        print(f"hashes has {hashCount} entries")
    
        #filename="pinru"
        filename="hashish"
        #filename="quran"
        with open(f"{filename}.pkl", "wb") as f:
            pickle.dump(hashes, f)
        with open(f"{filename}.json", "w") as f:
            json.dump(hashes, f, indent=2)

