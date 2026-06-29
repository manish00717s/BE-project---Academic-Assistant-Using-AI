import sqlite3

def truncate_tables():
    db_path = 'database/database/evaluation_system.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("⚠️  Truncating all tables...")

    # Disable Foreign Keys
    cursor.execute("PRAGMA foreign_keys = OFF;")

    tables = [
        "feedback",
        "evaluation_results",
        "student_answers",
        "model_answers",
        "teacher_profile",
        "activity_logs",
        "users",
        "subjects",
      "student_profile",
        "classes"
    ]
    
    tables = [
        
      
        
    ]

    for table in tables:
        try:
            cursor.execute(f"DELETE FROM {table};")
            print(f"✅ Cleared table: {table}")
        except Exception as e:
            print(f"❌ Error clearing {table}: {e}")

    # Re-enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Optional: Reclaim DB file space
    

    conn.commit()
    conn.close()

    print("✅ All tables truncated successfully!")

if __name__ == "__main__":
    truncate_tables()
