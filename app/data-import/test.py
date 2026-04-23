from DAG2 import initialiseDAG, expandDAG, extractPatterns
import matplotlib.pyplot as plt
import numpy as np
from collections import defaultdict
import json
import pickle
import time
from functools import lru_cache


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
    patterns2=defaultdict(lambda: defaultdict(lambda: {"f":0,"raw":""}))
    for k,d in patterns.items():
        for m,d2 in d.items():
            if(boolFunction(d2["f"])):
                patterns2[k][m]=d2
    return patterns2




if __name__=="__main__":
    with open("../../assets/englishTestCorpus/eng-uk_web_2002_10K-sentences.txt","r") as f:
        corpus=[line.split('\t')[1] for line in f.readlines()]
    hashes=defaultdict(lambda: defaultdict(lambda: {"f":0,"raw":""}))

    with open("pinru.pkl","rb") as f:
        hashes=pickle.load(f)

    #hashes={}

    #sentence=("yeah this is the queen speaking, billion, very modern")
    #sentence=("A $4.6 billion overrun on a $6 billion budget is just chump chnage to him.")
    #sentence="For noise which is persistent but occurs on such an irregular basis that the case officer is unable to attend, the Council operates an emergency out of hours service."
    #sentence="你你你在这儿干什么"
    sentence="发现了洪世贤的工作证"
    print("initialising DAG")
    DAG=initialiseDAG(sentence)
    print("expanding DAG")
    DAG=expandDAG(DAG,hashes)
    print("extracting from DAG")
    patterns=extractPatterns(DAG,raw=True)
    #for key, pattern in patterns.items():
    #    print(key, pattern.items())
    from line_profiler import LineProfiler

    #lp = LineProfiler()
    #lp.add_function(expandDAG)
    #DAG=initialiseDAG(sentence)
    #
    #lp.run('expandDAG(DAG, hashes, expand=True)')
    #lp.print_stats()


