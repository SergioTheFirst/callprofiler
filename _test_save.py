import sqlite3, sys, json
sys.path.insert(0, r'C:\pro\callprofiler\src')
from callprofiler.db.repository import Repository
from callprofiler.models import Analysis

db_path = r'C:\calls\data\db\callprofiler.db'
repo = Repository(db_path)
repo.init_db()

a = Analysis(priority=10, risk_score=20, summary="TEST")
a.call_type = "test"
a.parse_status = "parsed_ok"
a.schema_version = "v2"
a.model = "test"
a.prompt_version = "test"
a.raw_response = "test"

repo.save_analysis(999999, a)
print("Saved test analysis")

conn = sqlite3.connect(db_path)
row = conn.execute("SELECT * FROM analyses WHERE call_id=999999").fetchone()
print(f"Retrieved: {dict(row) if row else 'NOT FOUND'}")

conn.execute("DELETE FROM analyses WHERE call_id=999999")
conn.commit()
conn.close()
print("Cleaned up")