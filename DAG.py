from customHash import stateAppend, stateCombine, stateAppendRaw
from globalVariables import MASKWIDTH
from masks import generateMasks, int2binlist, mask2indices
import json
import pickle #save patterns
from collections import defaultdict #make writing to dicts easier

TESTSENTENCE="yeah man this is the sentence I wish to test lol thanks"

#decompose sentence by masks
def maskDecompose(sentence):
    """
    decompose a sentence into a dictionary in the form mask: characters
    window size defined in globalVariables.py
    """
    masks=generateMasks()
    width=0
    decomposed={}
    for mask in masks:
        if mask.bit_length()>width:
            width=mask.bit_length()
            substrings=[sentence[j:j+width] for j in range(len(sentence)-width+1)]
        indices=mask2indices(mask)
        decomposed[mask]=([[substring[index] for index in indices] for substring in substrings])
    return(decomposed)


#combine patterns together by function and mask
def combine(f, items, itemformat):
    """
    combine things together based on an append-like function and masks
    input f, function must take in a total string and a member of the items
    list eg f:output,item->output.append(item), or f:output,item->output+item
    input patterns [[mask, [list]]]
    input itemformat, the default item eg 0 for int, [] for list. must be as 
    a function returning an empty one or shared memory bugs
    amount of ones in the mask must be the same as number of items
    """
    output=itemformat()
    #print("combination")
    iters=[[iter(int2binlist(mask)),iter(hashes)] for [mask, hashes] in items]
    #print(f"itters: {[[int2binlist(mask),hashes] for [mask, hashes] in items]}")

    while iters:
        level=0
        while level < len(iters):
            try:
                tamade=next(iters[level][0])#mask digit
                #print(f"tamade:{tamade}")
                if tamade:
                    #print(f"tamadeyeboi")
                    #output.append(next(iters[level][1]))
                    n=next(iters[level][1])
                    #print(f"next:{n}")
                    #print(f"prevout:{output}")
                    #output=stateAppend(output,next(iters[level][1]))#hash
                    output=f(output,n)
                    #print(f"fout:{output}")
                    #print(f"notbroke")
                    level=0
                    break
                level+=1
            except:
                #print("wrecked")
                del iters[level]
    return(output)

#function to recursively generate chains (generator object for ram)
def generateChains(DAG, start, n, path=None):
    """
    return a gnererator of all chains of patterns of length
    n from a pattern, Start: [hash, index]
    note: first member is not part of the chain
    note: only returns chains who have a member from round at least
    """
    if path==None:#get rid of ghost memory
        path=[]

    chain=path+[start]
    if n==0:
        yield chain
        return 

    #print(chain)
    for link in DAG[start[0]]["data"][start[1]]["links"]:
        yield from generateChains(DAG, link, n-1, chain)


def generateDAG(sentence,hashes):
    """
    a variation on maskDecompose that also builds up patterns
    by building up a directed acryllic graph of different ways
    to build up the sentence.
    """
    # dag from source hash to end where sequentially hashing
    # across any path will make the hash of the sentence.
    # For a given index, it includes the mask, the subsequent
    # hash and it's index, and the round it was explored (to
    # avoid redundant checks. There is also a lookup of hashes
    # to raw letters and hashes as well as their lengths (for 
    # hashing)

    #print(hashes)
    DAG=defaultdict(lambda: {"data":defaultdict(lambda: {"links":[],"mask":0,"round":0, "length":0,"raw":[]})})
    sentenceHashes=[[[char,[stateAppend(0,char),1]]] for char in sentence+" "] #added garbage space so all characters are added to DAG
    #print(f"sentenceHashes: {sentenceHashes}")
    #print(f"Length of first item: {len(sentenceHashes[0])}")
    #print(f"First item: {sentenceHashes[0]}")
    #print(f"Last element of first item: {sentenceHashes[0][-1]}")
    #set up default graph (all characters of the sentence)
    DAG[0]={"data":{-1:{"links":[[sentenceHashes[0][0][1][0],0]],"round":0,"length":0,"raw":[["",[0,0]]]},len(sentence):{"links":[], "round":0, "length":0,"raw":[["",[0,0]]]}}} #start and end
    i=0
    for i in range(len(sentenceHashes)-1):
        DAG[sentenceHashes[i][0][1][0]]["data"][i]={"links":[[sentenceHashes[i+1][0][1][0],i+1]],"mask":1,"round":1,"length":1,"raw":sentenceHashes[i]}


    seperatedMasks=[[] for i in range(MASKWIDTH+1)]#2d list of masks seperated by their size
    for mask in generateMasks():
        seperatedMasks[mask.bit_length()].append(mask)
    
    loop=True
    itteration=2 #counter for itterations, starts at round 2
    while loop:
    #for i in range(3):
        loop=False

        width=0
        decomposed={}
        for width in range(2,len(seperatedMasks)):
            indicesOfWidth=[mask2indices(mask) for mask in seperatedMasks[width]]
            #print(f"indices: {indicesOfWidth}")
            #print(f"seperatedMasks: {seperatedMasks}")
            DAGcandidates=defaultdict(lambda: {"data":defaultdict(lambda: {"raw":[],"links":[],"mask":0,"round":0, "length":0})})
            sources=[]
            for key, data in list(DAG.items()):
                for pos in list(data["data"].keys()):
                    chains=generateChains(DAG,[key,pos],width) #every chain of length width !after! the given one
                    for chain in chains:
                        #print(f"chain: {chain}")
                        if chain[-1][1]==len(sentence):#chains must be like not include the sink node 
                            continue
                        prev=chain[0]
                        chain=chain[1:]
                        #make sure there are new nodes in the chain
                        for node in chain:
                            if DAG[node[0]]["data"][node[1]]["round"]>=itteration-1:
                                break
                        else:
                            continue
                        for mask in seperatedMasks[width]:
                            indices=mask2indices(mask)
                            rawlist=[]
                            explored=True
                            #find if chain contains any new nodes 
                            previndex=-5
                            for index in range(len(chain)):
                                if index in indices:
                                    m=DAG[chain[index][0]]["data"][chain[index][1]]["mask"]
                                    r=DAG[chain[index][0]]["data"][chain[index][1]]["raw"]
                                    #rint(f"nodeRaw:{r}")
                                    #hl=r[1]
                                    #text=r[0]

                                    if index > previndex+1:
                                        rawlist.append([[m,r]])
                                    else:
                                        rawlist[-1].append([m,r])
                                    if DAG[chain[index][0]]["data"][chain[index][1]]["round"]>=itteration-1:
                                        explored=False
                                    previndex=index
                            if explored:
                                continue

                            maskedNodes=[]
                            references=[]
                            chainHash,length=stateCombine([[chain[index][0],DAG[chain[index][0]]["data"][chain[index][1]]["length"]] for index in indices])
                            for index in range(len(chain)):
                                if index not in indices:
                                    #seperate this chain from the others by giving a deterministically randomised location
                                    maskedNodes.append([chain[index][0],chainHash+index])
                                    references.append(DAG[chain[index][0]]["data"][chain[index][1]])
                            #print("I be road running")
                            #print(maskedNodes)
                            #print(references)
                            #if already explored (ie prev from a different node)
                            if chainHash in DAGcandidates:
                                if chain[0][1] in DAGcandidates[chainHash]["data"]:
                                    sources.append( (prev,chainHash,chain[0][1]) )
                                    break

                            #join the raws of all these nodes
                            rawfunction=lambda raws: combine(
                                    lambda x,y: [x[0]+y[0], stateCombine([x[1],y[1]])],
                                    raws,

                                    lambda: ["",[0,0]]
                                )
                            raw=[rawfunction(raws) for raws in rawlist]
                            #print(f"rawlist:{rawlist}")
                            #print(f"raw:{raw}")

                            if chainHash in hashes:
                                loop=True
                                #print(f"yeah boi: {hashes[chainHash]}, {pos}")
                                sources.append( (prev,chainHash,chain[0][1]) )
                                links=DAG[chain[-1][0]]["data"][chain[-1][1]]["links"]#links of last member of chain
                                if maskedNodes:
                                    DAGcandidates[chainHash]["data"][chain[0][1]]={"links":[maskedNodes[0]],"mask":mask,"round":itteration,"length":length,"raw":raw}
                                    for i in range(len(maskedNodes)-1):
                                        DAGcandidates[maskedNodes[i][0]]["data"][maskedNodes[i][1]]={"links":references[i]["links"],"mask":references[i]["mask"],"round":itteration,"length":references[i]["links"],"raw":references[i]["raw"]}
                                    DAGcandidates[maskedNodes[-1][0]]["data"][maskedNodes[-1][1]]={"links":links,"mask":references[-1]["mask"],"round":itteration,"length":references[-1]["length"],"raw":references[-1]["raw"]}
                                else:
                                    DAGcandidates[chainHash]["data"][chain[0][1]]={"links":links,"mask":mask,"round":itteration,"length":length,"raw":raw}

            #print(f"sources: {sources}")
            DAG.update(DAGcandidates)
            #give sources to the new nodes
            for prev, h, location in sources:
                DAG[prev[0]]["data"][prev[1]]["links"].append([h,location])
        itteration+=1 
        
    return(DAG)

def extractPatterns(DAG):
    """
    returns all patterns from within a DAG
    """
    # Takes all nodes of the DAG as well as new patterns by  
    # the same logic as in the construction of the DAG   

    seperatedMasks=[[] for i in range(MASKWIDTH+1)]#2d list of masks seperated by their size
    for mask in generateMasks():
        seperatedMasks[mask.bit_length()].append(mask)
    
    width=0
    for width in range(1,len(seperatedMasks)):
        indicesOfWidth=[mask2indices(mask) for mask in seperatedMasks[width]]
        DAGcandidates=defaultdict(lambda: {"data":defaultdict(lambda: {"raw":[],"links":[],"mask":0,"round":0, "length":0})})
        sources=[]
        for key, data in list(DAG.items()):
            for pos in list(data["data"].keys()):
                chains=generateChains(DAG,[key,pos],width) #every chain of length width !after! the given one
                for chain in chains:
                    #print(f"chain: {chain}")
                    if chain[-1][0]==0:#chains must be like not include the sink node 
                        continue
                    prev=chain[0]
                    chain=chain[1:]

                    for mask in seperatedMasks[width]:
                        indices=mask2indices(mask)
                        rawlist=[]
                        previndex=-5
                        for index in range(len(chain)):
                            if index in indices:
                                m=DAG[chain[index][0]]["data"][chain[index][1]]["mask"]
                                r=DAG[chain[index][0]]["data"][chain[index][1]]["raw"]
                                #rint(f"nodeRaw:{r}")
                                #hl=r[1]
                                #text=r[0]

                                if index > previndex+1:
                                    rawlist.append([[m,r]])
                                else:
                                    rawlist[-1].append([m,r])
                                previndex=index

                        maskedNodes=[]
                        references=[]
                        chainHash,length=stateCombine([[chain[index][0],DAG[chain[index][0]]["data"][chain[index][1]]["length"]] for index in indices])
                        for index in range(len(chain)):
                            if index not in indices:
                                #seperate this chain from the others by giving a deterministically randomised location
                                maskedNodes.append([chain[index][0],chainHash+index])
                                references.append(DAG[chain[index][0]]["data"][chain[index][1]])

                        #if already explored (ie prev from a different node)
                        if chainHash in DAGcandidates:
                            if chain[0][1] in DAGcandidates[chainHash]["data"]:
                                sources.append( (prev,chainHash,chain[0][1]) )
                                break

                        #join the raws of all these nodes
                        rawfunction=lambda raws: combine(
                                lambda x,y: [x[0]+y[0], stateCombine([x[1],y[1]])],
                                raws,

                                lambda: ["",[0,0]]
                            )
                        raw=[rawfunction(raws) for raws in rawlist]

                        #print(f"yeah boi: {hashes[chainHash]}, {pos}")
                        sources.append( (prev,chainHash,chain[0][1]) )
                        links=DAG[chain[-1][0]]["data"][chain[-1][1]]["links"]#links of last member of chain
                        if maskedNodes:
                            DAGcandidates[chainHash]["data"][chain[0][1]]={"links":[maskedNodes[0]],"mask":mask,"round":0,"length":length,"raw":raw}
                            for i in range(len(maskedNodes)-1):
                                DAGcandidates[maskedNodes[i][0]]["data"][maskedNodes[i][1]]={"links":references[i]["links"],"mask":references[i]["mask"],"round":0,"length":references[i]["links"],"raw":references[i]["raw"]}
                            DAGcandidates[maskedNodes[-1][0]]["data"][maskedNodes[-1][1]]={"links":links,"mask":references[-1]["mask"],"round":0,"length":references[-1]["length"],"raw":references[-1]["raw"]}
                        else:
                            DAGcandidates[chainHash]["data"][chain[0][1]]={"links":links,"mask":mask,"round":0,"length":length,"raw":raw}

    DAG.update(DAGcandidates)
    for prev, h, location in sources:
        DAG[prev[0]]["data"][prev[1]]["links"].append([h,location])

    patterns=[] 
    for key,d in DAG.items():
        if key!=0:
            for location, d2 in d["data"].items():
                patterns.append((d2["raw"],d2["mask"],key,location))
    return(patterns)

if __name__=="__main__":
    #print(stateCombine([[0,0],[90562456458300340380530175575906829794937656566326909372563908985992714911744, 1]]))
    #print(stateCombine([[90562456458300340380530175575906829794937656566326909372563908985992714911744, 1],[48798591765648602533665786387796102391711931756703157467141673184823938646016,1]]))


    #print("today came yesterday")
    #print(stateCombine([[0,0],[90562456458300340380530175575906829794937656566326909372563908985992714911744, 1]]))
    #testfunct=lambda x,y: [x[0]+y[0], stateCombine([x[1],y[1]])]
    #print("tomorrowcomestoday")
    #print(testfunct(['', [0, 0]],['y', [90562456458300340380530175575906829794937656566326909372563908985992714911744, 1]]))
    #setup
    parts=["yeah","man","this","is","the","sent","ence","sentence","th","this is","ye", "sen", "ten", "ce", "ti", "sne", "sn" ]+[c for c in "abcdefghijklmnopqrstuvwxyzI "]
    hashes={stateAppend(0,part):part for part in parts}
    with open("data/englishTestCorpus/eng-uk_web_2002_10K-sentences.txt","r") as f:
        corpus=[line.split('\t')[1] for line in f.readlines()]
    hashes={}
    sentence=TESTSENTENCE
    DAG=generateDAG(sentence, hashes)
    DAGpatterns=extractPatterns(DAG)


    for DAGpattern in DAGpatterns:
        print(DAGpattern)

    count=0
    total=len(corpus)
    patterns=defaultdict(lambda: defaultdict(lambda: {"f":0,"raw":""}))
    for sentence in corpus:
        count+=1
        if not count%2000:
            percentage=100*count//total
            print(f"{count} out of {total} ({percentage}%)")
        DAGpatterns=extractPatterns(generateDAG(sentence,hashes))
        for pattern in DAGpatterns:
            (raw,mask,h,location)=pattern
            text="".join([tag[0] for tag in raw])
            patterns[h][mask]["f"]+=1
            patterns[h][mask]["raw"]=raw


    with open("patterns.json", "w") as f:
        json.dump(patterns, f, indent=4)



if 1: a=1
else: 
    decomposed=maskDecompose(sentence)
    patterns=defaultdict(lambda: defaultdict(lambda:{"f":0,"subs":[]}))
    for mask,items in decomposed.items():
        for chars in items:
            key = stateAppend(0,chars) #<< MASKWIDTH + mask
            patterns[key][mask]["f"]+=1
            if not patterns[key][mask]["subs"]: 
                patterns[key][mask]["subs"] = [stateAppend(0,c) for c in chars]
            print(chars)

    with open("patterns.json", "w") as f:
        json.dump(patterns, f, indent=4)
    
    #with open("patterns.json", "r") as f:
    #    loaded_data = json.load(f)
    #    if stateAppend(0,"yeah") in hashes:
    #        print("yup")


#check hashes

