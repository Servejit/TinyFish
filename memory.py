import sqlite3
from datetime import datetime

class Memory:
    def __init__(self, path="agent_memory.db"):
        self.path = path
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, task TEXT, result TEXT, created TEXT)")

    def add(self, task, result):
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO tasks(task,result,created) VALUES(?,?,?)", (task, result, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    def list_recent(self, limit=20):
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT task,result,created FROM tasks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"task": r[0], "result": r[1], "created": r[2]} for r in rows]

    def clear(self):
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM tasks")
