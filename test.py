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
    input itemformat, the default item eg 0 for int, [] for list
    amount of ones in the mask must be the same as number of items
    """
    output=itemformat
    print("combination")
    iters=[[iter(int2binlist(mask)),iter(hashes)] for [mask, hashes] in items]

    while iters:
        level=0
        while level < len(iters):
            try:
                tamade=next(iters[level][0])#mask digit
                if tamade:
                    #output=stateAppend(output,next(iters[level][1]))#hash
                    #output.append(next(iters[level][1]))
                    output=f(output,next(iters[level][1]))
                    print(f"tamade:{output}")
                    level=0
                    break
                level+=1
            except:
                del iters[level]
    return(output)


def findPatterns(sentence,hashes):
    """
    a variation on maskDecompose that also builds up patterns
    by building up a directed acryllic graph of different ways
    to build up the sentence.
    """
    print(hashes)
    # dag from source hash to end where sequentially hashing
    # across any path will make the hash of the sentence.
    # For a given index, it includes the mask, the subsequent
    # hash and it's index, and the round it was explored (to
    # avoid redundant checks. There is also a lookup of hashes
    # to raw letters and hashes as well as their lengths (for 
    # hashing)
    DAG=defaultdict(lambda: {"data":defaultdict(lambda: {"links":[],"mask":0,"round":0, "length":0,"raw":[]})})
    sentenceHashes=[[char,stateAppend(0,char),1] for char in sentence+" "] #added garbage space so all characters are added to DAG
    print(f"sentenceHashes: {sentenceHashes}")
    print(f"Length of first item: {len(sentenceHashes[0])}")
    print(f"First item: {sentenceHashes[0]}")
    print(f"Last element of first item: {sentenceHashes[0][-1]}")
    #set up default graph (all characters of the sentence)
    DAG[0]={"data":{-1:{"links":[[sentenceHashes[0][1],0]],"round":0,"length":0,"raw":[]},len(sentence):{"links":[], "round":0, "length":0,"raw":[]}}} #start and end
    i=0
    for i in range(len(sentenceHashes)-1):
        DAG[sentenceHashes[i][1]]["data"][i]={"links":[[sentenceHashes[i+1][1],i+1]],"mask":1,"round":1,"length":1,"raw":sentenceHashes[i]}

    #function to recursively generate chains (generator object for ram)
    def generateChains(start, n, path=None):
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

        for link in DAG[start[0]]["data"][start[1]]["links"]:
            yield from generateChains(link, n-1, chain)

    seperatedMasks=[[] for i in range(MASKWIDTH+1)]#2d list of masks seperated by their size
    for mask in generateMasks():
        seperatedMasks[mask.bit_length()].append(mask)
    
    loop=True
    itteration=2 #counter for itterations, starts at round 2
    #while loop:
    for i in range(2):
        loop=False

        width=0
        decomposed={}
        for width in range(2,len(seperatedMasks)):
            indicesOfWidth=[mask2indices(mask) for mask in seperatedMasks[width]]
            #print(f"indices: {indicesOfWidth}")
            #print(f"seperatedMasks: {seperatedMasks}")
            DAGcandidates=defaultdict(lambda: {"data":defaultdict(lambda: {"raw":[],"links":[],"mask":0,"round":0, "length":0})})
            sources=[]
            for key, data in DAG.copy().items():
                for pos in data["data"].keys():
                    chains=generateChains([key,pos],width) #every chain of length width !after! the given one
                    for chain in chains:
                        if chain[-1][1]==len(sentence):#chains must be like not include the sink node 
                            continue
                        prev=chain[0]
                        chain=chain[1:]
                        #make sure there are new nodes in the chain
                        for node in chain:
                            if DAG[node[0]]["data"][node[1]]["round"]==itteration-1:
                                break
                        else:
                            continue
                        for mask in seperatedMasks[width]:
                            indices=mask2indices(mask)
                            rawlist=[]
                            explored=True
                            #find if chain contains any new nodes 
                            maskedNodes=[]
                            for index in range(len(chain)):
                                if index in indices:
                                    m=DAG[chain[index][0]]["data"][chain[index][1]]["mask"]
                                    r=DAG[chain[index][0]]["data"][chain[index][1]]["raw"]
                                    #rint(f"nodeRaw:{r}")
                                    hl=r[1:]
                                    text=r[0]

                                    rawlist.append([m,[text,hl]])
                                    if DAG[chain[index][0]]["data"][chain[index][1]]["round"]==itteration-1:
                                        explored=False
                            if explored:
                                continue

                            #join the raws of all these together
                            raw=combine(
                                    lambda x,y: [x[0]+y[0],stateCombine(x[1],y[1])],
                                    rawlist,
                                    ["",0]
                                )
                            print(f"rawlist:{rawlist}")
                            print(f"raw:{raw}")

                            chainHash,length=stateCombine([(chain[index][0],DAG[chain[index][0]]["data"][chain[index][1]]["length"]) for index in indices])
                            for index in range(len(chain)):
                                if index not in indices:
                                    #seperate this chain from the others by giving a deterministically randomised location
                                    maskedNodes.append([node[1],chainHash+index])
                            #if already explored (ie prev from a different node)
                            if chainHash in DAGcandidates:
                                if chain[0][1] in DAGcandidates[chainHash]["data"]:
                                    sources.append( (prev,chainHash,chain[0][1]) )
                                    break

                            if chainHash in hashes:
                                #print(f"yeah boi: {hashes[chainHash]}, {pos}")
                                sources.append( (prev,chainHash,chain[0][1]) )
                                links=DAG[chain[-1][0]]["data"][chain[-1][1]]["links"]#links of last member of chain
                                if maskedNodes:
                                    DAGcandidates[chainHash]["data"][chain[0][1]]={"links":maskedNodes[0],"mask":mask,"round":itteration,"length":length,"raw":raw}
                                    for i in range(len(maskedNodes)-1):
                                        DAGcandidates[maskedNodes[i][0]]["data"][maskedNodes[i][1]]={"links":[maskedNodes[i+1]],"mask":mask,"round":itteration,"length":length,"raw":raw}
                                else:
                                    DAGcandidates[chainHash]["data"][chain[0][1]]={"links":links,"mask":mask,"round":itteration,"length":length,"raw":raw}

            #print(f"sources: {sources}")
            DAG.update(DAGcandidates)
            #give sources to the new nodes
            for prev, h, location in sources:
                DAG[prev[0]]["data"][prev[1]]["links"].append([h,location])
        itteration+=1 
        print(f"here:{DAG}")
        
    with open("DAG.json","w") as f:
        json.dump(DAG,f,indent=4)

    patterns=[] 
    for key,d in DAG.items():
        if key!=0:
            for location, d2 in d["data"].items():
                patterns.append((d2["raw"],mask2indices(d2["mask"]).count(0),key,location))
    return(patterns)




if __name__=="__main__":
    #setup
    parts=["yeah","man","this","is","the","sent","ence","sentence","th","this is","ye", "sen", "ten", "ce", ]+[c for c in "abcdefghijklmnopqrstuvwxyzI "]
    hashes={stateAppend(0,part):part for part in parts}
    print(hashes)
    sentence=TESTSENTENCE
    print(findPatterns(sentence, hashes))


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

