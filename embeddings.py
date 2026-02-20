import sys
#for now, embeddings are saved as np lists
import numpy as np
from sentence_transformers import SentenceTransformer

def save_embeddings(embeddings, filename):
    np.save(filename,embeddings)

def load_embeddings(filename):
    return np.load(filename)

def append_embeddings(additions,filename):
    embedding=np.load(filename)
    np.save(filename,embedding+additions)

#assuming use of liepzig sentence corpus format
def save_corpus(corpusfilename,embeddingFilename):
    model=SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    with open(corpusfilename,"r") as corpus:
        sentences=[line.split("\t")[1] for line in corpus.readlines()]
    embeddings=model.encode(sentences)
    save_embeddings(embeddings,embeddingFilename)

#load the corpus once as it it heavy and then load it whenever needed
if __name__=="__main__":
    save_corpus(sys.argv[1],sys.argv[2])
