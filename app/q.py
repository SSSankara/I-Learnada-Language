from collections import defaultdict
import time
import random
import math
import heapq

MIN_LEN=5
REVISE_DUE_TIME=300 #5 minutes until reshowing

#note: this file is called q.py rather than the more profesisonal queue.py because that would conflict with the translation library

class Queue:
    def __init__(self,conn,lid,review_threshold,num_news,learner_state_dict,start,knn_cache=None,min_len=MIN_LEN,verbose=True):
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
        self._known_dirty=False  # skip updateKnown rebuild unless known set changed
        self._verbose=verbose
        self._load()

    def _load(self):
        from session import decay # inline import > circular import
        from session import getNeighbours # inline import > circular import
        #get all known and border
        st=self.state
        print("├─loading sentences...")
        for sid, state in st.items():
            if state.get("sentence_status") == "review":
                due=state["last_event_activation"]+REVISE_DUE_TIME # five minutes (300 seconds)
                heapq.heappush(self.revise, (due, sid))
                continue
            if state.get("sentence_status") == "known":
                r = decay(state["last_event_time"], state["stability"], state["last_event_activation"])
                heapq.heappush(self.known, (r, sid))
                continue
            if state.get("sentence_status") == "border":
                from session import sp_dict
                k=0
                for nid,sim in self.knn_cache.get(sid,[]):
                    nst=st.get(nid,0)
                    if nst and nst["sentence_status"]=="known":
                        k+=nst["stability"]*sim
                density=sum(sp_dict.get(sid,{}).values()) or 1
                heapq.heappush(self.border, (-(k*density), sid))
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
        if not self._known_dirty: return
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
        self._known_dirty=False

    def answer(self,sid,passed):
        self.was_correct=passed
        from session import sp_dict
        if passed:
            for pid in sp_dict.get(sid,{}):
                self.seenPatterns.add(pid)
    
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
            SELECT s.sentence_id
            FROM sentences s
            WHERE s.sentence_id NOT IN (
                SELECT sentence_id FROM learner_state WHERE learner_id = ? AND sentence_status != 'border'
            )
            AND length(s.text) >= ?
            ORDER BY s.density DESC
            LIMIT 1
        """, (self.lid,self.min_len)).fetchone()
        return row[0] if row else None

    def selectSeeds(self, conn, n=None, max_idf=8.0):
        if n is None: n=self.nn
        rows=conn.execute("""
            SELECT s.sentence_id FROM sentences s
            JOIN (SELECT sp.sentence_id, MAX(p.idf_score) as mx
                  FROM sentences_patterns sp
                  JOIN patterns p ON p.pattern_id=sp.pattern_id
                  GROUP BY sp.sentence_id) pi ON pi.sentence_id=s.sentence_id
            WHERE pi.mx<=? AND length(s.text)>=?
        """, (max_idf, self.min_len)).fetchall()
        # sort by KNN degree so seeds are central in their graph neighbourhoods
        candidates=sorted([sid for (sid,) in rows],
                          key=lambda s: len(self.knn_cache.get(s,[])), reverse=True)
        seeds,excluded=[],set()
        for sid in candidates:
            if sid in excluded: continue
            seeds.append(sid)
            for nid,_ in self.knn_cache.get(sid,[]): excluded.add(nid)
            if len(seeds)>=n: break
        return seeds

    def finishSession(self):
        if self.revise:
            if self._verbose:
                print("relearning:")
            sid=heapq.heappop(self.revise)[1]
            return(self.package(sid))
        self.nn=5
        self.rt=1
        self.updateKnown()
    def next(self):
        if self._verbose:
            print(f"seenPatterns: {len(self.seenPatterns)}")
        #if self.start:
        #    out=self.package(self.start)
        #    self.start=0
        #    return(out)#first sentence,

        if self.nn<=0 and self.nk<=0:
            result=self.finishSession()
            if result: return result
            return (-1, None)

        # lazy queue clean for cascaded cards
        from session import decay
        while self.known:
            _, peek_sid = self.known[0]
            st = self.state.get(peek_sid)
            if st and st.get("sentence_status") == "known":
                # Calculate its actual retrievability right now
                current_r = decay(st["last_event_time"], st["stability"], st["last_event_activation"])
                if current_r >= self.rt:
                    # Propagation boosted this sentence
                    heapq.heappop(self.known)
                    self.nk -= 1
                    continue
            break # If we get here, the sentence is genuinely due


        if not (self.was_new and self.was_correct): #skip all this and go straight to the next new card
            self.was_new=False

            #check review list
            if self.revise:
                if self.revise[0][0]<time.time():
                    if self._verbose:
                        print("relearning:")
                    sid=heapq.heappop(self.revise)[1]
                    return(self.package(sid))
            

            self.updateKnown()
            if self.nn<0:self.nn=0
            if self.nk<0:self.nk=0
            #print(f"nk:{self.nk},nn:{self.nn}")
            if self.nk==0:
                if self.nn<=0:
                    if self.known:
                        if self._verbose:
                            print("reviewing:")
                        sid=heapq.heappop(self.known)[1]
                        return(self.package(sid))
                    result=self.finishSession()
                    if result: return result
                    return (-1, None)
                do_review=False
            elif self.nn==0:
                do_review=True
            else:
                do_review=random.choices([True,False],weights=[math.log(self.nk+1),math.log(self.nn+1)])[0]
            if do_review:
                if self._verbose:
                    print("reviewing:")
                sid=heapq.heappop(self.known)[1]
                self.nk-=1
                return(self.package(sid))
        else:
            self.nn+=1
        self.was_new=True
        self.nn-=1
        if self._verbose:
            print(f"new sentence: ({self.nn} remaining)")
        if not self.border:
            bid=self.bestUnknown()
            while bid is None and self.min_len>1:
                self.min_len-=1
                bid=self.bestUnknown()
            if bid is None: return (-1, None)
            return self.package(bid)
        from session import sp_dict
        sid=heapq.heappop(self.border)[1]
        #patterns=list(sp_dict.get(sid,{}).keys())
        #while self._textlen(sid)<self.min_len or any(neighbour[0] in self.wronglist for neighbour in self.knn_cache.get(sid,[])) or all(pid in self.seenPatterns for pid in patterns):
        #    if not self.border:
        #        bid=self.bestUnknown()
        #        while bid is None and self.min_len>1:
        #            self.min_len-=1
        #            bid=self.bestUnknown()
        #        if bid is None: return (-1, None)
        #        return self.package(bid)
        #    sid=heapq.heappop(self.border)[1]
        #    patterns=list(sp_dict.get(sid,{}).keys())
        return(self.package(sid))

    def addBorder(self,sid):
        from session import sp_dict
        st=self.state
        k,b,u=0,0,0
        for nid,sim in self.knn_cache.get(sid,[]):
            nst=st.get(nid,0)
            if nst:
                if nst["sentence_status"]=="known":
                    k+=sim
                elif nst["sentence_status"]=="border":
                    b+=sim
                else:
                    u+=sim
        #density=sum(sp_dict.get(sid,{}).values()) or 1
        score=(k or 0.1)*(b or 0.1)*(u or 0.1)
        heapq.heappush(self.border, (-score, sid))

    def addKnown(self,sid):
        from session import decay, sp_dict
        items=self.state[sid]
        self._known_dirty=True
        r = decay(items["last_event_time"], items["stability"], items["last_event_activation"])
        if r < self.rt: self.nk+=1
        heapq.heappush(self.known, (r, sid))
        for pid in sp_dict.get(sid,{}):
            self.seenPatterns.add(pid)

    def addRevise(self,sid):
        self.wronglist.add(sid)
        heapq.heappush(self.revise, (time.time()+REVISE_DUE_TIME, sid))
