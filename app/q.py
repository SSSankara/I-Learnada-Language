from collections import defaultdict
import time
import random
import math
import heapq

#note: this file is called q.py rather than the more profesisonal queue.py because that would conflict with the translation library

class Queue:
    def __init__(self,conn,lid,review_threshold,num_news,learner_state_dict,start,knn_cache=None):
        self.conn=conn
        self.lid=lid
        self.rt=review_threshold
        self.nn=num_news
        self.nk=0
        self.state=learner_state_dict
        self.knn_cache=knn_cache or {}
        self.known=[(1,start)]#list of all known sentences with by their retrievability
        heapq.heapify(self.known)
        self.border=[]#list of all border sentences from most useful
        heapq.heapify(self.border)
        self.revise=[]#list of all sentences gotten wrong (tuple of time to review and sentence)
        self.seenPatterns=set()
        heapq.heapify(self.revise)
        self.wronglist=set()
        self.was_new=False# if a new sentence is known, give another new sentence
        self.was_correct=False
        self.start=start
        self._load()

    def _load(self):
        from session import decay # inline import > circular import
        from session import getNeighbours # inline import > circular import
        #get all known and border
        st=self.state
        print("├─loading sentences...")
        for sid, state in st.items():
            if state.get("sentence_status") == "review":
                due=state["last_event_activation"]+300 # five minutes (300 seconds)
                heapq.heappush(self.revise, (due, sid))
                continue
            if state.get("sentence_status") == "known":
                r = decay(state["last_event_time"], state["stability"], state["last_event_activation"])
                heapq.heappush(self.known, (r, sid))
                continue
            if state.get("sentence_status") == "border":
#                for nid,sim in getNeighbours(self.conn,sid):
                k,b=0,0 
                for nid,sim in self.knn_cache[sid]:
                    if st.get(nid,0):
                        if st[nid]["sentence_status"] == "known":
                            k+=st[nid]["stability"]*sim
                        if st[nid]["sentence_status"] == "border":
                            b+=sim
                potential=(k or 1) * (b or 1)
                heapq.heappush(self.border, (-potential, sid))
                continue
        print("└─sorting sentences")

        #calculate ratio
        for item in self.known:
            if item[0]>self.rt:
                break
            self.nk+=1

    def updateKnown(self):
        from session import decay # inline import > circular import
        self.known=[]
        self.nk=0
        st=self.state
        for sid, state in st.items():
            if state.get("sentence_status") == "known":
                r = decay(state["last_event_time"], state["stability"], state["last_event_activation"])
                heapq.heappush(self.known, (r, sid))
                continue
        self.known.sort(key=lambda x: x[0])
        for item in self.known:
            if item[0]>self.rt:
                break
            self.nk+=1

    def answer(self,sid,passed):
        self.was_correct=passed
        if passed:
            for pid in conn.execute("SELECT pid FROM sentences_patterns WHERE sentence_id = ?",(sid,)):
                seenPatterns.add(pid[0])
    
    def package(self,sid):
        text=self.conn.execute("""
        SELECT text FROM sentences 
        WHERE sentence_id = ?
        LIMIT 1;""",(sid,)).fetchone()[0]
        return(sid,text)

    def bestUnknown(self):
        return self.conn.execute("""
            SELECT s.sentence_id, s.text, s.density
            FROM sentences s
            WHERE s.sentence_id NOT IN (
                SELECT sentence_id FROM learner_state WHERE learner_id = ?
            )
            ORDER BY s.density DESC
            LIMIT 1
        """, (self.lid,)).fetchone()[0]

    def next(self):
        #if self.start:
        #    out=self.package(self.start)
        #    self.start=0
        #    return(out)#first sentence,

        if not self.nn and not self.nk:
            print("session over. Leave now or continue for 5 new cards and a bunch of extra reviews")
            self.nn=5
            self.rt=1
            self.updateKnown()

        if not self.border: return(self.package(self.bestUnknown()))

        if not (self.was_new and self.was_correct): #skip all this and go straight to the next new card
            self.was_new=False

            #check review list
            if self.revise:
                if self.revise[0][0]<time.time():
                    print("relearning:")
                    sid=heapq.heappop(self.revise)[1]
                    return(self.package(sid))
            

            self.updateKnown()
            if self.nn<0:self.nn=0
            if random.choices([True, False], weights=[math.log(self.nk+1), math.log(self.nn+1)])[0]:
                #review
                print("reviewing:")
                sid=heapq.heappop(self.known)[1]
                self.nk-=1
                return(self.package(sid))
        else:
            self.nn+=1
        print(f"new sentence: ({self.nn} remaining)")
        self.nn-=1
        sid=heapq.heappop(self.border)[1]
        patterns=conn.execute("SELECT pid FROM sentences_patterns WHERE sentence_id = ?",(sid,)
        while any(neighbour[0] in self.wronglist for neighbour in self.knn_cache[sid]) or any(pid[0] in self.seenPatterns for pid in patterns):
            if not self.border: return(self.package(self.bestUnknown()))
            sid=heapq.heappop(self.border)[1]
            patterns=conn.execute("SELECT pid FROM sentences_patterns WHERE sentence_id = ?",(sid,)
        self.was_new=True
        return(self.package(sid))

    def addBorder(self,sid):
        st=self.state
        k,b=0,0 
        for nid,sim in self.knn_cache[sid]:
            if st.get(nid,0):
                if st[nid]["sentence_status"] == "known":
                    k+=st[nid]["stability"]*sim
                if st[nid]["sentence_status"] == "border":
                    b+=sim
        potential=(k or 1) * (b or 1)
        heapq.heappush(self.border, (-potential, sid))

    def addKnown(self,sid):
        from session import decay
        items=self.state[sid]
        self.nk+=1
        r = decay(items["last_event_time"], items["stability"], items["last_event_activation"])
        heapq.heappush(self.border, (r, sid))

    def addRevise(self,sid):
        self.wronglist.add(sid)
        heapq.heappush(self.revise, (time.time()+300, sid))
