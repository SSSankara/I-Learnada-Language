import sqlite3
from collections import defaultdict
from q import Queue
import time
import math
import os
import pickle
from pypinyin import pinyin
from deep_translator import GoogleTranslator
import edge_tts
import asyncio
import io
import subprocess
import threading
import tempfile
import readchar

MIN_IDF=0.3
TAU_MAX=100*365*86400 #maximum decay constant - 100 years to decay to 1/e retrievability
TAU_MIN=86400 #1 day to decay to 1/e retrievability
REVIEW_RET_THRESHOLD=0.9
NEW_PER_SESSION=10
REWARD=0.05 #of the distance between stability and 1
PENALTY=0.3 #loss to the stability afterwards, these are subject to change
DEFAULT_STABILITY=((-86400/math.log(REVIEW_RET_THRESHOLD))-TAU_MIN)/(TAU_MAX-TAU_MIN)#passes review threshold in 24 hours

knn_cache=defaultdict(list)#for quick sentence edge lookups
global queue

def loadCache(conn,cache_path):
    global knn_cache
    if os.path.exists(cache_path):
        print("├─loading knn from cache...")
        with open(cache_path, "rb") as f:
            knn_cache = pickle.load(f)
    else:
        print("building knn cache from DB (this will only happen once per database)...")
        rows = conn.execute(
            "SELECT sentence_id, neighbour_id, similarity FROM knn_edges"
        ).fetchall()
        for sid, nid, sim in rows:
            knn_cache[sid].append((nid, sim))
        with open(cache_path, "wb") as f:
            pickle.dump(dict(knn_cache), f)
        print("knn cache saved.")

def loadSession(conn,learner_id):
    rows=conn.execute("""
        SELECT sentence_id,stability,last_event_activation, last_event_time, sentence_status 
        FROM learner_state WHERE learner_id = ?
    """, (learner_id,)).fetchall()
    learner_state_dict={sid:{"stability": s, "last_event_activation": a, "last_event_time":t, "sentence_status":stat} for sid,s,a,t,stat in rows}

    return (learner_state_dict)#dict(sentences_patterns))#,knn)

_current_proc = None
_play_lock = threading.Lock()
def playAudio(text, voice="zh-CN-XiaoxiaoNeural"):
    async def _run():
        global _current_proc
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            path = f.name
        await edge_tts.Communicate(text, voice).save(path)
        with _play_lock:
            if _current_proc and _current_proc.poll() is None:
                _current_proc.terminate()
            _current_proc = subprocess.Popen(
                ["mpg123", "-q", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            _current_proc.wait()
        os.unlink(path)

    threading.Thread(target=asyncio.run, args=(_run(),), daemon=True).start()

def decay(last_event_time,stability,last_event_activation=1):
    elapsed=time.time() - last_event_time
    tau=TAU_MIN + stability * (TAU_MAX-TAU_MIN)
    return(last_event_activation*math.exp(-elapsed/tau))

def retrievability(conn,lid,sid,ignore_activation=False):
    """It's called retrievability but also returns activation, stability, time, and status"""
    time, activation, stability,status=conn.execute(
            "SELECT last_event_time, last_event_activation, stability, sentence_status FROM learner_state WHERE sentence_id=? AND learner_id=?",
            (sid,lid,)
    ).fetchone()
    if ignore_activation:
        activation=1
    return(decay(time,stability,activation),activation,stability,status)

def setStatus(conn,lid,sid,session_id,learner_state_dict,status):
    learner_state_dict[sid]["sentence_status"]=status
    conn.execute("""
        UPDATE learner_state SET
        sentence_status=?,
        session_id=?
        WHERE learner_id=? AND sentence_id=?
    """,(status,session_id,lid,sid,)
    )


def cascadeKnown(conn,lid,sid,session_id,learner_state_dict):
    global queue
    cascadeQueue=[sid]
    visited=set()
    #all unknown neighbours and their patterns
    count=-1
    query="""
    WITH required AS ( 
    	SELECT DISTINCT k.neighbour_id AS nid, sp.pattern_id FROM knn_edges k
        JOIN learner_state x ON x.sentence_id=k.sentence_id
        JOIN sentences_patterns sp ON sp.sentence_id=k.neighbour_id
        WHERE  x.sentence_id=?
        AND NOT EXISTS (
            SELECT 1
            FROM learner_state y
            WHERE y.sentence_id=k.neighbour_id
            AND y.learner_id=?
            AND y.sentence_status='known'
        )
    ),
        available AS (
            SELECT r.nid, r.pattern_id,
            MAX(ls.stability)       AS stability,
            MAX(ls.last_event_time) AS last_event_time
        FROM required r
        JOIN knn_edges k2 ON k2.neighbour_id = r.nid
        JOIN learner_state ls ON ls.sentence_id = k2.sentence_id
            AND ls.learner_id = ?
            AND ls.sentence_status = 'known'
        JOIN sentences_patterns sp2 ON sp2.sentence_id = k2.sentence_id
            AND sp2.pattern_id = r.pattern_id
        GROUP BY r.nid, r.pattern_id
    )
    SELECT r.nid,
        COUNT(a.pattern_id) AS matched_count,
        COUNT(r.pattern_id) AS required_count,
        MIN(a.stability) AS newS, 
        MIN(a.last_event_time) AS newT
    FROM required r
    LEFT JOIN available a
    ON r.nid=a.nid
    AND r.pattern_id = a.pattern_id
    GROUP BY r.nid
    """

    while cascadeQueue:
        print(f"{'.'*(count%3+1)}   ",end="\r")
        sid=cascadeQueue.pop()
        queue.addKnown(sid)
        
        if sid in visited:
            continue
        #cache the neighbours of the sentence
        getNeighbours(conn,sid)
        count+=1
        visited.add(sid)
        setStatus(conn,lid,sid,session_id,learner_state_dict,"known")
        throws=conn.execute(query,(sid,lid,lid,))
        batch=[]
        for nid,matched_count,required_count,s,t in list(throws):
            isKnown = (matched_count==required_count)
            if s is None:
                s=0
                t=time.time()
            if isKnown:
                a=decay(t,s)
                stat="known"
            else:
                a=0
                stat="border"
            batch.append((lid,nid,s,t,a,stat,session_id))

            learner_state_dict[nid]={"stability": s, "last_event_activation": a, "last_event_time": t, "sentence_status":stat}
            if isKnown:
                cascadeQueue.append(nid)
        
        conn.executemany("""
            INSERT INTO learner_state (
                learner_id, sentence_id, stability, last_event_activation, 
                last_event_time, sentence_status, session_id
            ) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(learner_id, sentence_id) DO UPDATE SET
                stability = excluded.stability,
                last_event_activation = excluded.last_event_activation,
                last_event_time = excluded.last_event_time,
                sentence_status = excluded.sentence_status,
                session_id = excluded.session_id;
        """,batch
        )
    return(count)
    #cascatron2000=defaultdict(lambda:[])
    #rows=iter(conn.execute("""
    #    SELECT k.neighbour_id, sp.pattern_id FROM knn_edges k
    #    JOIN learner_state x ON x.sentence_id=k.sentence_id
    #    JOIN sentences_patterns sp ON sp.sentence_id=k.neighbour_id
    #    WHERE x.learner_id=?
    #    AND x.sentence_id=?
    #    AND NOT EXISTS (
    #        SELECT 1
    #        FROM learner_state y
    #        WHERE y.sentence_id=k.neighbour_id
    #        AND y.learner_id=?
    #        AND y.sentence_status='known'
    #    )
    #""",(lid,sid,lid,)))
    #for nid,pid in rows:
    #    cascatron2000[nid].append(pid)
    #for nid,patterns in cascatron2000.items():
    #    if not patterns: #just incase
    #        continue
    #    #all matching patterns in the known neighbours of unknown neighbours and stabilities and event times
    #    innocentCivilians=defaultdict(lambda:{"stability":0,"last_event_time":0})
    #    #find all patterns in known neighbours and their respective activation and stabilities
    #    rows=iter(conn.execute("""
    #        SELECT sp.pattern_id, x.last_event_time, x.stability FROM knn_edges k
    #        JOIN learner_state x ON x.sentence_id=k.neighbour_id
    #        JOIN sentences_patterns sp ON sp.sentence_id=k.neighbour_id
    #        WHERE k.sentence_id=?
    #        AND x.learner_id=?
    #        AND x.sentence_status='known'
    #    """,(nid,lid)))
    #    for pid,t,s in rows:
    #        s=max(s,innocentCivilians[pid]["stability"])
    #        t=max(t,innocentCivilians[pid]["last_event_time"])
    #        innocentCivilians[pid]={"stability":s,"last_event_time":t}
    #    newS=1
    #    newT=time.time()
    #    #for nid,patterns in cascatron2000.items():
    #    isKnown=True
    #    for pid in patterns:
    #        if innocentCivilians.get(pid,{}):#if the pattern is in a known neighbour
    #            newS=min(newS,innocentCivilians[pid]["stability"])
    #            newT=min(newT,innocentCivilians[pid]["last_event_time"])
    #        else:
    #            isKnown=False
    #            break #pattern is not in a known neighbour
    #    if newS==1:
    #        newS=None
    #        newT=None
    #    updateList.add((nid,newS,newT,isKnown))

    ##for nid,s,t,isKnown in updateList:
    #for nid,matched_count,required_count,s,t in throws:
    #    isKnown=matched_count==required_count
    #    if (nid,s,t,isKnown) in updateList:
    #        print("yeahboi")
    #        print(nid,s,t,isKnown)
    #    else:
    #        print("fuck")
    #    if isKnown:
    #        print("cascaded")
    #        a=decay(t,s)
    #        stat="known"
    #    else:
    #        a=0
    #        stat="border"
    #    conn.execute("""
    #        INSERT INTO learner_state (
    #            learner_id, sentence_id, stability, last_event_activation, 
    #            last_event_time, sentence_status, session_id
    #        ) 
    #        VALUES (?, ?, ?, ?, ?, ?, ?)
    #        ON CONFLICT(learner_id, sentence_id) DO UPDATE SET
    #            stability = excluded.stability,
    #            last_event_activation = excluded.last_event_activation,
    #            last_event_time = excluded.last_event_time,
    #            sentence_status = excluded.sentence_status,
    #            session_id = excluded.session_id;
    #    """,(lid,nid,s,t,a,stat,session_id,)
    #    )
    #    learner_state_dict[nid]={"stability": s, "last_event_activation": a, "last_event_time": t, "sentence_status":stat}
    #    if isKnown:
    #        cascadeKnown(conn,lid,nid,session_id,learner_state_dict)

def updateSentence(conn,lid,sid,session_id,passed,learner_state_dict,similarity=1):
        #similarity here is for neighbours

    global queue
    if conn.execute("SELECT 1 FROM learner_state WHERE sentence_id=? AND learner_id=?", (sid, lid)).fetchone():
        r,a,s,stat=retrievability(conn,lid,sid)
    else:
        r,a,s,stat=1,1,DEFAULT_STABILITY,"border"
        queue.addBorder(sid)

    delta=similarity*0.1*(1-r) #boost or penatly asymptotic toward 1
                               #if retrievability is high, does nothing(ideal)
    t=time.time()
    cascade=False
    if passed:
        a=max(1.0*similarity,a)
        s=s+REWARD*(1-s)*similarity
        if similarity==1:
            if stat != "known":
                cascade=True
                stat="known"
    else:
        s=s-s*PENALTY
        if similarity==1:
            stat="review"
            queue.addRevise(sid)

    conn.execute("""
        INSERT INTO learner_state (
            learner_id, sentence_id, stability, last_event_activation, 
            last_event_time, sentence_status, session_id
        ) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(learner_id, sentence_id) DO UPDATE SET
            stability = excluded.stability,
            last_event_activation = excluded.last_event_activation,
            last_event_time = excluded.last_event_time,
            sentence_status = excluded.sentence_status,
            session_id = excluded.session_id;
    """,(lid,sid,s,a,t,stat,session_id,)
    )
    learner_state_dict[sid]={"stability": s, "last_event_activation": a, "last_event_time":t,"sentence_status":stat}
    if cascade:
        count=cascadeKnown(conn,lid,sid,session_id,learner_state_dict)
        if count:
            print(f"{count} extra sentence{"s"*(count>1)} learnt ^_^")
    return(s,a,t,stat)

def getNeighbours(conn, sid):
    if not knn_cache.get(sid,0):
        knn_cache[sid] = conn.execute(
            "SELECT neighbour_id, similarity FROM knn_edges WHERE sentence_id = ?",
            (sid,)
        ).fetchall()
    return knn_cache[sid]
    #return conn.execute(
    #        "SELECT neighbour_id, similarity FROM knn_edges WHERE sentence_id=?",
    #        (sid,)
    #).fetchall()

def propogate(conn,lid,sid,session_id,passed,learner_state_dict):
    s,a,t,stat=updateSentence(conn,lid,sid,session_id,passed,learner_state_dict)#includes DB calls
    for nid,similarity in getNeighbours(conn,sid):
        s,a,t,stat=updateSentence(conn,lid,nid,session_id,passed,learner_state_dict,similarity)


def runSession(db_path,lid):
    conn = sqlite3.connect(db_path)
    print("loading session...")
    #load session (learner state, sentence-patterns dict, knn dict
    learner_state_dict=loadSession(conn,lid)
    print("├─loading cache...")
    cache_path=db_path.replace("data/","cache/").replace(".db",".pickle")
    loadCache(conn,cache_path)
    session_id=0
    
    default_sid=2065#你好
    global queue
    queue=Queue(conn,lid,REVIEW_RET_THRESHOLD,NEW_PER_SESSION,learner_state_dict,default_sid,knn_cache)
    grade=""
    while grade!="e":
        #sid,text=conn.execute("""
        #SELECT * FROM sentences 
        #WHERE sentence_id >= ABS(RANDOM()) % (SELECT MAX(sentence_id) FROM sentences) 
        #LIMIT 1;""").fetchone()
        sid,text=queue.next()
        print("  "+text)
        playAudio(text)
        grade=""
        while grade not in ("y","n","e"):
            print("do you understand(y/n/t/r/e-yes,no,translation,replay,exit)")
            grade=readchar.readchar().lower()
            if grade=="t":
                print("  "+' '.join([item[0] for item in pinyin(text)]))
                playAudio(text)
                print("  "+GoogleTranslator(source='zh-CN', target='en').translate(text))
            if grade=="r":
                playAudio(text)
        if grade=="e": break
        passed=(grade == "y")
        queue.answer(sid,passed)
        propogate(conn,lid,sid,session_id,passed,learner_state_dict)
        conn.commit()
    conn.close()
    #identify initial targets for reviews and new
    #figure out warmup sentences (build graph with priveledge) (greedy set cover)
    #session loop
        # next node
        # get answer
        # update weights

    #learn more option
    #dynamic session stretching out from reviews to new cards


if __name__ == "__main__":
    db_path="../data/pinru.db"
    learner_id=3 #testuser
    runSession(db_path,learner_id)
