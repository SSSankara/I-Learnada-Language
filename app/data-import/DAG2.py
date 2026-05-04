from customHash import stateAppend, stateCombine, stateAppendRaw
from globalVariables import MASKWIDTH, HASHSIZE
from masks import generateMasks, int2binlist, mask2indices
import json
import pickle #save patterns
from collections import defaultdict #make writing to dicts easier
from functools import lru_cache


TESTSENTENCE="yeah man this is the sentence I wish to test lol thanks"

def initialiseDAG(sentence):
    DAG=defaultdict(lambda: defaultdict(lambda: {"links":[],"mask":1,"round":0, "length":0,"raw":["",[0,0]],"masked":False}))
    sentenceHashes=[[[char,[stateAppend(0,char),1]]] for char in sentence] #added garbage space so all characters are added to DAG
    sentenceHashes.append([["",[0,0]]])
    DAG[0]={-1:{"links":[[sentenceHashes[0][0][1][0],0]],"mask":0,"round":0,"length":0,"raw":["",[0,0]],"masked":False},len(sentence):{"links":[],"mask":1, "round":0, "length":0,"raw":["",[0,0]],"masked":False}} #start and end
    i=0
    for i in range(len(sentenceHashes)-1):
        DAG[sentenceHashes[i][0][1][0]][i]={"links":[[sentenceHashes[i+1][0][1][0],i+1]],"mask":1,"round":0,"length":1,"raw":sentenceHashes[i],"masked":False}
    return(DAG)

@lru_cache(None)
def cachedStateCombine(tupleinput):
    return stateCombine(list(tupleinput))

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
def generateChains(DAG, n, itteration, loop, fucklist, references=None , start=None, chain=None,new=False,first=True):
    """
    return a genererator of all chains of patterns of length
    n from a pattern, Start: [hash, index]
    note: first member is not part of the chain
    note: only returns chains who have a member from round at least
    """
    if first:
        for key, data in list(DAG.items()):
            for pos in list(data.keys()):#for every node in the DAG (hash, index)
                yield from generateChains(DAG, n, itteration, loop, fucklist, references=references, start=[key,pos], chain=None, new=new, first=False)
        return

    if chain==None: chain=[]
    if start==None: start=[]
    if references==None: references=[]

    if start[0]==0 and start[1]>0:
        return

    chain=chain+[start]
    references=references+[DAG[start[0]][start[1]]]
    if not new:
        if references[-1]["round"] == itteration-1-(loop==1)*1:
            new=True
    #references=[DAG[node[0]][node[1]] for node in chain]

    if (new or loop == 1) and (len(chain)>1+1*(itteration>1)):
        chainHash,length=cachedStateCombine(tuple((c[0],references[i]["length"]) for i,c in enumerate(chain[1:])))
        fuckKey = chainHash ^ (chain[0][1] << 5)
        if fuckKey not in fucklist:
            yield (chain, references)
    if n==0:
        return 

    #print(chain)
    for link in DAG[start[0]][start[1]]["links"]:
        node = DAG.get(link[0], {}).get(link[1])
        if node is not None:
            yield from generateChains(DAG, n-1, itteration, loop, fucklist, references=references, start=link, chain=chain, new=new, first=False)


def expandDAG(DAG,hashes,expand=True,expRound=-420): #where round refers to which hashes you want to make patterns out of

    separatedMasks=[[] for i in range(MASKWIDTH+1)]#2d list of masks seperated by their size
    separatedIndices=[[] for i in range(MASKWIDTH+1)]#2d list of indices
    for mask in generateMasks():
        separatedMasks[mask.bit_length()].append(mask)
        separatedIndices[mask.bit_length()].append(mask2indices(mask))

    loop=2
    itteration=0 # generation counts as 0th itteration
    DAGcandidates=defaultdict(lambda: {}) 
    sources=[]
    cap=2
    if expand:
        cap=1

    #join the raws of all these nodes
    rawfunction=lambda raws: combine(
            #lambda x,y: ["", stateCombine([x[1],y[1]])],
            lambda x,y: [x[0]+y[0], cachedStateCombine((tuple(x[1]),tuple(y[1])))],
            raws,
            lambda: ["",[0,0]]
                    )

    fucklist=set()
    while loop>=cap:
        itteration+=1
        chains=generateChains(DAG,len(separatedMasks)-1,itteration, loop,fucklist) #every chain of length width !after! the given one
        for chain,references in chains:
            prev=chain[0] # where the chain came from
            chain=chain[1:]
            width=len(chain)
            references=references[1:]

            for mask,indices in zip(separatedMasks[width],separatedIndices[width]):
                rawlist=[]
                DAGexplored=True
                Hashexplored=False
                #find if chain contains any new nodes 
                previndex=-1
                newmask=1
                maskedNodes=[]
                chainHash,length=cachedStateCombine(tuple((chain[index][0],references[index]["length"]) for index in indices))
                if chainHash==0:
                    continue
                fuckKey = chainHash ^ (chain[0][1] << 5) ^ mask
                if fuckKey in fucklist and loop>1:
                    continue
                fucklist.add(fuckKey)
                #if already explored (ie prev from a different node)
                if DAGcandidates.get(chainHash):
                    if DAGcandidates[chainHash].get(chain[0][1]):
                        sources.append( (prev,chainHash,chain[0][1]) )
                        continue
                if DAG.get(chainHash):
                    if DAG[chainHash].get(chain[0][1]):
                        sources.append( (prev,chainHash,chain[0][1]) )
                        continue

                for index in range(len(chain)):
                    if index in indices:
                        m=references[index]["mask"]
                        r=references[index]["raw"]

                        if index > previndex+1: #if,else to join sequential nodes, keep others seperate
                            rawlist.append([[m,r]])
                            newmask <<= 2
                            newmask |= 1 # I fucking love bit operators
                        else:
                            if not rawlist:
                                rawlist=[[]]
                            rawlist[-1].append([m,r])

                        #make sure at least one node from previous itteration or expansion
                        if (references[index]["round"]==itteration-1-1*(loop==1)):
                            DAGexplored=False
                        previndex=index

                    else:
                        #seperate this chain from the others by giving a deterministically randomised location
                        maskedNodes.append([chain[index][0],chainHash+index])

                # make sure there are new nodes in the chain
                if (DAGexplored and loop > 1): #or hashexplored:
                    continue
                if rawlist==[[]]:
                    continue

                raw=[rawfunction(raws) for raws in rawlist]
                sh=sum([part[1][0] for part in raw]) & ((1<<HASHSIZE)-1)
                # if this already exists (final round)
                if loop==1 and chainHash in hashes and expand:
                    if sh in hashes.get(chainHash, {}):
                        continue

                match=False
                if chainHash in hashes:
                    if sh in hashes.get(chainHash, {}):
                        match=True

                #DEBUG
                #debugstring=f"{itteration} {loop} | " 
                #for r in raw:
                #    debugstring+= r[0].replace("\n","")+" "
                #print(debugstring[:min(len(debugstring),49)],end="\r")
                #print(itteration,loop,end="|")
                #for r in raw:
                #    print(r[0],end=" ")
                #print("")

                if (match and loop>1) or (not match and loop==1):
                    if loop != 1:
                        loop=3

                    
                    sources.append( (prev,chainHash,chain[0][1]) )
                    links=DAG[chain[-1][0]][chain[-1][1]]["links"]#links of last member of chain
                    if maskedNodes:
                        DAGcandidates[chainHash][chain[0][1]]={"links":[maskedNodes[0]],
                                                               "mask":newmask,
                                                               "round":itteration,
                                                               "length":length,
                                                               "raw":raw,
                                                               "masked":False,
                                                               "sh":sh}
                        maskedReferences=[]
                        for index in range(len(chain)):
                            if index not in indices:
                                maskedReferences.append(references[index])
                        for i in range(len(maskedNodes)-1):
                            DAGcandidates[maskedNodes[i][0]][maskedNodes[i][1]]={
                                    "links":[maskedNodes[i+1]],
                                    "mask":maskedReferences[i]["mask"],
                                    "round":itteration,
                                    "length":maskedReferences[i]["length"],
                                    "raw":maskedReferences[i]["raw"],
                                    "masked":True,
                                    "sh":maskedNodes[i][0]}
                        DAGcandidates[maskedNodes[-1][0]][maskedNodes[-1][1]]={
                                "links":links,
                                "mask":maskedReferences[-1]["mask"],
                                "round":itteration,
                                "length":maskedReferences[-1]["length"],
                                "raw":maskedReferences[-1]["raw"],
                                "masked":True,
                                "sh":maskedNodes[-1][0]}
                    else:
                        DAGcandidates[chainHash][chain[0][1]]={
                                "links":links,
                                "mask":newmask,
                                "round":itteration,
                                "length":length,
                                "raw":raw,
                                "masked":False,
                                "sh":sh}
               

        if loop>1:
            for key,d in DAGcandidates.items():
                for location, d2 in d.items():
                    DAG[key][location]=d2

            #give sources to the new nodes
            for prev, h, location in sources:
                DAG[prev[0]][prev[1]]["links"].append([h,location])

            DAGcandidates=defaultdict(lambda: {})#defaultdict(lambda: defaultdict(lambda:  {"raw":[["",[0,0]]],"links":[],"mask":0,"round":0, "length":0,"masked":False}))
            sources=[]#keep track of where each chain came from for relinking into DAG
        loop-=1


    if expand:
        return(DAGcandidates)
    for key,d in DAGcandidates.items():
        for location, d2 in d.items():
            DAG[key][location]=d2
    #give sources to the new nodes
    for prev, h, location in sources:
        DAG[prev[0]][prev[1]]["links"].append([h,location])
    return(DAG)





def extractPatterns(DAG,r=-1,raw=False):
    #patterns=defaultdict(lambda: defaultdict(lambda: {"f":0,"raw":""}))
    patterns=defaultdict(lambda: defaultdict(lambda: {"f":0,"round":0}))
    for key,d in DAG.items():
        if key!=0:
            for location, d2 in d.items():
                subhash=sum([part[1][0] for part in d2["raw"]])
                if subhash == 0:
                    continue
                if d2["masked"]:
                    continue
                patterns[key][subhash]["f"]+=1
                if raw:
                    patterns[key][subhash]["raw"]=d2["raw"]
                patterns[key][subhash]["round"]=r
    #print(patterns)
    return(patterns)

if __name__=="__main__":
    sentence=TESTSENTENCE
    parts=["yeah","man","this","is","the","sent","ence","sentence","th","this is","ye", "sen", "ten", "ce", "ti", "sne", "sn" ]+[c for c in "abcdefghijklmnopqrstuvwxyzI "]
    hashes={stateAppend(0,part):{stateAppend(0,part):0} for part in parts}
    #with open("hashish.json","r") as f:
    #    hashes=json.load(f)

    #hashes={}

    print(sentence)
    print("initialising sentence")
    DAG=initialiseDAG(sentence)
    print("expanding DAG")
    DAG=expandDAG(DAG,hashes,expand=True)
    #print(json.dumps(DAG, indent=2))
    patterns=defaultdict(lambda: defaultdict(lambda: {"f":0}))
    extractPatterns(DAG)

    print("extracting patterns")
    for h,d in DAG.items():
        for location,d2 in d.items():
            if d2["masked"]:
                continue
            sh=d2["sh"]
            patterns[h][sh]["raw"]=d2["raw"]
            if h==sh:
                patterns[h][sh]["f"]+=1
            else:
                patterns[h][sh]["f"]+=0.1

    with open("patterns.json","w") as f:
        json.dump(patterns, f, indent=2)
    
    #from line_profiler import LineProfiler

    #lp = LineProfiler()
    #lp.add_function(expandDAG)
    #DAG=initialiseDAG(sentence)
    #
    #lp.run('expandDAG(DAG, hashes, expand=True)')
    #lp.print_stats()
    ##lp.add_function(extractPatterns)
    ##lp.run('extractPatterns(DAG, raw=True)')
    #lp.print_stats()
    #print(json.dumps(patterns, indent=2))
    print(f"no patterns: {len(patterns)}")
