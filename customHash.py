import time
from globalVariables import HASHSIZE


MASK=(1<<HASHSIZE)-1 #
CONST = int((2**HASHSIZE) * ((1 + 5**0.5) / 2)) & MASK
def rotate(x,r):
    """rotate a binary number, ie shift left r times and put the carry at the start"""
    return ((x << r) & MASK) | (x >> (HASHSIZE - r))

def stateAppend(state, string):
    """change state new unique based on new hash 
    - (xor+rotation+mix) ensures uiqueness
    this is non commutative - order matters, 
    and associative - xy + z is the same as x + yz"""
    # multiply ord by phi times 2^HASHSIZE for determinstic then
    # rotate by 5 for a mix step (sentences should idealy be under HASHSIZE chars)
    for c in string:
        state = rotate(state,5) 
        state ^= ord(c) * CONST
        state &= MASK
    return(state)

def combine(d1,d2):
    [h1,l1]=d1
    [h2,l2]=d2
    return [
        rotate(h1, l2 * 5) ^ h2,
        l1 + l2
    ]

def stateCombine(data):
    out=data[0]
    for d in data[1:]:
        out=combine(out,d)
    return(out)

def stateAppendRaw(state, data):
    """
    same as stateAppend but with the hashes as an input
    rather than the strings
    """
    length=sum(l for _, l in data)
    state = rotate(state, length * 5)
    for h,l in data:
        length-=l
        state ^= rotate(h,length*5) 
    return(state)



##test hashing function
if __name__=="__main__":
    #with open("data/tur-tr_web_2019_300K/tur-tr_web_2019_300K-sentences.txt","r") as f:
    #    sentences=f.readlines()
    ##sentence=input("gib sebtens:\n")
   
    #state=0
    #count=0
    #start=time.time()
    #for sentence in sentences:
    #    count+=1
    #    state=stateAppend(state, sentence)
    #runtime=time.time()-start
    #print(f"time:{runtime}\ncount:{count}\nspeed:{1000*runtime/count}ms per sentence")

    sentence=input("gib sebtens:\n")
   
    state=0
    count=0
    start=time.time()
    for i in range(len(sentence)):
        count+=1
        part1=sentence[:i]
        part2=sentence[i:]
        s1=stateAppend(0,part1)
        s2=stateAppend(0,part2)
        s3=stateAppend(s1,part2)
        print(f"""=====
p1:{part1},s1:{s1}
p2:{part2},s2:{s2}
total:{s3}""")
    runtime=time.time()-start
    print(f"time:{runtime}\ncount:{count}\nspeed:{1000*runtime/count}ms per sentence")
