from DAG2 import initialiseDAG, expandDAG, extractPatterns
import matplotlib.pyplot as plt
import numpy as np
from collections import defaultdict
import json
import pickle
import time
import sqlite3
import math
import shutil

MIN_IDF=0.3

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
        session_id  INTEGER,
        PRIMARY KEY (learner_id, sentence_id)
    );
    CREATE TABLE IF NOT EXISTS sessions (
        session_id  INTEGER PRIMARY KEY AUTOINCREMENT,
        learner_id  INTEGER NOT NULL REFERENCES learners(learner_id),
        started_at  REAL NOT NULL
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
    return h.to_bytes(32,byteorder='big', signed=True)
def blob2hash(b:bytes):
    return int.from_bytes(b, byteorder='big', signed=True)

def timeleft(start, count, length):
    return (time.time()-start)*(length-count)/count


if __name__=="__main__":
    with open("../../assets/pinru/subs","r") as f:
        corpus=f.readlines()
    with open("pinru.pkl","rb") as f:
        hashes=pickle.load(f)
    #with open("../../assets/eng_newscrawl_/eng_newscrawl_2018_10K-sentences.txt","r") as f:
    #   corpus=[line.split('\t')[1] for line in f.readlines()]
    #with open("hashish.pkl","rb") as f:
    #    hashes=pickle.load(f)
    #with open("../../assets/quran","r") as f:
    #    corpus=f.readlines()
    #with open("quran.pkl","rb") as f:
    #    hashes=pickle.load(f)
    conn = create_db("../../data/pin2.db")
    cur=conn.cursor()

    start=time.time()
    
    print("adding corpus sentences to database")
    count=0
    length=len(corpus)
    for sentence in corpus:
        sentence=sentence.replace("\n","")
        cur.execute("INSERT OR IGNORE INTO sentences(text) values (?)",
                    (sentence,))
        sentence_id=cur.execute("SELECT sentence_id FROM sentences WHERE text = ?",
                     (sentence,)).fetchone()[0]

        DAG=initialiseDAG(sentence)
        DAG=expandDAG(DAG,hashes,expand=False)
        count+=1
        colsize = shutil.get_terminal_size().columns
        print(f"{count}/{length}, {timeleft(start,count,length):.0f}s remaining, {sentence.replace("\n","")}{" "*50}"[:colsize-2],end="\r",flush=True)
        for k,d in DAG.items():
            h=hash2blob(k)
            for k2,d2 in d.items():
                sh=hash2blob(k2)
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
                pattern_id = cur.execute(
                    "SELECT pattern_id FROM patterns WHERE hash = ? AND subhash = ?",
                    (h,sh,)
                ).fetchone()[0]
                cur.execute(
                    "INSERT OR IGNORE INTO sentences_patterns (sentence_id, pattern_id) VALUES (?, ?)",
                    (sentence_id, pattern_id,)
                )


    print(count)
    conn.commit()
    # IDF and sentence relations
    print("calculating IDF of each pattern")
    patterns = conn.execute("SELECT pattern_id, doc_frequency FROM patterns").fetchall()
    N = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
    print(f"num-patterns: {N}")
    
    for pattern_id, df in patterns:
        idf = max(math.log((N+1) / (df+1)),0)
        conn.execute(
            "UPDATE patterns SET idf_score = ? WHERE pattern_id = ?",
            (idf, pattern_id)
        )

    conn.commit()

    #relations

    sp = conn.execute("""
        SELECT sp.sentence_id, sp.pattern_id, p.idf_score
        FROM sentences_patterns sp
        JOIN patterns p ON p.pattern_id = sp.pattern_id
        WHERE p.idf_score >= ?
    """, (MIN_IDF,)).fetchall()
     
    sentence_patterns = defaultdict(dict)
    for sid, pid, idf in sp:
        sentence_patterns[sid][pid] = idf
     
    # Build inverted index
    print("building inverted index for jaccard")
    inverted = defaultdict(list)
    for sid, patterns in sentence_patterns.items():
        for pid in patterns:
            inverted[pid].append(sid)
     
    print("calculating Jaccard similarities")
    # weighted Jaccard 
    edges = []
    length=len(sentence_patterns)
    count=0
    start=time.time()
    for sid, patterns in sentence_patterns.items():
        count+=1
        colsize = shutil.get_terminal_size().columns
        print(f"{100*count/length:.1f}%, {timeleft(start,count,length):.0f}s remaining{" "*10}"[:colsize-1],end="\r")
        candidates = {nid for pid in patterns for nid in inverted[pid] if nid != sid}
     
        for nid in candidates:
            a, b = patterns, sentence_patterns[nid]
            all_p = a.keys() | b.keys()
            num = sum(min(a.get(p, 0.0), b.get(p, 0.0)) for p in all_p)
            den = sum(max(a.get(p, 0.0), b.get(p, 0.0)) for p in all_p)
            sim = num / den if den else 0.0
     
            if sim >= 0.05:
                edges.append((sid, nid, sim))
     
    print("inserting similarities")
    with conn:
        conn.executemany("""
            INSERT OR REPLACE INTO knn_edges (sentence_id, neighbour_id, similarity)
            VALUES (?, ?, ?)
        """, edges)
     
    print(f"Done. {len(edges):,} edges written.")






    conn.commit()

    conn.close()

    









