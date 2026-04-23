from globalVariables import MASKWIDTH

def generateMasks(maskwidth=MASKWIDTH):
    mid=2**(maskwidth//2)
    return([i for i in range(1,2**maskwidth,2)]) # odd numbers for no repeated masks


def int2binlist(num):
    """
    turn mask integer into list of binary 1s and 0s
    """
    return [(num >> i) & 1 for i in range(num.bit_length() - 1, -1, -1)]

def mask2indices(mask):
    """
    turn binary mask into list of locations that are 1
    """
    return [i for i in range(2**MASKWIDTH) if (mask >> i) & 1]
