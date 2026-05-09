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
import subprocess
import threading
import tempfile
import readchar

MIN_IDF=0.3
CASCADE_THRESHOLD=1 #not every pattern (there are absolutely some garbage patterns). eg most distinctive 85% of vocab weight
TAU_MAX=10*365*86400 #maximum decay constant - 10 years to decay to 1/e retrievability
TAU_MIN=86400 #1 day to decay to 1/e retrievability
REVIEW_RET_THRESHOLD=0.9
NEW_PER_SESSION=10
MIN_SENTENCE_LEN=5
REWARD=0.052  # first review at threshold: 1-day interval → ~3 days
PENALTY=0.104 # twice reward
DEFAULT_STABILITY=((-TAU_MIN/math.log(REVIEW_RET_THRESHOLD))-TAU_MIN)/(TAU_MAX-TAU_MIN)#passes review threshold in time for TAU_MIN
                                                                                       #to reach 1/e
knn_cache=defaultdict(list)#for quick sentence edge lookups
sp_dict={}                 #sentence->{pattern_id:idf}
_verbose=True
global queue

def loadPatterns(conn):
    global sp_dict
    if sp_dict: return
    print("├─loading patterns...")
    tmp=defaultdict(dict)
    for sid,pid,idf in conn.execute("""
        SELECT sp.sentence_id, sp.pattern_id, p.idf_score
        FROM sentences_patterns sp
        JOIN patterns p ON p.pattern_id=sp.pattern_id
        WHERE p.idf_score>=?
    """, (MIN_IDF,)):
        tmp[sid][pid]=idf
    sp_dict=dict(tmp)

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
    t,a,s,stat=conn.execute(
            "SELECT last_event_time, last_event_activation, stability, sentence_status FROM learner_state WHERE sentence_id=? AND learner_id=?",
            (sid,lid,)
    ).fetchone()
    if ignore_activation:
        a=1
    return(decay(t,s,a),a,s,stat)

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
    #queue.addKnown(sid)
    getNeighbours(conn,sid)
    cascadeQueue={nid for nid,_ in knn_cache.get(sid,[])}
    count=0
    now=time.time()

    while cascadeQueue:
        if _verbose:
            print(f"{'.'*(count%3+1)}   ",end="\r")
        nid=cascadeQueue.pop()
        if learner_state_dict.get(nid,{}).get("sentence_status")=="known": continue

        req=sp_dict.get(nid,{})
        best={}  # pattern_id -> (stability, sim, kn) — used only for stability
        getNeighbours(conn,nid)

        known_idf = 0

        for kn,sim in knn_cache.get(nid,[]):
            kst=learner_state_dict.get(kn)
            status=""
            if not kst: status="unknown"
            else: status=kst["sentence_status"]
            for pid in sp_dict.get(kn,{}):
                if status=="known": 
                    if pid not in best or kst["stability"]>best[pid][0]:
                        best[pid]=(kst["stability"],sim,kn)

        
        total_idf = sum(req.values())
        known_idf = sum(idf for pid, idf in req.items() if pid in best)

        isKnown = False
        if total_idf > 0:
            coverage = known_idf / total_idf
            if coverage >= (CASCADE_THRESHOLD - 1e-9):
                isKnown = True
        if best:
            unique={kn:(stab,sim) for stab,sim,kn in best.values()}
            total_sim=sum(sim for _,sim in unique.values())
            s=sum(sim*stab for stab,sim in unique.values())/total_sim if total_sim else 0
        else:
            s=DEFAULT_STABILITY
        #if isKnown: s=coverage  # high stability → won't appear in SRS queue; maintained by neighbours' reviews
        a=1 if isKnown else 0
        stat="known" if isKnown else "border"

        conn.execute("""
            INSERT INTO learner_state (
                learner_id, sentence_id, stability, last_event_activation,
                last_event_time, sentence_status, session_id
            )
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(learner_id,sentence_id) DO UPDATE SET
                stability=excluded.stability,
                last_event_activation=excluded.last_event_activation,
                last_event_time=excluded.last_event_time,
                sentence_status=excluded.sentence_status,
                session_id=excluded.session_id;
        """,(lid,nid,s,a,now,stat,session_id))
        learner_state_dict[nid]={"stability":s,"last_event_activation":a,"last_event_time":now,"sentence_status":stat}
        if isKnown:
            count+=1
            #queue.addKnown(nid)
            cascadeQueue.update(nnid for nnid,_ in knn_cache.get(nid,[])
                                if learner_state_dict.get(nnid,{}).get("sentence_status")!="known")
        # border: tracked in learner_state only — not pushed to queue.border so review phase can't serve them

    return count

def updateSentence(conn,lid,sid,session_id,passed,learner_state_dict,similarity=None,factor=None):
        #similarity here is for neighbours

    global queue
    if sid in learner_state_dict:
        state=learner_state_dict[sid]
        a,s,stat=state["last_event_activation"],state["stability"],state["sentence_status"]
        r=decay(state["last_event_time"],s,a)
    else:
        r,a,s,stat=1,1,DEFAULT_STABILITY,"border"
        queue.addBorder(sid)
    

    #just incase
    s = max(0.0, min(1.0, s))
    a = max(0.0, min(1.0, a))
    r = max(0.0, min(1.0, r))

    if factor is None: factor=r

    t=time.time()
    cascade=False
    if passed:
        if similarity is None:
            if stat != "known":
                cascade=True
                stat="known"
            similarity=1
        s=s+(1-s)*(REWARD*0.5 if stat=="review" else REWARD)*(1-factor)*similarity
        a=r+(1-r)*similarity
    else:
        if similarity is None:
            stat="review"
            queue.addRevise(sid)
            similarity=1
        s-=s*PENALTY*factor*similarity
        a=r-r*similarity*(1-REVIEW_RET_THRESHOLD)

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
        if count and _verbose:
            print(f"{count} extra sentence{"s"*(count>1)} learnt ^_^")
    return r

def getNeighbours(conn, sid):
    if not knn_cache.get(sid,0):
        knn_cache[sid] = conn.execute(
            "SELECT neighbour_id, similarity FROM knn_edges WHERE sentence_id = ?",
            (sid,)
        ).fetchall()
    return knn_cache[sid]

def propagate(conn,lid,sid,session_id,passed,learner_state_dict):
    was_new=sid not in learner_state_dict
    factor=updateSentence(conn,lid,sid,session_id,passed,learner_state_dict)
    if was_new: factor=DEFAULT_STABILITY  # r=1 for new sentences → (1-factor)=0, no propagation without this
    for nid,similarity in getNeighbours(conn,sid):
        updateSentence(conn,lid,nid,session_id,passed,learner_state_dict,similarity,factor)


def runSession(db_path,lid):
    conn = sqlite3.connect(db_path)
    print("loading session...")
    #load session (learner state, sentence-patterns dict, knn dict
    learner_state_dict=loadSession(conn,lid)
    print("├─loading cache...")
    cache_path=db_path.replace("data/","cache/").replace(".db",".pickle")
    loadCache(conn,cache_path)
    loadPatterns(conn)
    session_id=0
    
    default_sid=2065#你好
    global queue
    queue=Queue(conn,lid,REVIEW_RET_THRESHOLD,NEW_PER_SESSION,learner_state_dict,default_sid,knn_cache,MIN_SENTENCE_LEN)
    if not learner_state_dict:
        for sid in queue.selectSeeds(conn):
            queue.addBorder(sid)
    grade=""
    while grade!="e":
        sid,text=queue.next()
        if sid==-1:
            grade=""
            while grade not in ("e","c"):
                print("session over. Leave now (e) or continue (c) for 5 new cards and a bunch of extra reviews")
                print("="*20)
                grade=readchar.readchar().lower()
            if grade=="e": break
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
        propagate(conn,lid,sid,session_id,passed,learner_state_dict)
        conn.commit()
    conn.close()


if __name__ == "__main__":
    db_path="../data/pinru.db"
    learner_id=3 #testuser
    runSession(db_path,learner_id)
