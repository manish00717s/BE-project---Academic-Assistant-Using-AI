import sqlite3
import os
from werkzeug.security import generate_password_hash

def init_database():
    # Database path
    db_path = 'database/database/evaluation_system.db'
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute('PRAGMA foreign_keys = ON;')

    cursor.execute('''drop table if EXISTS feedback''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evaluation_id INTEGER NOT NULL,
        feedback_text TEXT,
        missing_keywords TEXT,
        corrected_by_teacher INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (evaluation_id) REFERENCES evaluation_results (id),
        FOREIGN KEY (corrected_by_teacher) REFERENCES users (id)
    )
    ''')
   
    # ===============================
    # EVALUATION RESULTS TABLE
    # (Generated after AI comparison)
    # ===============================
    cursor.execute('''drop table if EXISTS evaluation_results''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS evaluation_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_answer_id INTEGER NOT NULL,
        model_answer_id INTEGER,
        content_score FLOAT,
        concept_score FLOAT,
        grammar_score FLOAT,
        total_score FLOAT,
        evaluated_by_ai BOOLEAN DEFAULT 1,
        evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_answer_id) REFERENCES student_answers (id),
        FOREIGN KEY (model_answer_id) REFERENCES model_answers (id)
    )
    ''')
    cursor.execute('''drop table if EXISTS student_answers''')
    cursor.execute('''
  CREATE TABLE IF NOT EXISTS student_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    subject_id INTEGER NOT NULL,
    exam_title TEXT NOT NULL,
    question_id TEXT NOT NULL,
    answer_text TEXT,
    file_path TEXT,
    status TEXT DEFAULT 'Attempted',
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES student_profile (id),
    FOREIGN KEY (subject_id) REFERENCES subjects (id)
)
''')

    # ===============================
    # FEEDBACK TABLE
    # (AI or Teacher feedback on answers)
    # ===============================
    

    # ===============================
    # LOG TABLE (Optional)
    # To track admin or teacher actions
    # ===============================
 
    conn.commit()
    conn.close()
    print("✅ AI-Based Descriptive Answer Evaluation Database initialized successfully!")


if __name__ == '__main__':
    init_database()
