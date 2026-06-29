import sqlite3
import os
from werkzeug.security import generate_password_hash

def init_database():
    # Database path
    db_path = 'database/evaluation_system.db'
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute('PRAGMA foreign_keys = ON;')

    # ===============================
    # USERS TABLE (Common for all roles)
    # ===============================
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT CHECK(role IN ('Admin', 'Teacher', 'Student')) NOT NULL,
        status TEXT DEFAULT 'Active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # ===============================
    # CLASS TABLE
    # ===============================
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_name TEXT UNIQUE NOT NULL,
        description TEXT
    )
    ''')

    # ===============================
    # SUBJECT TABLE
    # ===============================
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_name TEXT NOT NULL,
        description TEXT
    )
    ''')

    # ===============================
    # TEACHER PROFILE
    # ===============================
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS teacher_profile (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        qualification TEXT,
        experience_years INTEGER,
        assigned_class_id INTEGER,
        assigned_subject_id INTEGER,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (assigned_class_id) REFERENCES classes (id),
        FOREIGN KEY (assigned_subject_id) REFERENCES subjects (id)
    )
    ''')

    # ===============================
    # STUDENT PROFILE
    # ===============================
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS student_profile (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        roll_no TEXT,
        class_id INTEGER,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (class_id) REFERENCES classes (id)
    )
    ''')

    # ===============================
    # SYLLABUS TABLE
    # ===============================
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS syllabus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_id INTEGER NOT NULL,
        class_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        pdf_path TEXT NOT NULL,
        extracted_text TEXT,
        uploaded_by INTEGER NOT NULL,
        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'Active',
        FOREIGN KEY (subject_id) REFERENCES subjects (id),
        FOREIGN KEY (class_id) REFERENCES classes (id),
        FOREIGN KEY (uploaded_by) REFERENCES users (id)
    )
    ''')

    # ===============================
    # EXAMS TABLE (Enhanced with difficulty_level)
    # ===============================
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS exams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_title TEXT NOT NULL,
        subject_id INTEGER NOT NULL,
        class_id INTEGER NOT NULL,
        syllabus_id INTEGER,
        created_by INTEGER NOT NULL,
        difficulty_level TEXT DEFAULT 'Medium' CHECK(difficulty_level IN ('Easy', 'Medium', 'Hard')),
        total_marks INTEGER DEFAULT 0,
        duration_minutes INTEGER DEFAULT 60,
        start_date DATETIME,
        end_date DATETIME,
        status TEXT DEFAULT 'Draft' CHECK(status IN ('Draft', 'In Review', 'Approved', 'Published', 'Completed', 'Archived')),
        ai_generated BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        approved_at TIMESTAMP,
        FOREIGN KEY (subject_id) REFERENCES subjects (id),
        FOREIGN KEY (class_id) REFERENCES classes (id),
        FOREIGN KEY (syllabus_id) REFERENCES syllabus (id),
        FOREIGN KEY (created_by) REFERENCES users (id)
    )
    ''')

    # ===============================
    # AI GENERATION HISTORY TABLE (NEW)
    # ===============================
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ai_generation_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id INTEGER NOT NULL,
        prompt_used TEXT NOT NULL,
        questions_generated INTEGER DEFAULT 0,
        difficulty_level TEXT,
        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        generated_by INTEGER NOT NULL,
        api_model TEXT DEFAULT 'gemini-2.0-flash',
        FOREIGN KEY (exam_id) REFERENCES exams (id) ON DELETE CASCADE,
        FOREIGN KEY (generated_by) REFERENCES users (id)
    )
    ''')

    # ===============================
    # MODEL ANSWERS TABLE (Updated with difficulty_level)
    # ===============================
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS model_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id INTEGER NOT NULL,
        question_id TEXT NOT NULL,
        question_text TEXT NOT NULL,
        question_type TEXT DEFAULT 'Subjective',
        difficulty_level TEXT DEFAULT 'Medium',
        model_answer_text TEXT,
        option_a TEXT,
        option_b TEXT,
        option_c TEXT,
        option_d TEXT,
        correct_option TEXT,
        marks INTEGER DEFAULT 0,
        ai_generated BOOLEAN DEFAULT 0,
        is_approved BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (exam_id) REFERENCES exams (id) ON DELETE CASCADE
    )
    ''')

    # ===============================
    # STUDENT ANSWERS TABLE
    # ===============================
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS student_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        exam_id INTEGER NOT NULL,
        question_id TEXT NOT NULL,
        answer_text TEXT,
        selected_option TEXT,
        file_path TEXT,
        status TEXT DEFAULT 'Attempted',
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES student_profile (id),
        FOREIGN KEY (exam_id) REFERENCES exams (id)
    )
    ''')

    # ===============================
    # EVALUATION RESULTS TABLE
    # ===============================
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

    # ===============================
    # FEEDBACK TABLE
    # ===============================
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
    # ACTIVITY LOGS TABLE
    # ===============================
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')


     # Add this table in init_database() function

# ===============================
# EXAM FEEDBACK TABLE
# ===============================
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS exam_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        exam_id INTEGER NOT NULL,
        rating INTEGER CHECK(rating >= 1 AND rating <= 5),
        difficulty_rating INTEGER CHECK(difficulty_rating >= 1 AND difficulty_rating <= 5),
        feedback_text TEXT NOT NULL,
        suggestions TEXT,
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES student_profile (id) ON DELETE CASCADE,
        FOREIGN KEY (exam_id) REFERENCES exams (id) ON DELETE CASCADE,
        UNIQUE(student_id, exam_id)
    )
    ''')
    # Create default admin
    admin_email = "admin@aievaluation.com"
    admin_name = "System Admin"
    admin_password = generate_password_hash("admin123")

    cursor.execute("SELECT * FROM users WHERE role = 'Admin'")
    admin_exists = cursor.fetchone()

    if not admin_exists:
        cursor.execute('''
            INSERT INTO users (full_name, email, password_hash, role)
            VALUES (?, ?, ?, 'Admin')
        ''', (admin_name, admin_email, admin_password))
        print("✅ Default Admin created (email: admin@aievaluation.com, password: admin123)")
    else:
        print("ℹ️ Admin already exists.")
    
    conn.commit()
    conn.close()
    print("✅ AI-Based Descriptive Answer Evaluation Database initialized successfully!")
    print("✅ Added support for AI question generation with difficulty levels!")


if __name__ == '__main__':
    init_database()