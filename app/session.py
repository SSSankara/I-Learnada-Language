import sqlite3
from collections import defaultdict
import time
import math

MIN_IDF=0.3
NEW_SENTENCE_CAP=10
TAU_MAX=10*365*86400 #maximum decay constant - 10 years to decay to 1/e retrievability
TAU_MIN=86400 #1 day to decay to 1/e retrievability
REWARD=0.05 #of the distance between stability and 1
PENALTY=0.3 #loss to the stability afterwards, these are subject to change

def updateDB():
    pass

def initialiseUser(conn, learner_id):
    pass

def loadSession(learner_id):
    print("loading learner history")
    rows=conn.execute("""
        SELECT sentence_id,stability,activation, last_event_time, sentence_status FROM learner_state WHERE learner_id = ?
    """, (learner_id,)).fetchall()
    learner_state_dict={sid:{"stabilty": s, "activation": a, "last_event_time":t, "sentence_status":stat} for sid,s,a,t,stat in rows}

    #this was fast, but unecessary in the end
    #get sentence patterns
    #print("loading sentences")
    #rows = conn.execute("""
    #    SELECT sp.sentence_id, sp.pattern_id, p.idf_score
    #    FROM sentences_patterns sp
    #    JOIN patterns p ON p.pattern_id = sp.pattern_id
    #    WHERE p.idf_score >= ?
    #""", (MIN_IDF,)).fetchall()
    #sentences_patterns = defaultdict(dict)
    #for sid, pid, idf in rows:
    #    sentences_patterns[sid][pid] = idf

    #this was too slow, I'll do direct database calls instead
    #get knn
    #print("loading sentence links")
    #rows = conn.execute(
    #    "SELECT sentence_id, neighbour_id, similarity FROM knn_edges"
    #).fetchall()
    #knn = defaultdict(list)
    #for sid, nid, sim in rows:
    #    knn[sid].append((nid, sim))

    return (learner_state_dict)#dict(sentences_patterns))#,knn)

def decay(last_event_time,stability,last_event_activation=1):
    elapsed=time.time() - last_event_time
    tau=TAU_MIN + stability * (TAU_MAX-TAU_MIN)
    return(last_event_activation*math.exp(-elapsed/tau))

def retrievability(conn,lid,sid):
    """It's called retrievability but also returns activation, stability, time, and status"""
    time, activation, stability,status=conn.execute(
            "SELECT last_event_time, last_event_activation, stability, sentence_status FROM learner_state WHERE sentence_id=? AND learner_id=?",
            (sid,lid,)
    ).fetchone()
    return(decay(time,stability,activation),activation,stability,status)

def setStatus(conn,lid,sid,session_id,learner_state_dict,status):
    learner_state_dict[sid]["status"]=status
    conn.execute("""
        UPDATE learner_state SET
        sentence_status=?,
        session_id=?
        WHERE learner_id=? AND sentence_id=?
    """,("known",session_id,lid,sid,)
    )

def cascadeKnown(conn,lid,sid,session_id,learner_state_dict):
    setStatus(conn,lid,sid,session_id,learner_state_dict,"known")
    updateList=set()
    #all unknown neighbours and their patterns
    cascatron2000=defaultdict(lambda:[])





    rows=iter(conn.execute("""
        SELECT k.neighbour_id, sp.pattern_id FROM knn_edges k
        JOIN learner_state x ON x.sentence_id=k.sentence_id
        JOIN sentences_patterns sp ON sp.sentence_id=k.neighbour_id
        WHERE x.learner_id=?
        AND x.sentence_id=?
        AND NOT EXISTS (
            SELECT 1
            FROM learner_state y
            WHERE y.sentence_id=k.neighbour_id
            AND y.learner_id=?
            AND y.sentence_status='known'
        )
    """,(lid,sid,lid,)))
    for nid,pid in rows:
        cascatron2000[nid].append(pid)
    for nid,patterns in cascatron2000.items():
        if not patterns: #just incase
            continue
        #all matching patterns in the known neighbours of unknown neighbours and stabilities and event times
        innocentCivilians=defaultdict(lambda:{"stability":0,"last_event_time":0})
        #find all patterns in known neighbours and their respective activation and stabilities
        rows=iter(conn.execute("""
            SELECT sp.pattern_id, x.last_event_time, x.stability FROM knn_edges k
            JOIN learner_state x ON x.sentence_id=k.neighbour_id
            JOIN sentences_patterns sp ON sp.sentence_id=k.neighbour_id
            WHERE k.sentence_id=?
            AND x.learner_id=?
            AND x.sentence_status='known'
        """,(nid,lid)))
        for pid,t,s in rows:
            s=max(s,innocentCivilians[pid]["stability"])
            t=max(t,innocentCivilians[pid]["last_event_time"])
            innocentCivilians[pid]={"stability":s,"last_event_time":t}
        newS=1
        newT=time.time()
        #for nid,patterns in cascatron2000.items():
        isKnown=True
        for pid in patterns:
            if innocentCivilians.get(pid,{}):#if the pattern is in a known neighbour
                newS=min(newS,innocentCivilians[pid]["stability"])
                newT=min(newT,innocentCivilians[pid]["last_event_time"])
            else:
                isKnown=False
                break #pattern is not in a known neighbour
        if isKnown:
            updateList.add((nid,newS,newT,isKnown))

    for nid,s,t,isKnown in updateList:
        if isKnown:
            print("cascaded")
            a=decay(t,s)
            stat="known"
        else:
            a=0
            stat="border"
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
        """,(lid,nid,s,t,a,stat,session_id,)
        )
        learner_state_dict[nid]={"stabilty": s, "last_event_activation": a, "last_event_time": t, "sentence_status":stat}
        cascadeKnown(conn,lid,nid,session_id,learner_state_dict)

def updateSentence(conn,lid,sid,session_id,passed,learner_state_dict,similarity=1):
        #similarity here is for neighbours

    if conn.execute("SELECT 1 FROM learner_state WHERE sentence_id=? AND learner_id=?", (sid, lid)).fetchone():
        r,a,s,stat=retrievability(conn,lid,sid)
    else:
        r,a,s,stat=0,0,0,"border"

    delta=similarity*0.1*(1-r) #boost or penatly asymptotic toward 1
                               #if retrievability is high, does nothing(ideal)
    t=time.time()
    cascade=False
    if passed:
        a=min(1.0,r+delta)
        s=s+REWARD*(1-s)*similarity
        if similarity==1:
            if stat != "known":
                cascade=True
                stat="known"
    else:
        a=max(0.0,r-delta)
        s=s-s*PENALTY
        if similarity==1:
            stat="review"

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
    learner_state_dict[sid]={"stabilty": s, "activation": a, "last_event_time":t,"sentence_status":stat}
    if cascade:
        cascadeKnown(conn,lid,sid,session_id,learner_state_dict)        
    return(s,a,t,stat)

def getNeighbours(conn, sid):
    return conn.execute(
            "SELECT neighbour_id, similarity FROM knn_edges WHERE sentence_id=?",
            (sid,)
    ).fetchall()

def propogate(conn,lid,sid,session_id,passed,learner_state_dict):
    s,a,t,stat=updateSentence(conn,lid,sid,session_id,passed,learner_state_dict)#includes DB calls
    for nid,similarity in getNeighbours(conn,sid):
        s,a,t,stat=updateSentence(conn,lid,nid,session_id,passed,learner_state_dict,similarity)


def runSession(conn,learner_id):
    print("yeah")
    print(learner_id)
    #load session (learner state, sentence-patterns dict, knn dict
    learner_state_dict=loadSession(learner_id)
    session_id=0
    
    grade=""
    while grade!="s":
        sid,text=conn.execute("""
        SELECT * FROM sentences 
        WHERE sentence_id >= ABS(RANDOM()) % (SELECT MAX(sentence_id) FROM sentences) 
        LIMIT 1;""").fetchone()
        print(text)
        grade=""
        while grade not in ("y","n","s"):
            grade=input("do you understand(y/n/s-yes,no,stop)").lower()
        passed=(grade == "y")
        propogate(conn,learner_id,sid,session_id,passed,learner_state_dict)
        conn.commit()
    #identify initial targets for reviews and new
    #figure out warmup sentences (build graph with priveledge) (greedy set cover)
    #session loop
        # next node
        # get answer
        # update weights

    #learn more option
    #dynamic session stretching out from reviews to new cards


if __name__ == "__main__":
    conn = sqlite3.connect("../data/pin2.db")
    learner_id=3 #testuser
    runSession(conn,learner_id)
    conn.close()
