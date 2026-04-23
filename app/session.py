import sqlite3
from collections import defaultdict


MIN_IDF=0.3
NEW_SENTENCE_CAP=10
TAU_MAX=10*365*86400 #maximum decay constant - 10 years to decay to 1/e retrievability
TAU_MIN=86400 #1 day to decay to 1/e retrievability


def updateDB():
    pass

def initialiseUser(conn, learner_id):
    pass

def loadSession(learner_id):
    print("loading learner history")
    rows=conn.execute("""
        SELECT sentence_id,stability,activation, last_event_time FROM learner_state WHERE learner_id = ?
    """, (learner_id,)).fetchall()
    learner_state={sid:{"stabilty": s, "activation": a, "last_event_time":t} for sid,s,a,t in rows}
    #get sentence patterns
    print("loading sentences")
    rows = conn.execute("""
        SELECT sp.sentence_id, sp.pattern_id, p.idf_score
        FROM sentences_patterns sp
        JOIN patterns p ON p.pattern_id = sp.pattern_id
        WHERE p.idf_score >= ?
    """, (MIN_IDF,)).fetchall()
    sentence_patterns = defaultdict(dict)
    for sid, pid, idf in rows:
        sentence_patterns[sid][pid] = idf
    #this was too slow, I'll do direct database calls instead
    #get knn
    #print("loading sentence links")
    #rows = conn.execute(
    #    "SELECT sentence_id, neighbour_id, similarity FROM knn_edges"
    #).fetchall()
    #knn = defaultdict(list)
    #for sid, nid, sim in rows:
    #    knn[sid].append((nid, sim))

    return (learner_state,dict(sentence_patterns))#,knn)

def decay(last_event_time,stability):
    elapsed=time.time() - last_event_time
    tau=TAU_MIN + stability * (TAU_MAX-TAU_MIN)
    return(math.exp(-elapsed/tau))

def retrievability(conn,lid,sid):
    time, stability=con.execute(
            "SELECT last_event_time, stability FROM sentence_status WHERE sentence_id=? AND learner_id=?",
            (sid,lid,)
    ).fetchall()
    return(decay(time,stability))


def getNeighbours(conn, sid):
    return conn.execute(
        "SELECT neighbour_id, similarity FROM knn_edges WHERE sentence_id = ?",
        (sid,)
    ).fetchall()





def runSession(conn,learner_id):
    print("yeah")
    print(learner_id)
    #load session (learner state, sentence-patterns dict, knn dict
    learner_state,sentence_patterns=loadSession(learner_id)
    
    #identify initial targets for reviews and new
    #figure out warmup sentences (build graph with priveledge) (greedy set cover)
    #session loop
        # next node
        # get answer
        # update weights

    #learn more option
    #dynamic session stretching out from reviews to new cards


if __name__ == "__main__":
    conn = sqlite3.connect("../data/pinru.db")
    learner_id=3 #testuser
    runSession(conn,learner_id)
