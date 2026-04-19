import matplotlib.pyplot as plt
import numpy as np
from collections import defaultdict
import json

with open("patterns.json","r") as f:
    patterns=json.load(f)
freqs = []
count1=0
for k,d in patterns.items():
    for m,d2 in d.items():
        count1+=1
        freqs.append(d2["f"])


fig1=plt.hist(freqs, bins=50)
plt.xlabel("Pattern frequency")
plt.ylabel("Number of patterns")
plt.title("Pattern Frequency Distribution")
plt.yscale("log")  # IMPORTANT for long tail
plt.savefig("plot.png", dpi=200, bbox_inches="tight")
print("saved to plot.png")

threshold = np.percentile(freqs, 80)

def freqFilter(patterns,boolFunction):
    patterns2=defaultdict(lambda: defaultdict(lambda: {"f":0,"raw":""}))
    for k,d in patterns.items():
        for m,d2 in d.items():
            if(boolFunction(d2["f"])):
                patterns2[k][m]=d2
    return patterns2

patterns2=freqFilter(patterns,lambda f: f>threshold)

freqs2=[]
count2=0
for k,d in patterns2.items():
    for m,d2 in d.items():
        count2+=1
        freqs2.append(d2["f"])

plt.close()
fig2=plt.hist(freqs2, bins=50)
plt.xlabel("Pattern frequency")
plt.ylabel("Number of patterns")
plt.title("Pattern Frequency Distribution")
plt.yscale("log")  # IMPORTANT for long tail
plt.savefig("plot2.png", dpi=200, bbox_inches="tight")
print("saved to plot2.png")

print(f"c1,c2: {count1,count2}")
