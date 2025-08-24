# test_db.py
from lawfirm_functions import get_db_connection

def test_db_connection():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM practice_areas;")
        count = cur.fetchone()[0]
        print(f"Database connection successful! Found {count} practice areas.")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Database connection failed: {e}")

if __name__ == "__main__":
    test_db_connection()