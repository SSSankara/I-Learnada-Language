from setup import login
from session import runSession

if __name__=="__main__":
    db_path,learner_id=login()
    runSession(db_path,learner_id)
    print("goodbye")
