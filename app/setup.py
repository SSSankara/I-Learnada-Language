import time
import os
import sqlite3

def login():
    files = [f for f in os.listdir("../data") if f.endswith('.db')]
    print("choose database:")
    for i,file in enumerate(files):
        print(f"{i}) {file.replace(".db","")}")
    while True:
        try:
            answer=int(input("enter number:"))
            dbPath=f"../data/{files[answer]}"
            break
        except:
            continue
    print(dbPath)
    conn = sqlite3.connect(dbPath)
    #login/create new user
    userName=input("enter username (case sensitive):")
    with conn:
        cur=conn.cursor()
        while not cur.execute("SELECT learner_id FROM learners WHERE name = ?", (userName,)).fetchone():
            print("username does not exist")
            new=input(f"would you like to create a new user called {userName} ?(y/n)").lower()
            if new=="n":
                userName=input("enter username:")
                continue
            if new=="y":
                cur.execute("INSERT INTO learners (name, created_at) VALUES (?, ?)", (userName, int(time.time())))
                break
            print("please enter y or n")
    
    learner_id = cur.execute("SELECT learner_id FROM learners WHERE name = ?", (userName,)).fetchone()[0]
    print(f"Welcome, {userName}! ({learner_id})")
    print("="*20)
    return(dbPath,learner_id)

