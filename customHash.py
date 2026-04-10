import time

MASK=(1<<64)-1 #
def rotate(x,r):
    """rotate a binary number, ie shift left r times and put the carry at the start"""
    return ((x << r) & MASK) | (x >> (64 - r))

def stateAppend(state, string):
    """change state new unique based on new hash 
    - (xor+rotation+mix) ensures uiqueness
    this is non commutative - order matters, 
    and associative - xy + z is the same as x + yz"""
    # multiply by phi times 2^64 for determinstic then
    # rotate by 5 for a mix step (sentences should idealy be under 64 chars)
    for c in string:
        state ^= ord(c) * 0x9E3779B97F4A7C15 
        state = rotate(state,5) 
    return(state)

##test hashing function
if __name__=="__main__":
    #with open("data/tur-tr_web_2019_300K/tur-tr_web_2019_300K-sentences.txt","r") as f:
    #    sentences=f.readlines()
    sentence=input("gib sebtens:\n")
   
    state=0
    count=0
    start=time.time()
    #for sentence in sentences:
    #count+=1
    state=stateAppend(state, sentence)
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
