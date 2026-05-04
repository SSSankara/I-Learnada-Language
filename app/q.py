from collections import defaultdict
import time
import random
import math
import heapq

MIN_LEN=5

#note: this file is called q.py rather than the more profesisonal queue.py because that would conflict with the translation library

class Queue:
    def __init__(self,conn,lid,review_threshold,num_news,learner_state_dict,start,knn_cache=None,min_len=MIN_LEN):
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
        self.min_len=min_len
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
                for nid,sim in self.knn_cache.get(sid,[]):
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
        self.known.sort(key=lambda x: x[0])
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
        for pid in self.conn.execute("SELECT pattern_id FROM sentences_patterns WHERE sentence_id = ?",(sid,)):
            self.seenPatterns.add(pid[0])
    
    def package(self,sid):
        text=self.conn.execute("""
        SELECT text FROM sentences 
        WHERE sentence_id = ?
        LIMIT 1;""",(sid,)).fetchone()[0]
        return(sid,text)

    def _textlen(self,sid):
        return self.conn.execute("SELECT length(text) FROM sentences WHERE sentence_id=?",(sid,)).fetchone()[0]

    def bestUnknown(self):
        row=self.conn.execute("""
            SELECT s.sentence_id, s.text, s.density
            FROM sentences s
            WHERE s.sentence_id NOT IN (
                SELECT sentence_id FROM learner_state WHERE learner_id = ?
            )
            AND length(s.text) >= ?
            ORDER BY s.density DESC
            LIMIT 1
        """, (self.lid,self.min_len)).fetchone()
        return row[0] if row else None

    def finishSession(self):
        if self.revise:
            print("relearning:")
            sid=heapq.heappop(self.revise)[1]
            return(self.package(sid))
        print("session over. Leave now or continue for 5 new cards and a bunch of extra reviews")
        print("="*20)
        self.nn=5
        self.rt=1
        self.updateKnown()
    def next(self):
        print(f"seenPatterns: {len(self.seenPatterns)}")
        #if self.start:
        #    out=self.package(self.start)
        #    self.start=0
        #    return(out)#first sentence,

        if self.nn<=0 and self.nk<=0:
            result=self.finishSession()
            if result: return result

        if not self.border:
            bid=self.bestUnknown()
            while bid is None and self.min_len>1:
                self.min_len-=1
                bid=self.bestUnknown()
            if bid is None: return None
            return self.package(bid)

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
            if self.nk<0:self.nk=0
            print(f"nk:{self.nk},nn:{self.nn}")
            if self.nk==0:
                do_review=False
            elif self.nn==0:
                do_review=True
            else:
                do_review=random.choices([True,False],weights=[math.log(self.nk+1),math.log(self.nn+1)])[0]
            if do_review:
                #review
                print("reviewing:")
                sid=heapq.heappop(self.known)[1]
                self.nk-=1
                return(self.package(sid))
        else:
            self.nn+=1
        self.was_new=True
        self.nn-=1
        print(f"new sentence: ({self.nn} remaining)")
        sid=heapq.heappop(self.border)[1]
        patterns=[pid[0] for pid in self.conn.execute("SELECT pattern_id FROM sentences_patterns WHERE sentence_id = ?",(sid,))]
        while self._textlen(sid)<self.min_len or any(neighbour[0] in self.wronglist for neighbour in self.knn_cache.get(sid,[])) or all(pid in self.seenPatterns for pid in patterns):
            if not self.border:
                bid=self.bestUnknown()
                while bid is None and self.min_len>1:
                    self.min_len-=1
                    bid=self.bestUnknown()
                if bid is None: return None
                return self.package(bid)
            sid=heapq.heappop(self.border)[1]
            patterns=[pid[0] for pid in self.conn.execute("SELECT pattern_id FROM sentences_patterns WHERE sentence_id = ?",(sid,))]
        return(self.package(sid))

    def addBorder(self,sid):
        st=self.state
        k,b=0,0
        for nid,sim in self.knn_cache.get(sid,[]):
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
        heapq.heappush(self.known, (r, sid))

    def addRevise(self,sid):
        self.wronglist.add(sid)
        heapq.heappush(self.revise, (time.time()+300, sid))
