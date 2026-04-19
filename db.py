from DAG2 import initialiseDAG, expandDAG, extractPatterns
import matplotlib.pyplot as plt
import numpy as np
from collections import defaultdict
import json
import pickle
import time
import sqlite3
import math


def create_db(path):
    conn=sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS sentences (
        sentence_id INTEGER PRIMARY KEY AUTOINCREMENT,
        text    TEXT NOT NULL UNIQUE
    );
    CREATE TABLE IF NOT EXISTS patterns (
        pattern_id INTEGER PRIMARY KEY AUTOINCREMENT,
        hash    BLOB NOT NULL,
        subhash    BLOB NOT NULL,
    -- integers can only be 64 bits, blob 16 bytes=128 bits
        doc_frequency INTEGER NOT NULL DEFAULT 0,
        idf_score   REAL,
        UNIQUE (hash,subhash)
    );
    CREATE TABLE IF NOT EXISTS sentences_patterns (
        sentence_id INTEGER NOT NULL REFERENCES sentences(sentence_id),
        pattern_id  INTEGER NOT NULL REFERENCES patterns(pattern_id),
        PRIMARY KEY (sentence_id, pattern_id)
    );
    CREATE TABLE IF NOT EXISTS knn_edges (
        sentence_id INTEGER NOT NULL REFERENCES sentences(sentence_id),
        neighbour_id    INTEGER NOT NULL REFERENCES sentences(sentence_id),
        similarity  REAL NOT NULL,
        PRIMARY KEY (sentence_id, neighbour_id)
    );
    CREATE TABLE IF NOT EXISTS learners (
        learner_id  INTEGER PRIMARY KEY AUTOINCREMENT,
        name    TEXT NOT NULL UNIQUE,
        created_at  REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS learner_state (
        learner_id INTEGER NOT NULL REFERENCES learners(learner_id),
        sentence_id INTEGER NOT NULL REFERENCES sentences(sentence_id),
        stability   REAL NOT NULL DEFAULT 0.1,
        activation  REAL NOT NULL DEFAULT 0.1,
        last_event_time REAL NOT NULL,
        PRIMARY KEY (learner_id, sentence_id)
    );

    CREATE INDEX IF NOT EXISTS idx_sp_sentence
        ON sentences_patterns(sentence_id);
    CREATE INDEX IF NOT EXISTS idx_sp_pattern
        ON sentences_patterns(pattern_id);
    CREATE INDEX IF NOT EXISTS idx_knn_sentence
        ON knn_edges(sentence_id);
    CREATE INDEX IF NOT EXISTS idx_ls_learner
        ON learner_state(learner_id);
    """)
    conn.commit()
    return(conn)

def hash2blob(h:int):
    return h.to_bytes(16,byteorder='big', signed=True)
def blob2hash(b:bytes):
    return int.from_bytes(b, byteorder='big', signed=True)



if __name__=="__main__":
    with open("data/pinru/subs","r") as f:
        corpus=f.readlines()
    with open("pinru.pkl","rb") as f:
        hashes=pickle.load(f)
    #with open("data/eng_newscrawl_/eng_newscrawl_2018_10K-sentences.txt","r") as f:
    #   corpus=[line.split('\t')[1] for line in f.readlines()]
    #with open("hashish.pkl","rb") as f:
    #    hashes=pickle.load(f)
    #with open("data/quran","r") as f:
    #    corpus=f.readlines()
    #with open("quran.pkl","rb") as f:
    #    hashes=pickle.load(f)
    conn = create_db("pinru.db")
    cur=conn.cursor()

    
    for sentence in corpus:
        cur.execute("INSERT OR IGNORE INTO sentences(text) values (?)",
                    (sentence,))
        sentence_id=cur.execute("SELECT sentence_id FROM sentences WHERE text = ?",
                     (sentence,)).fetchone()[0]

        DAG=initialiseDAG(sentence)
        DAG=expandDAG(DAG,hashes,expand=False)
        count=0
        print(sentence.replace("\n",""),end="||")
        for k,d in DAG.items():
            h=hash2blob(k)
            for k2,d2 in d.items():
                sh=hash2blob(k2)
                print(f"k={k}, sh={k2}")
                print(f"h={h.hex()}, sh={sh.hex()}")
                if d2["masked"]:
                    continue
                cur.execute(
                    "INSERT OR IGNORE INTO patterns (hash, subhash, doc_frequency) VALUES (?, ?, 0)",
                    (h,sh,)
                )
                cur.execute(
                    "UPDATE patterns SET doc_frequency = doc_frequency + 1 WHERE hash = ? AND subhash = ?",
                    (h,sh,)
                )
                rows = cur.execute("SELECT pattern_id, hex(hash), hex(subhash) FROM patterns").fetchall()
                print(f"patterns in db: {rows}")
                print(f"looking for h={h.hex()} sh={sh.hex()}")
                pattern_id = cur.execute(
                    "SELECT pattern_id FROM patterns WHERE hash = ? AND subhash = ?",
                    (h,sh,)
                ).fetchone()[0]
                cur.execute(
                    "INSERT OR IGNORE INTO sentences_patterns (sentence_id, pattern_id) VALUES (?, ?)",
                    (sentence_id, pattern_id,)
                )
            count+=1
            print([r[0] for r in d2["raw"]],end="|")


        # IDF
        patterns = conn.execute("SELECT pattern_id, doc_frequency FROM patterns").fetchall()
        N = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
        
        with conn:
            for pattern_id, df in patterns:
                idf = math.log(N+1 / df+1)   # natural log, base e
                conn.execute(
                    "UPDATE patterns SET idf_score = ? WHERE pattern_id = ?",
                    (idf, pattern_id)
                )
        print(count)





    conn.commit()

    conn.close

    










else: 
    #filename="pinru"
    filename="hashish"
    #filename="quran"
    with open(f"{filename}.pkl", "wb") as f:
        pickle.dump(hashes, f)
    with open(f"{filename}.json", "w") as f:
        json.dump(hashes, f, indent=2)

