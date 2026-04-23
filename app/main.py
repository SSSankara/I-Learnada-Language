import sqlite3
import os
import time
from setup import login
from session import runSession

##choose database
#files = [f for f in os.listdir("../data") if f.endswith('.db')]
#print("choose database:")
#for i,file in enumerate(files):
#    print(f"{i}) {file.replace(".db","")}")
#while True:
#    try:
#        answer=int(input("enter number:"))
#        dbPath=f"../data/{files[answer]}"
#        break
#    except:
#        continue
#print(dbPath)
#conn = sqlite3.connect(dbPath)
##login/create new user
#userName=input("enter username (case sensitive):")
#with conn:
#    cur=conn.cursor()
#    while not cur.execute("SELECT learner_id FROM learners WHERE name = ?", (userName,)).fetchone():
#        print("username does not exist")
#        new=input(f"would you like to create a new user called {userName} ?(y/n)").lower()
#        if new=="n":
#            userName=input("enter username:")
#            continue
#        if new=="y":
#            cur.execute("INSERT INTO learners (name, created_at) VALUES (?, ?)", (userName, int(time.time())))
#            break
#        print("please enter y or n")
#
#print(f"Welcome, {userName}")
#learner_id = cur.execute("SELECT learner_id FROM learners WHERE name = ?", (userName,)).fetchone()


#setup
    #figure out session
    #find new and review cards
    #find involved patterns
    #append targets in score order
#review loop
conn,learner_id=login()
runSession(conn,learner_id)
#2065	        你好
#11283	6344	你跟我说说
#32622	6203	我跟你说过
#6073	6210	我不是说过
#11648	6770	我不是你妈
#6247	6485	我要的是你
#49417	6773	那是我做的
#30374	6143	好了我走了
#16815	6175	那我走了啊
#59243	6014	她不是说了













conn.close()

