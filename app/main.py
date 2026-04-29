import sqlite3
import os
import time
from setup import login
from session import runSession

db_path,learner_id=login()
runSession(db_path,learner_id)
print("goodbye")











