import matplotlib.pyplot as plt
import json

with open("patterns.json","r") as f:
    patterns=json.load(f)
freqs = []
for k,d in patterns.items():
    for m,d2 in d.items():
        freqs.append(d2["f"])


plt.hist(freqs, bins=50)
plt.xlabel("Pattern frequency")
plt.ylabel("Number of patterns")
plt.title("Pattern Frequency Distribution")
plt.yscale("log")  # IMPORTANT for long tail
plt.savefig("plot.png", dpi=200, bbox_inches="tight")
print("saved to plot.png")
