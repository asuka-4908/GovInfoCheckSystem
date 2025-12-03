from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
db_path = ROOT / "app" / "data" / "app.db"
migrations_dir = ROOT / "migrations"

db_path.parent.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(str(db_path))

# Simple migration runner: just sort files and execute
# In real app, we should track applied migrations in a table
sql_files = sorted(migrations_dir.glob("*.sql"))

print(f"Found {len(sql_files)} migration files.")

for sql_file in sql_files:
    print(f"Applying {sql_file.name}...")
    with open(sql_file, "r", encoding="utf-8") as f:
        sql = f.read()
    try:
        conn.executescript(sql)
    except Exception as e:
        print(f"Error applying {sql_file.name}: {e}")

conn.commit()
conn.close()
print("Database initialization complete.")
