from datetime import datetime
import time
import requests
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
from functools import wraps
import os
import pandas as pd
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
import PyPDF2
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import re
from ai_question_generator import question_generator
from pdf_text_extractor import pdf_to_text, extract_text_from_pdf
from dotenv import load_dotenv
load_dotenv()



# Load models once at startup



# Load models once at startup
# nlp = spacy.load('en_core_web_sm')
# sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
# grammar_tool = language_tool_python.LanguageTool('en-US')

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback-dev-secret-key-change-in-production')

# Base directory (absolute path to project root)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Database path (absolute)
DB_PATH = os.path.join(BASE_DIR, os.getenv('DB_PATH', 'database/database/evaluation_system.db'))

# Upload configuration (absolute paths)
SYLLABUS_FOLDER = os.path.join(BASE_DIR, 'uploads', 'syllabus')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads', 'answer_sheets')
STUDENT_ANSWERS_FOLDER = os.path.join(BASE_DIR, 'uploads', 'student_answers')
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create all upload folders if not exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SYLLABUS_FOLDER, exist_ok=True)
os.makedirs(STUDENT_ANSWERS_FOLDER, exist_ok=True)

# ==================== Helper Functions ====================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==================== Database Helper ====================
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON;')
    conn.execute('PRAGMA journal_mode=WAL;')
    return conn

# ==================== Login Required Decorator ====================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'Admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'Teacher':
            flash('Teacher access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'Student':
            flash('Student access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== AUTH ROUTES ====================
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            session['email'] = user['email']
            flash(f'Welcome back, {user["full_name"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

# ==================== DASHBOARD ====================
@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    
    if session['role'] == 'Admin':
        # Admin Dashboard
        total_users = conn.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
        total_students = conn.execute('SELECT COUNT(*) as count FROM users WHERE role = "Student"').fetchone()['count']
        total_teachers = conn.execute('SELECT COUNT(*) as count FROM users WHERE role = "Teacher"').fetchone()['count']
        total_classes = conn.execute('SELECT COUNT(*) as count FROM classes').fetchone()['count']
        total_subjects = conn.execute('SELECT COUNT(*) as count FROM subjects').fetchone()['count']
        total_evaluations = conn.execute('SELECT COUNT(*) as count FROM evaluation_results').fetchone()['count']
        
        recent_activities = conn.execute('''
            SELECT al.*, u.full_name 
            FROM activity_logs al
            LEFT JOIN users u ON al.user_id = u.id
            ORDER BY al.timestamp DESC
            LIMIT 10
        ''').fetchall()
        
        stats = {
            'total_users': total_users,
            'total_students': total_students,
            'total_teachers': total_teachers,
            'total_classes': total_classes,
            'total_subjects': total_subjects,
            'total_evaluations': total_evaluations
        }
        conn.close()
        return render_template('dashboard.html', stats=stats, activities=recent_activities)
    
    elif session['role'] == 'Student':
        # Student Dashboard
        student_profile = conn.execute('''
            SELECT sp.*, c.class_name 
            FROM student_profile sp
            LEFT JOIN classes c ON sp.class_id = c.id
            WHERE sp.user_id = ?
        ''', (session['user_id'],)).fetchone()
        
        total_submissions = conn.execute('''
            SELECT COUNT(*) as count 
            FROM student_answers sa
            JOIN student_profile sp ON sa.student_id = sp.id
            WHERE sp.user_id = ?
        ''', (session['user_id'],)).fetchone()['count']
        
        total_evaluated = conn.execute('''
            SELECT COUNT(*) as count 
            FROM evaluation_results er
            JOIN student_answers sa ON er.student_answer_id = sa.id
            JOIN student_profile sp ON sa.student_id = sp.id
            WHERE sp.user_id = ?
        ''', (session['user_id'],)).fetchone()['count']
        
        avg_score = conn.execute('''
            SELECT AVG(er.total_score) as avg_score 
            FROM evaluation_results er
            JOIN student_answers sa ON er.student_answer_id = sa.id
            JOIN student_profile sp ON sa.student_id = sp.id
            WHERE sp.user_id = ?
        ''', (session['user_id'],)).fetchone()['avg_score']

        recent_submissions = []
        
        # recent_submissions = conn.execute('''
        #     SELECT sa.*, s.subject_name, er.total_score, er.evaluated_at
        #     FROM student_answers sa
        #     JOIN student_profile sp ON sa.student_id = sp.id
        #     JOIN subjects s ON sa.subject_id = s.id
        #     LEFT JOIN evaluation_results er ON sa.id = er.student_answer_id
        #     WHERE sp.user_id = ?
        #     ORDER BY sa.uploaded_at DESC
        #     LIMIT 10
        # ''', (session['user_id'],)).fetchall()
      

        available_exams=[]
    #     available_exams = conn.execute('''
    #         SELECT DISTINCT
    #         ma.exam_title,
    #         ma.subject_id,
    #         ma.class_id,
    #         s.subject_name,
    #         c.class_name,
    #         COUNT(ma.id) as total_questions,
    #         SUM(ma.marks) as total_marks,
    #         MAX(ma.created_at) as created_at
    #     FROM model_answers ma
    #     JOIN subjects s ON ma.subject_id = s.id
    #     JOIN classes c ON ma.class_id = c.id
    #     WHERE ma.class_id = ?
    #     AND ma.exam_title NOT IN (
    #         SELECT DISTINCT exam_title 
    #         FROM student_answers 
    #         WHERE student_id = ?
    #     )
    #     GROUP BY ma.exam_title, ma.subject_id, ma.class_id
    #     ORDER BY ma.created_at DESC
    # ''', (student_profile['class_id'], student_profile['id'])).fetchall()
    
    # Get submitted exams
        submitted_exams=[]
        # submitted_exams = conn.execute('''
        #     SELECT DISTINCT
        #         ma.exam_title,
        #         s.subject_name,
        #         c.class_name,
        #         COUNT(sa.id) as attempted_questions,
        #         sa.uploaded_at,
        #         (SELECT COUNT(*) FROM evaluation_results er 
        #         JOIN student_answers sa2 ON er.student_answer_id = sa2.id
        #         WHERE sa2.student_id = sa.student_id AND ma.exam_title = ma.exam_title) as evaluated_count
        #     FROM student_answers sa
        #     JOIN model_answers ma ON ma.exam_title = ma.exam_title
        #     JOIN subjects s ON ma.subject_id = s.id
        #     JOIN classes c ON ma.class_id = c.id
        #     WHERE sa.student_id = ?
        #     GROUP BY ma.exam_title
        #     ORDER BY sa.uploaded_at DESC
        # ''', (student_profile['id'],)).fetchall()
    
        stats = {
            'total_submissions': total_submissions,
            'total_evaluated': total_evaluated,
            'avg_score': round(avg_score, 2) if avg_score else 0,
            'pending': total_submissions - total_evaluated
        }
        
        conn.close()
        return render_template('student/dashboard.html', stats=stats, 
                             student_profile=student_profile, 
                             recent_submissions=recent_submissions,available_exams=available_exams,
                         submitted_exams=submitted_exams)
    

    elif session['role'] == 'Teacher':
        # Teacher statistics
        teacher_id = session['user_id']
        
        stats = {
            'total_exams': conn.execute('SELECT COUNT(*) as count FROM exams WHERE created_by=?', 
                                    (teacher_id,)).fetchone()['count'],
            'total_syllabus': conn.execute('SELECT COUNT(*) as count FROM syllabus WHERE uploaded_by=?', 
                                        (teacher_id,)).fetchone()['count'],
            'draft_exams': conn.execute("SELECT COUNT(*) as count FROM exams WHERE created_by=? AND status='Draft'", 
                                    (teacher_id,)).fetchone()['count'],
            'approved_exams': conn.execute("SELECT COUNT(*) as count FROM exams WHERE created_by=? AND status='Approved'", 
                                        (teacher_id,)).fetchone()['count'],
            'pending_count': conn.execute('''
                SELECT COUNT(*) as count
                FROM student_answers sa
                JOIN student_profile sp ON sa.student_id = sp.id
                JOIN teacher_profile tp ON sp.class_id = tp.assigned_class_id
                WHERE tp.user_id = ? AND sa.id NOT IN (SELECT student_answer_id FROM evaluation_results)
            ''', (teacher_id,)).fetchone()['count']
        }
        
        # Recent exams
        recent_exams = conn.execute('''
            SELECT e.*, s.subject_name, c.class_name
            FROM exams e
            JOIN subjects s ON e.subject_id = s.id
            JOIN classes c ON e.class_id = c.id
            WHERE e.created_by = ?
            ORDER BY e.created_at DESC
            LIMIT 5
        ''', (teacher_id,)).fetchall()
        
        # Recent activities
        activities = conn.execute('''
            SELECT al.*, u.full_name 
            FROM activity_logs al
            LEFT JOIN users u ON al.user_id = u.id 
            WHERE u.id=?
            ORDER BY al.timestamp DESC
            LIMIT 10
        ''', (teacher_id,)).fetchall()
        
        conn.close()
        return render_template('teacher/dashboard.html', stats=stats, 
                             recent_exams=recent_exams, activities=activities)
    
    conn.close()
    return redirect(url_for('login'))
    
@app.route('/student/profile')
@login_required
@student_required
def student_profile():
    conn = get_db_connection()
    
    # Get student profile with user details
    student_profile = conn.execute('''
        SELECT 
            sp.*, 
            c.class_name, 
            u.full_name, 
            u.email,
            u.created_at as registration_date
        FROM student_profile sp
        LEFT JOIN classes c ON sp.class_id = c.id
        LEFT JOIN users u ON sp.user_id = u.id
        WHERE sp.user_id = ?
    ''', (session['user_id'],)).fetchone()
    
    # Get all subjects for the student's class
    subjects = []
    if student_profile and student_profile['class_id']:
        subjects = conn.execute('''
            SELECT DISTINCT s.id, s.subject_name, s.description
    FROM subjects s
    INNER JOIN teacher_profile tp ON s.id = tp.assigned_subject_id
    WHERE tp.assigned_class_id = ?
    ORDER BY s.subject_name
        ''', (student_profile['class_id'],)).fetchall()
    
    conn.close()
    
    return render_template('student/profile.html', 
                         profile=student_profile, 
                         subjects=subjects)

@app.route('/student/upload-answer', methods=['GET', 'POST'])
@login_required
@student_required
def upload_answer():
    exam_title = request.args.get('exam_title', '')
    
    conn = get_db_connection()
    
    # # if request.method == 'POST':
    # #     exam_title = request.form.get('exam_title')
    # #     answer_file = request.files.get('answer_file')
        
    # #     # Get student profile
    # #     student_profile = conn.execute(
    # #         'SELECT id, class_id FROM student_profile WHERE user_id = ?', 
    # #         (session['user_id'],)
    # #     ).fetchone()
        
    # #     if not student_profile:
    # #         flash('Student profile not found!', 'danger')
    # #         conn.close()
    # #         return redirect(url_for('upload_answer'))
        
    # #     if not answer_file or answer_file.filename == '':
    # #         flash('Please upload an answer sheet!', 'danger')
    # #         conn.close()
    # #         return redirect(url_for('upload_answer'))
        
    # #     if not answer_file.filename.endswith('.pdf'):
    # #         flash('Only PDF files are allowed!', 'danger')
    # #         conn.close()
    # #         return redirect(url_for('upload_answer'))
        
    # #     try:
    # #         # Save uploaded PDF
    # #         upload_dir = 'uploads/student_answers'
    # #         os.makedirs(upload_dir, exist_ok=True)
            
    # #         filename = secure_filename(answer_file.filename)
    # #         timestamp = int(time.time())
    # #         file_path = os.path.join(upload_dir, f"{session['user_id']}_{timestamp}_{filename}")
    # #         answer_file.save(file_path)
            
    # #         # Extract text from PDF
    # #         extracted_answers = extract_text_from_pdf(file_path)
    # #         print(extracted_answers)
    # #         # Get all questions for this exam
    # #         exam_questions = conn.execute('''
    # #             SELECT id, question_id, question_text, model_answer_text, marks, subject_id
    # #             FROM model_answers
    # #             WHERE exam_title = ?
    # #             ORDER BY question_id
    # #         ''', (exam_title,)).fetchall()
            
    # #         if not exam_questions:
    # #             flash('Exam questions not found!', 'danger')
    # #             os.remove(file_path)
    # #             conn.close()
    # #             return redirect(url_for('upload_answer'))
            
    # #         # Process each question
    # #         for question in exam_questions:
    # #             question_id = question['question_id']
    # #             model_answer = question['model_answer_text']
                
    # #             # Get student's answer for this question
    # #             student_answer = extracted_answers.get(question_id, '')
    # #             print(student_answer)
    # #             # Determine status
    # #             status = 'Attempted' if student_answer.strip() else 'Not Attempted'
                
    # #             # Insert student answer
    # #             cursor = conn.cursor()
    # #             cursor.execute('''
    # #                 INSERT INTO student_answers 
    # #                 (student_id, subject_id, exam_title, question_id, answer_text, file_path, status, uploaded_at)
    # #                 VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    # #             ''', (student_profile['id'], question['subject_id'], exam_title, 
    # #                   question_id, student_answer, file_path, status))
                
    # #             student_answer_id = cursor.lastrowid
                
    # #             # If attempted, evaluate with AI
    # #             if status == 'Attempted':
    # #                 scores, feedback = evaluate_answer_with_ai(student_answer, model_answer, question['marks'])
                    
    # #                 # Insert evaluation results
    # #                 cursor.execute('''
    # #                     INSERT INTO evaluation_results
    # #                     (student_answer_id, model_answer_id, content_score, concept_score, 
    # #                      grammar_score, total_score, evaluated_by_ai, evaluated_at)
    # #                     VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
    # #                 ''', (student_answer_id, question['id'], scores['content_score'], 
    # #                       scores['concept_score'], scores['grammar_score'], scores['total_score']))
                    
    # #                 evaluation_id = cursor.lastrowid
                    
    # #                 # Insert feedback
    # #                 cursor.execute('''
    # #                     INSERT INTO feedback
    # #                     (evaluation_id, feedback_text, missing_keywords, created_at)
    # #                     VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    # #                 ''', (evaluation_id, feedback['feedback_text'], feedback['missing_keywords']))
    # #             else:
    # #                 # Not attempted - give 0 marks
    # #                 cursor.execute('''
    # #                     INSERT INTO evaluation_results
    # #                     (student_answer_id, model_answer_id, content_score, concept_score, 
    # #                      grammar_score, total_score, evaluated_by_ai, evaluated_at)
    # #                     VALUES (?, ?, 0, 0, 0, 0, 1, CURRENT_TIMESTAMP)
    # #                 ''', (student_answer_id, question['id']))
                    
    # #                 evaluation_id = cursor.lastrowid
                    
    # #                 cursor.execute('''
    # #                     INSERT INTO feedback
    # #                     (evaluation_id, feedback_text, created_at)
    # #                     VALUES (?, 'Question not attempted.', CURRENT_TIMESTAMP)
    # #                 ''', (evaluation_id,))
            
    # #         # Log activity
    # #         conn.execute('''
    # #             INSERT INTO activity_logs (user_id, action)
    # #             VALUES (?, ?)
    # #         ''', (session['user_id'], f'Submitted exam: {exam_title}'))
            
    # #         conn.commit()
    # #         conn.close()
            
    # #         flash(f'Exam "{exam_title}" submitted and evaluated successfully!', 'success')
    # #         return redirect(url_for('dashboard'))
            
    # #     except Exception as e:
    # #         flash(f'Error processing answer sheet: {str(e)}', 'danger')
    # #         if os.path.exists(file_path):
    # #             os.remove(file_path)
    # #         conn.close()
    # #         return redirect(url_for('upload_answer'))
    
    # GET request
    student = conn.execute('''
        SELECT class_id FROM student_profile WHERE user_id = ?
    ''', (session['user_id'],)).fetchone()
    exam_details = None
    if student:
        # If exam_title is passed, get its details
        if exam_title:
            exam_details = conn.execute('''
                SELECT 
                    ma.exam_title,
                    ma.subject_id,
                    s.subject_name,
                    ma.class_id,
                    c.class_name,
                    COUNT(ma.id) as total_questions,
                    SUM(ma.marks) as total_marks
                FROM model_answers ma
                JOIN subjects s ON ma.subject_id = s.id
                JOIN classes c ON ma.class_id = c.id
                WHERE ma.exam_title = ? AND ma.class_id = ?
                GROUP BY ma.exam_title, ma.subject_id, ma.class_id
            ''', (exam_title, student['class_id'])).fetchone()
        
        # Get all available exams for dropdown (if no exam_title passed)
        exams = conn.execute('''
            SELECT DISTINCT exam_title
            FROM model_answers
            WHERE class_id = ?
            ORDER BY exam_title
        ''', (student['class_id'],)).fetchall()
    else:
        exams = []
    
    conn.close()
    
    return render_template('student/upload_answer_sheet.html', subjects=exams, selected_exam=exam_title)

# @app.route('/student/my-submissions')
# @login_required
# @student_required
# def my_submissions():
#     conn = get_db_connection()
    
#     submissions = conn.execute('''
#         SELECT sa.*, s.subject_name, er.total_score, er.content_score, 
#                er.concept_score, er.grammar_score, er.evaluated_at,
#                f.feedback_text, f.missing_keywords
#         FROM student_answers sa
#         JOIN student_profile sp ON sa.student_id = sp.id
#         JOIN subjects s ON sa.subject_id = s.id
#         LEFT JOIN evaluation_results er ON sa.id = er.student_answer_id
#         LEFT JOIN feedback f ON er.id = f.evaluation_id
#         WHERE sp.user_id = ?
#         ORDER BY sa.uploaded_at DESC
#     ''', (session['user_id'],)).fetchall()
    
#     conn.close()
#     return render_template('student/submissions.html', submissions=submissions)

# ==================== TEACHER ROUTES ====================
@app.route('/teacher/profile')
@login_required
@teacher_required
def teacher_profile():
    conn = get_db_connection()
    
    teacher_profile = conn.execute('''
        SELECT tp.*, c.class_name, s.subject_name, u.full_name, u.email
        FROM teacher_profile tp
        LEFT JOIN classes c ON tp.assigned_class_id = c.id
        LEFT JOIN subjects s ON tp.assigned_subject_id = s.id
        LEFT JOIN users u ON tp.user_id = u.id
        WHERE tp.user_id = ?
    ''', (session['user_id'],)).fetchone()
    
    conn.close()
    return render_template('teacher/profile.html', profile=teacher_profile)

@app.route('/teacher/pending-evaluations')
@login_required
@teacher_required
def pending_evaluations():
    conn = get_db_connection()
    
    pending = conn.execute('''
        SELECT sa.*, s.subject_name, u.full_name as student_name, sp.roll_no, c.class_name
        FROM student_answers sa
        JOIN student_profile sp ON sa.student_id = sp.id
        JOIN users u ON sp.user_id = u.id
        JOIN exams e ON sa.exam_id = e.id
        JOIN subjects s ON e.subject_id = s.id
        JOIN classes c ON sp.class_id = c.id
        JOIN teacher_profile tp ON sp.class_id = tp.assigned_class_id
        WHERE tp.user_id = ? AND sa.id NOT IN (SELECT student_answer_id FROM evaluation_results)
        ORDER BY sa.uploaded_at DESC
    ''', (session['user_id'],)).fetchall()
    
    conn.close()
    return render_template('teacher/pending_evaluations.html', pending=pending)

@app.route('/teacher/provide-feedback/<int:answer_id>', methods=['GET', 'POST'])
@login_required
@teacher_required
def provide_feedback(answer_id):
    conn = get_db_connection()
    
    # Get the student's answer and the matching question details
    answer = conn.execute('''
        SELECT sa.*, s.subject_name, u.full_name as student_name, sp.roll_no,
               ma.question_text, ma.model_answer_text, ma.marks as max_marks, ma.id as model_answer_id
        FROM student_answers sa
        JOIN student_profile sp ON sa.student_id = sp.id
        JOIN users u ON sp.user_id = u.id
        JOIN exams e ON sa.exam_id = e.id
        JOIN subjects s ON e.subject_id = s.id
        LEFT JOIN model_answers ma ON sa.exam_id = ma.exam_id AND sa.question_id = ma.question_id
        WHERE sa.id = ?
    ''', (answer_id,)).fetchone()
    
    if not answer:
        flash('Student answer not found!', 'danger')
        conn.close()
        return redirect(url_for('pending_evaluations'))

    if request.method == 'POST':
        content_score = float(request.form.get('content_score', 0))
        concept_score = float(request.form.get('concept_score', 0))
        grammar_score = float(request.form.get('grammar_score', 0))
        feedback_text = request.form.get('feedback_text', '')
        missing_keywords = request.form.get('missing_keywords', '')
        
        max_marks = float(answer['max_marks'] or 10.0)
        
        # Calculate raw total marks awarded (average of scores entered out of max_marks)
        total_score = round((content_score + concept_score + grammar_score) / 3, 2)
        total_score = max(0.0, min(max_marks, total_score))
        
        # Convert scores to percentages (0-100) for database consistency
        content_pct = round((content_score / max_marks) * 100, 2) if max_marks > 0 else 0
        concept_pct = round((concept_score / max_marks) * 100, 2) if max_marks > 0 else 0
        grammar_pct = round((grammar_score / max_marks) * 100, 2) if max_marks > 0 else 0
        
        # Insert evaluation result
        cursor = conn.execute('''
            INSERT INTO evaluation_results 
            (student_answer_id, model_answer_id, content_score, concept_score, grammar_score, total_score, evaluated_by_ai)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        ''', (answer_id, answer['model_answer_id'], content_pct, concept_pct, grammar_pct, total_score))
        
        evaluation_id = cursor.lastrowid
        
        # Insert feedback
        conn.execute('''
            INSERT INTO feedback 
            (evaluation_id, feedback_text, missing_keywords, corrected_by_teacher)
            VALUES (?, ?, ?, ?)
        ''', (evaluation_id, feedback_text, missing_keywords, session['user_id']))
        
        # Log activity
        conn.execute('''
            INSERT INTO activity_logs (user_id, action)
            VALUES (?, ?)
        ''', (session['user_id'], f'Provided feedback for answer ID: {answer_id}'))
        
        conn.commit()
        conn.close()
        
        flash('Feedback provided successfully!', 'success')
        return redirect(url_for('pending_evaluations'))
    
    # GET request
    conn.close()
    return render_template('teacher/provide_feedback.html', answer=answer)

# ==================== USER MANAGEMENT ====================
@app.route('/users')
@login_required
@admin_required
def users_list():
    conn = get_db_connection()
    users = conn.execute('''
        SELECT u.*, 
               CASE 
                   WHEN u.role = "Student" THEN sp.roll_no
                   ELSE NULL
               END as roll_no,
               CASE 
                   WHEN u.role = "Student" THEN c.class_name
                   ELSE NULL
               END as class_name
        FROM users u
        LEFT JOIN student_profile sp ON u.id = sp.user_id
        LEFT JOIN classes c ON sp.class_id = c.id
        ORDER BY u.created_at DESC
    ''').fetchall()
    conn.close()
    
    return render_template('users/list.html', users=users)

@app.route('/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        
        conn = get_db_connection()
        
        # Check if email exists
        existing_user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if existing_user:
            flash('Email already exists!', 'danger')
            conn.close()
            return redirect(url_for('add_user'))
        
        # Insert user
        password_hash = generate_password_hash(password)
        cursor = conn.execute('''
            INSERT INTO users (full_name, email, password_hash, role)
            VALUES (?, ?, ?, ?)
        ''', (full_name, email, password_hash, role))
        user_id = cursor.lastrowid
        
        # Create profile based on role
        if role == 'Student':
            roll_no = request.form.get('roll_no')
            class_id = request.form.get('class_id')
            conn.execute('''
                INSERT INTO student_profile (user_id, roll_no, class_id)
                VALUES (?, ?, ?)
            ''', (user_id, roll_no, class_id))
        
        elif role == 'Teacher':
            qualification = request.form.get('qualification', '')
            experience_years = request.form.get('experience_years', 0)
            assigned_class_id = request.form.get('assigned_class_id')
            assigned_subject_id = request.form.get('assigned_subject_id')
            
            conn.execute('''
                INSERT INTO teacher_profile (user_id, qualification, experience_years, 
                                            assigned_class_id, assigned_subject_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, qualification, experience_years, assigned_class_id, assigned_subject_id))
        
        # Log activity
        conn.execute('''
            INSERT INTO activity_logs (user_id, action)
            VALUES (?, ?)
        ''', (session['user_id'], f'Added new {role}: {full_name}'))
        
        conn.commit()
        conn.close()
        
        flash(f'{role} added successfully!', 'success')
        return redirect(url_for('users_list'))
    
    # GET request
    conn = get_db_connection()
    classes = conn.execute('SELECT * FROM classes ORDER BY class_name').fetchall()
    subjects = conn.execute('SELECT * FROM subjects ORDER BY subject_name').fetchall()
    conn.close()
    
    return render_template('users/add.html', classes=classes, subjects=subjects)

@app.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    conn = get_db_connection()
    
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        status = request.form.get('status')
        role = request.form.get('role')
        
        # Update user
        conn.execute('''
            UPDATE users 
            SET full_name = ?, email = ?, status = ?
            WHERE id = ?
        ''', (full_name, email, status, user_id))
        
        # Update profile based on role
        if role == 'Student':
            roll_no = request.form.get('roll_no')
            class_id = request.form.get('class_id')
            conn.execute('''
                UPDATE student_profile 
                SET roll_no = ?, class_id = ?
                WHERE user_id = ?
            ''', (roll_no, class_id, user_id))
        
        elif role == 'Teacher':
            qualification = request.form.get('qualification', '')
            experience_years = request.form.get('experience_years', 0)
            assigned_class_id = request.form.get('assigned_class_id')
            assigned_subject_id = request.form.get('assigned_subject_id')
            
            conn.execute('''
                UPDATE teacher_profile 
                SET qualification = ?, experience_years = ?, 
                    assigned_class_id = ?, assigned_subject_id = ?
                WHERE user_id = ?
            ''', (qualification, experience_years, assigned_class_id, assigned_subject_id, user_id))
        
        # Log activity
        conn.execute('''
            INSERT INTO activity_logs (user_id, action)
            VALUES (?, ?)
        ''', (session['user_id'], f'Updated {role}: {full_name}'))
        
        conn.commit()
        conn.close()
        
        flash('User updated successfully!', 'success')
        return redirect(url_for('users_list'))
    
    # GET request
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    
    student_profile = None
    teacher_profile = None
    
    if user['role'] == 'Student':
        student_profile = conn.execute('SELECT * FROM student_profile WHERE user_id = ?', (user_id,)).fetchone()
    elif user['role'] == 'Teacher':
        teacher_profile = conn.execute('SELECT * FROM teacher_profile WHERE user_id = ?', (user_id,)).fetchone()
    
    classes = conn.execute('SELECT * FROM classes ORDER BY class_name').fetchall()
    subjects = conn.execute('SELECT * FROM subjects ORDER BY subject_name').fetchall()
    conn.close()
    
    return render_template('users/edit.html', user=user, student_profile=student_profile, 
                         teacher_profile=teacher_profile, classes=classes, subjects=subjects)

@app.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    
    if user:
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.execute('''
            INSERT INTO activity_logs (user_id, action)
            VALUES (?, ?)
        ''', (session['user_id'], f'Deleted user: {user["full_name"]}'))
        conn.commit()
        flash('User deleted successfully!', 'success')
    
    conn.close()
    return redirect(url_for('users_list'))

# ==================== CLASS MANAGEMENT ====================
@app.route('/classes')
@login_required
@admin_required
def classes_list():
    conn = get_db_connection()
    classes = conn.execute('SELECT * FROM classes ORDER BY class_name').fetchall()
    conn.close()
    return render_template('classes/list.html', classes=classes)

@app.route('/classes/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_class():
    if request.method == 'POST':
        class_name = request.form.get('class_name')
        description = request.form.get('description', '')
        
        conn = get_db_connection()
        try:
            conn.execute('''
                INSERT INTO classes (class_name, description)
                VALUES (?, ?)
            ''', (class_name, description))
            
            conn.execute('''
                INSERT INTO activity_logs (user_id, action)
                VALUES (?, ?)
            ''', (session['user_id'], f'Added class: {class_name}'))
            
            conn.commit()
            flash('Class added successfully!', 'success')
        except sqlite3.IntegrityError:
            flash('Class name already exists!', 'danger')
        finally:
            conn.close()
        
        return redirect(url_for('classes_list'))
    
    return render_template('classes/add.html')

@app.route('/classes/edit/<int:class_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_class(class_id):
    conn = get_db_connection()
    
    if request.method == 'POST':
        class_name = request.form.get('class_name')
        description = request.form.get('description', '')
        
        try:
            conn.execute('''
                UPDATE classes 
                SET class_name = ?, description = ?
                WHERE id = ?
            ''', (class_name, description, class_id))
            
            conn.execute('''
                INSERT INTO activity_logs (user_id, action)
                VALUES (?, ?)
            ''', (session['user_id'], f'Updated class: {class_name}'))
            
            conn.commit()
            flash('Class updated successfully!', 'success')
        except sqlite3.IntegrityError:
            flash('Class name already exists!', 'danger')
        finally:
            conn.close()
        
        return redirect(url_for('classes_list'))
    
    class_data = conn.execute('SELECT * FROM classes WHERE id = ?', (class_id,)).fetchone()
    conn.close()
    
    return render_template('classes/edit.html', class_data=class_data)

@app.route('/classes/delete/<int:class_id>', methods=['POST'])
@login_required
@admin_required
def delete_class(class_id):
    conn = get_db_connection()
    class_data = conn.execute('SELECT * FROM classes WHERE id = ?', (class_id,)).fetchone()
    
    if class_data:
        conn.execute('DELETE FROM classes WHERE id = ?', (class_id,))
        conn.execute('''
            INSERT INTO activity_logs (user_id, action)
            VALUES (?, ?)
        ''', (session['user_id'], f'Deleted class: {class_data["class_name"]}'))
        conn.commit()
        flash('Class deleted successfully!', 'success')
    
    conn.close()
    return redirect(url_for('classes_list'))

# ==================== SUBJECT MANAGEMENT ====================
@app.route('/subjects')
@login_required
@admin_required
def subjects_list():
    conn = get_db_connection()
    subjects = conn.execute('SELECT * FROM subjects ORDER BY subject_name').fetchall()
    conn.close()
    return render_template('subjects/list.html', subjects=subjects)

@app.route('/subjects/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_subject():
    if request.method == 'POST':
        subject_name = request.form.get('subject_name')
        description = request.form.get('description', '')
        
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO subjects (subject_name, description)
            VALUES (?, ?)
        ''', (subject_name, description))
        
        conn.execute('''
            INSERT INTO activity_logs (user_id, action)
            VALUES (?, ?)
        ''', (session['user_id'], f'Added subject: {subject_name}'))
        
        conn.commit()
        conn.close()
        
        flash('Subject added successfully!', 'success')
        return redirect(url_for('subjects_list'))
    
    return render_template('subjects/add.html')

@app.route('/subjects/edit/<int:subject_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_subject(subject_id):
    conn = get_db_connection()
    
    if request.method == 'POST':
        subject_name = request.form.get('subject_name')
        description = request.form.get('description', '')
        
        conn.execute('''
            UPDATE subjects 
            SET subject_name = ?, description = ?
            WHERE id = ?
        ''', (subject_name, description, subject_id))
        
        conn.execute('''
            INSERT INTO activity_logs (user_id, action)
            VALUES (?, ?)
        ''', (session['user_id'], f'Updated subject: {subject_name}'))
        
        conn.commit()
        conn.close()
        
        flash('Subject updated successfully!', 'success')
        return redirect(url_for('subjects_list'))
    
    subject = conn.execute('SELECT * FROM subjects WHERE id = ?', (subject_id,)).fetchone()
    conn.close()
    
    return render_template('subjects/edit.html', subject=subject)

@app.route('/subjects/delete/<int:subject_id>', methods=['POST'])
@login_required
@admin_required
def delete_subject(subject_id):
    conn = get_db_connection()
    subject = conn.execute('SELECT * FROM subjects WHERE id = ?', (subject_id,)).fetchone()
    
    if subject:
        conn.execute('DELETE FROM subjects WHERE id = ?', (subject_id,))
        conn.execute('''
            INSERT INTO activity_logs (user_id, action)
            VALUES (?, ?)
        ''', (session['user_id'], f'Deleted subject: {subject["subject_name"]}'))
        conn.commit()
        flash('Subject deleted successfully!', 'success')
    
    conn.close()
    return redirect(url_for('subjects_list'))


# Exam Creation by Teacher 

# @app.route('/teacher/create_exam', methods=['GET', 'POST'])
# @login_required
# @teacher_required
# def create_exam():

#     if request.method == 'POST':
#         exam_title = request.form.get('exam_title')
#         subject_id = request.form.get('subject_id')
#         class_id = request.form.get('class_id')
#         excel_file = request.files.get('excel_file')
        
#         # Validation
#         if not all([exam_title, subject_id, class_id, excel_file]):
#             flash('All fields are required!', 'danger')
#             return redirect(url_for('create_exam'))
        
#         if not excel_file.filename.endswith(('.xlsx', '.xls')):
#             flash('Please upload a valid Excel file (.xlsx or .xls)', 'danger')
#             return redirect(url_for('create_exam'))
        
#         try:
#             # Create upload directory if not exists
#             upload_dir = 'uploads/model_answers'
#             os.makedirs(upload_dir, exist_ok=True)
            
#             # Save Excel file
#             filename = f"{exam_title.replace(' ', '_')}_{subject_id}_{class_id}_{int(time.time())}.xlsx"
#             file_path = os.path.join(upload_dir, filename)
#             excel_file.save(file_path)
            
#             # Read Excel file
#             import pandas as pd
#             df = pd.read_excel(file_path)
            
#             # Validate Excel structure
#             required_columns = ['Question No', 'Question', 'Answer','Marks']
#             print(df.columns)
#             if not all(col in df.columns for col in required_columns):
#                 flash('Excel file must have columns: Question No, Question, Answer, Marks (optional)', 'danger')
#                 os.remove(file_path)  # Delete uploaded file
#                 return redirect(url_for('create_exam'))
            
#             # Insert into database
#             conn = get_db_connection()
#             cursor = conn.cursor()
            
#             for index, row in df.iterrows():
#                 question_id = str(row['Question No']).strip()
#                 question_text = str(row['Question']).strip()
#                 model_answer_text = str(row['Answer']).strip()
#                 marks = int(row.get('Marks', 5))  # Default 5 marks if not provided
                
#                 cursor.execute('''
#                     INSERT INTO model_answers 
#                     (exam_title, subject_id, class_id, question_id, question_text, 
#                      model_answer_text, marks, source_file, uploaded_by)
#                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
#                 ''', (exam_title, subject_id, class_id, question_id, question_text,
#                       model_answer_text, marks, file_path, session['user_id']))
            
#             # Log activity
#             cursor.execute('''
#                 INSERT INTO activity_logs (user_id, action)
#                 VALUES (?, ?)
#             ''', (session['user_id'], f'Created exam: {exam_title}'))
            
#             conn.commit()
#             conn.close()
            
#             flash(f'Exam "{exam_title}" created successfully with {len(df)} questions!', 'success')
#             return redirect(url_for('dashboard'))
           
#         except Exception as e:
#             flash(f'Error creating exam: {str(e)}', 'danger')
#             if os.path.exists(file_path):
#                 os.remove(file_path)
#             return redirect(url_for('create_exam'))
    
#     # GET request - show form
#     conn = get_db_connection()
#     cursor = conn.cursor()
    
#     # Get teacher's assigned subject and class
#     cursor.execute('''
#         SELECT assigned_subject_id, assigned_class_id 
#         FROM teacher_profile 
#         WHERE user_id = ?
#     ''', (session['user_id'],))
#     teacher_info = cursor.fetchone()
    
#     # Get all subjects and classes for dropdown
#     cursor.execute('''
#             SELECT s.id, s.subject_name 
#             FROM subjects s
#             INNER JOIN teacher_profile tp ON s.id = tp.assigned_subject_id
#             WHERE tp.user_id = ?
#             ORDER BY s.subject_name
#         ''', (session['user_id'],))
#     subjects = cursor.fetchall()

#         # Get only the class assigned to this teacher
#     cursor.execute('''
#             SELECT c.id, c.class_name 
#             FROM classes c
#             INNER JOIN teacher_profile tp ON c.id = tp.assigned_class_id
#             WHERE tp.user_id = ?
#             ORDER BY c.class_name
#         ''', (session['user_id'],))
#     classes = cursor.fetchall()
    
#     conn.close()
    
#     return render_template('teacher/create_exam.html', 
#                          subjects=subjects, 
#                          classes=classes,
#                          teacher_info=teacher_info)
@app.route('/teacher/exams')
def exam_list():
    if 'user_id' not in session or session.get('role') != 'Teacher':
        flash('Unauthorized access!', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all exams created by this teacher (grouped by exam_title)
    exams = cursor.execute('''
        SELECT 
            exam_title,
            subject_id,
            class_id,
            COUNT(*) as total_questions,
            SUM(marks) as total_marks,
            MAX(created_at) as created_at,
            source_file
        FROM model_answers
        WHERE uploaded_by = ?
        GROUP BY exam_title, subject_id, class_id
        ORDER BY created_at DESC
    ''', (session['user_id'],)).fetchall()
    
    # Get subject and class names for each exam
    exam_list = []
    for exam in exams:
        # Get subject name
        subject = cursor.execute('SELECT subject_name FROM subjects WHERE id = ?', 
                                (exam['subject_id'],)).fetchone()
        
        # Get class name
        class_info = cursor.execute('SELECT class_name FROM classes WHERE id = ?', 
                                   (exam['class_id'],)).fetchone()
        
        exam_list.append({
            'exam_title': exam['exam_title'],
            'subject_name': subject['subject_name'] if subject else 'N/A',
            'class_name': class_info['class_name'] if class_info else 'N/A',
            'total_questions': exam['total_questions'],
            'total_marks': exam['total_marks'],
            'created_at': exam['created_at']
        })
    
    conn.close()
    
    return render_template('teacher/exam_list.html', exams=exam_list)       


@app.route('/student/view_question_paper/<exam_title>')
def view_question_paper(exam_title):
    if 'user_id' not in session or session.get('role') != 'Student':
        flash('Unauthorized access!', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get exam details and questions
    questions = cursor.execute('''
        SELECT 
            ma.question_id,
            ma.question_text,
            ma.marks,
            ma.exam_title,
            s.subject_name,
            c.class_name
        FROM model_answers ma
        JOIN subjects s ON ma.subject_id = s.id
        JOIN classes c ON ma.class_id = c.id
        WHERE ma.exam_title = ?
        ORDER BY ma.question_id
    ''', (exam_title,)).fetchall()
    
    conn.close()
    
    if not questions:
        flash('Question paper not found!', 'danger')
        return redirect(url_for('dashboard'))
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.HexColor('#666666'),
        spaceAfter=20,
        alignment=TA_CENTER
    )
    
    question_style = ParagraphStyle(
        'QuestionStyle',
        parent=styles['Normal'],
        fontSize=11,
        leading=14,
        spaceAfter=8
    )
    
    # Header
    elements.append(Paragraph(f"<b>{questions[0]['exam_title']}</b>", title_style))
    elements.append(Paragraph(
        f"Subject: {questions[0]['subject_name']} | Class: {questions[0]['class_name']}", 
        subtitle_style
    ))
    elements.append(Spacer(1, 0.2*inch))
    
    # Instructions
    instructions = """
    <b>Instructions:</b><br/>
    1. Answer all questions in the space provided.<br/>
    2. Write your answers clearly and legibly.<br/>
    3. Each question carries marks as indicated.<br/>
    """
    elements.append(Paragraph(instructions, styles['Normal']))
    elements.append(Spacer(1, 0.3*inch))
    
    # Questions
    total_marks = 0
    for idx, q in enumerate(questions, 1):
        total_marks += q['marks']
        
        # Question header with marks
        q_header = f"<b>{q['question_id']}. [{q['marks']} Marks]</b>"
        elements.append(Paragraph(q_header, question_style))
        
        # Question text
        q_text = q['question_text']
        elements.append(Paragraph(q_text, question_style))
        
        # # Answer space
        # elements.append(Spacer(1, 0.15*inch))
        # elements.append(Paragraph("_" * 100, styles['Normal']))
        # elements.append(Spacer(1, 0.05*inch))
        # elements.append(Paragraph("_" * 100, styles['Normal']))
        # elements.append(Spacer(1, 0.3*inch))
    
    # Footer
    elements.append(Spacer(1, 0.3*inch))
    footer = f"<b>Total Marks: {total_marks}</b>"
    elements.append(Paragraph(footer, subtitle_style))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"{exam_title.replace(' ', '_')}_Question_Paper.pdf"
    )  
@app.route('/upload_syllabus', methods=['GET', 'POST'])
def upload_syllabus():
    """Upload syllabus PDF"""
    if 'user_id' not in session or session.get('role') != 'Teacher':
        flash('Access denied. Teachers only.', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        title = request.form.get('title')
        subject_id = request.form.get('subject_id')
        class_id = request.form.get('class_id')
        
        # Handle file upload
        if 'syllabus_pdf' not in request.files:
            flash('No file uploaded', 'danger')
            return redirect(request.url)
        
        file = request.files['syllabus_pdf']
        
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            filepath = os.path.join(SYLLABUS_FOLDER, filename)
            file.save(filepath)
            
            # Extract text from PDF
            extracted_text = pdf_to_text.extract_text_from_pdf(filepath)
            
            # Save to database
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO syllabus (subject_id, class_id, title, pdf_path, 
                                     extracted_text, uploaded_by)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (subject_id, class_id, title, filepath, extracted_text, session['user_id']))
            conn.commit()
            
            flash('Syllabus uploaded successfully!', 'success')
            return redirect(url_for('view_syllabus'))
        else:
            flash('Invalid file format. Only PDF allowed.', 'danger')
    
    # Get subjects and classes
    subjects = conn.execute('SELECT * FROM subjects').fetchall()
    classes = conn.execute('SELECT * FROM classes').fetchall()
    
    # Get teacher info
    teacher_info = conn.execute('''
        SELECT * FROM teacher_profile WHERE user_id = ?
    ''', (session['user_id'],)).fetchone()
    
    # Get recent syllabus
    recent_syllabus = conn.execute('''
        SELECT s.*, sub.subject_name, c.class_name
        FROM syllabus s
        JOIN subjects sub ON s.subject_id = sub.id
        JOIN classes c ON s.class_id = c.id
        WHERE s.uploaded_by = ?
        ORDER BY s.upload_date DESC
        LIMIT 5
    ''', (session['user_id'],)).fetchall()
    
    conn.close()
    
    return render_template('teacher/upload_syllabus.html', 
                          subjects=subjects, 
                          classes=classes,
                          teacher_info=teacher_info,
                          recent_syllabus=recent_syllabus)

@app.route('/view_syllabus')
def view_syllabus():
    """View all uploaded syllabus"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    syllabus_list = conn.execute('''
        SELECT s.*, sub.subject_name, c.class_name, u.full_name as uploaded_by_name
        FROM syllabus s
        JOIN subjects sub ON s.subject_id = sub.id
        JOIN classes c ON s.class_id = c.id
        JOIN users u ON s.uploaded_by = u.id
        ORDER BY s.upload_date DESC
    ''').fetchall()
    
    conn.close()
    
    return render_template('teacher/view_syllabus.html', syllabus_list=syllabus_list)

@app.route('/download_syllabus/<int:syllabus_id>')
def download_syllabus(syllabus_id):
    """Download syllabus PDF"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    syllabus = conn.execute('SELECT * FROM syllabus WHERE id = ?', (syllabus_id,)).fetchone()
    conn.close()
    
    if syllabus:
        return send_file(syllabus['pdf_path'], as_attachment=True)
    else:
        flash('Syllabus not found', 'danger')
        return redirect(url_for('view_syllabus'))

@app.route('/get_syllabus/<int:subject_id>/<int:class_id>')
def get_syllabus(subject_id, class_id):
    """API endpoint to get syllabus for subject and class"""
    conn = get_db_connection()
    syllabus = conn.execute('''
        SELECT id, title FROM syllabus 
        WHERE subject_id = ? AND class_id = ? AND status = 'Active'
    ''', (subject_id, class_id)).fetchall()
    conn.close()
    
    return jsonify([dict(s) for s in syllabus])

# =====================================================
# AI EXAM GENERATION ROUTES
# =====================================================

# =====================================================
# AI EXAM GENERATION ROUTES
# =====================================================
# AI EXAM GENERATION ROUTES - SUBJECTIVE ONLY
# =====================================================


@app.route('/teacher/create_exam', methods=['GET', 'POST'])
@login_required
@teacher_required
def create_exam():
    """Create AI-generated exam with difficulty levels - Subjective Questions Only"""
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        # Get form data
        exam_title = request.form.get('exam_title')
        subject_id = request.form.get('subject_id')
        class_id = request.form.get('class_id')
        syllabus_id = request.form.get('syllabus_id')
        difficulty_level = request.form.get('difficulty_level', 'Medium')
        duration = request.form.get('duration')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        
        # Question configuration - SUBJECTIVE ONLY
        subjective_count = int(request.form.get('subjective_count', 5))
        subjective_marks = int(request.form.get('subjective_marks', 5))
        
        # Validate
        if subjective_count < 1:
            flash('Please enter at least 1 question', 'danger')
            conn.close()
            return redirect(request.url)
        
        if subjective_count > 30:
            flash('Maximum 30 questions allowed', 'danger')
            conn.close()
            return redirect(request.url)
        
        total_marks = subjective_count * subjective_marks
        
        # Get syllabus content
        syllabus = conn.execute('SELECT * FROM syllabus WHERE id = ?', (syllabus_id,)).fetchone()
        
        if not syllabus:
            flash('Syllabus not found', 'danger')
            conn.close()
            return redirect(request.url)
        
        syllabus_text = syllabus['extracted_text']
        
        if not syllabus_text or len(syllabus_text.strip()) < 100:
            flash('Syllabus has insufficient content. Please upload a detailed syllabus.', 'danger')
            conn.close()
            return redirect(request.url)
        
        # Create exam record
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO exams (exam_title, subject_id, class_id, syllabus_id, 
                                  created_by, difficulty_level, total_marks, duration_minutes, 
                                  start_date, end_date, status, ai_generated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Draft', 1)
            ''', (exam_title, subject_id, class_id, syllabus_id, session['user_id'], 
                  difficulty_level, total_marks, duration, start_date, end_date))
            
            exam_id = cursor.lastrowid
            
            # Generate Subjective questions with difficulty
            questions_generated = 0
            try:
                print(f"Generating {subjective_count} {difficulty_level} subjective questions...")
                
                subjective_questions = question_generator.generate_subjective_questions(
                    syllabus_text, subjective_count, subjective_marks, difficulty_level
                )
                
                for i, q in enumerate(subjective_questions):
                    cursor.execute('''
                        INSERT INTO model_answers (exam_id, question_id, question_text, 
                                                  question_type, difficulty_level,
                                                  model_answer_text, marks, ai_generated, is_approved)
                        VALUES (?, ?, ?, 'Subjective', ?, ?, ?, 1, 0)
                    ''', (exam_id, f'Q{i+1}', q['question'], difficulty_level,
                          q['model_answer'], q['marks']))
                    questions_generated += 1
                
                print(f"Successfully generated {questions_generated} questions")
                
            except Exception as e:
                print(f'Error generating questions: {str(e)}')
                flash(f'Error generating questions: {str(e)}', 'danger')
                # Rollback and delete exam if question generation fails
                cursor.execute('DELETE FROM exams WHERE id = ?', (exam_id,))
                conn.commit()
                conn.close()
                return redirect(request.url)
            
            # Log AI generation
            cursor.execute('''
                INSERT INTO ai_generation_history 
                (exam_id, prompt_used, questions_generated, difficulty_level, generated_by)
                VALUES (?, ?, ?, ?, ?)
            ''', (exam_id, f'Generated {questions_generated} {difficulty_level} subjective questions', 
                  questions_generated, difficulty_level, session['user_id']))
            
            # Update exam status to "In Review"
            cursor.execute('''
                UPDATE exams SET status = 'In Review' WHERE id = ?
            ''', (exam_id,))
            
            # Log activity
            cursor.execute('''
                INSERT INTO activity_logs (user_id, action)
                VALUES (?, ?)
            ''', (session['user_id'], f'Created AI exam: {exam_title} with {questions_generated} questions'))
            
            conn.commit()
            
            flash(f'✓ AI exam "{exam_title}" generated successfully with {questions_generated} questions! Please review and approve.', 'success')
            
            # Redirect to same page to show updated list
            conn.close()
            return redirect(url_for('create_exam'))
            
        except Exception as e:
            conn.rollback()
            conn.close()
            flash(f'Error creating exam: {str(e)}', 'danger')
            return redirect(request.url)
    
    # GET request - show form with created exams list
    subjects = conn.execute('''
        SELECT s.id, s.subject_name 
        FROM subjects s
        INNER JOIN teacher_profile tp ON s.id = tp.assigned_subject_id
        WHERE tp.user_id = ?
        ORDER BY s.subject_name
    ''', (session['user_id'],)).fetchall()
    
    classes = conn.execute('''
        SELECT c.id, c.class_name 
        FROM classes c
        INNER JOIN teacher_profile tp ON c.id = tp.assigned_class_id
        WHERE tp.user_id = ?
        ORDER BY c.class_name
    ''', (session['user_id'],)).fetchall()
    
    # Get all created exams by this teacher
    created_exams = conn.execute('''
        SELECT 
            e.id,
            e.exam_title,
            e.difficulty_level,
            e.total_marks,
            e.status,
            e.created_at,
            s.subject_name,
            c.class_name,
            COUNT(ma.id) as question_count
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        JOIN classes c ON e.class_id = c.id
        LEFT JOIN model_answers ma ON e.id = ma.exam_id
        WHERE e.created_by = ? AND e.ai_generated = 1
        GROUP BY e.id
        ORDER BY e.created_at DESC
    ''', (session['user_id'],)).fetchall()
    
    conn.close()
    
    return render_template('teacher/create_exam.html', 
                         subjects=subjects, 
                         classes=classes,
                         created_exams=created_exams)


@app.route('/teacher/view_exam_details/<int:exam_id>')
@login_required
@teacher_required
def view_exam_details(exam_id):
    """View detailed information about an exam"""
    
    conn = get_db_connection()
    
    # Get exam details
    exam = conn.execute('''
        SELECT e.*, s.subject_name, c.class_name, u.full_name as created_by_name
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        JOIN classes c ON e.class_id = c.id
        JOIN users u ON e.created_by = u.id
        WHERE e.id = ? AND e.created_by = ?
    ''', (exam_id, session['user_id'])).fetchone()
    
    if not exam:
        flash('Exam not found or access denied', 'danger')
        conn.close()
        return redirect(url_for('create_exam'))
    
    # Get all questions
    questions = conn.execute('''
        SELECT * FROM model_answers 
        WHERE exam_id = ?
        ORDER BY question_id
    ''', (exam_id,)).fetchall()
    
    # Get AI generation history
    ai_history = conn.execute('''
        SELECT * FROM ai_generation_history 
        WHERE exam_id = ?
        ORDER BY generated_at DESC
    ''', (exam_id,)).fetchall()
    
    # Get statistics
    stats = {
        'total_questions': len(questions),
        'easy_count': len([q for q in questions if q['difficulty_level'] == 'Easy']),
        'medium_count': len([q for q in questions if q['difficulty_level'] == 'Medium']),
        'hard_count': len([q for q in questions if q['difficulty_level'] == 'Hard']),
        'approved_count': len([q for q in questions if q['is_approved'] == 1]),
    }
    
    conn.close()
    
    return render_template('teacher/exam_details.html', 
                         exam=exam, 
                         questions=questions,
                         ai_history=ai_history,
                         stats=stats)


@app.route('/teacher/delete_exam/<int:exam_id>', methods=['POST'])
@login_required
@teacher_required
def delete_exam(exam_id):
    """Delete an exam and all its questions"""
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verify ownership
    exam = conn.execute(
        'SELECT * FROM exams WHERE id = ? AND created_by = ?', 
        (exam_id, session['user_id'])
    ).fetchone()
    
    if not exam:
        flash('Exam not found or access denied', 'danger')
        conn.close()
        return redirect(url_for('create_exam'))
    
    try:
        # Delete related records (cascade should handle this, but being explicit)
        cursor.execute('DELETE FROM ai_generation_history WHERE exam_id = ?', (exam_id,))
        cursor.execute('DELETE FROM model_answers WHERE exam_id = ?', (exam_id,))
        cursor.execute('DELETE FROM exams WHERE id = ?', (exam_id,))
        
        # Log activity
        cursor.execute('''
            INSERT INTO activity_logs (user_id, action)
            VALUES (?, ?)
        ''', (session['user_id'], f'Deleted exam: {exam["exam_title"]}'))
        
        conn.commit()
        conn.close()
        
        flash(f'✓ Exam "{exam["exam_title"]}" deleted successfully!', 'success')
    except Exception as e:
        conn.rollback()
        conn.close()
        flash(f'Error deleting exam: {str(e)}', 'danger')
    
    return redirect(url_for('create_exam'))


@app.route('/teacher/review_exam/<int:exam_id>', methods=['GET', 'POST'])
@login_required
@teacher_required
def review_exam(exam_id):
    """Review and edit AI-generated exam questions - Subjective Only"""
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        action = request.form.get('action')
        cursor = conn.cursor()
        
        # Get all questions
        questions = conn.execute(
            'SELECT * FROM model_answers WHERE exam_id = ? ORDER BY question_id', 
            (exam_id,)
        ).fetchall()
        
        # Update each question with edited values
        for question in questions:
            q_id = question['id']
            
            # Check if question should be deleted
            if f'delete_{q_id}' in request.form and request.form.get(f'delete_{q_id}') == '1':
                cursor.execute('DELETE FROM model_answers WHERE id = ?', (q_id,))
                continue
            
            question_text = request.form.get(f'question_text_{q_id}')
            marks = request.form.get(f'marks_{q_id}')
            difficulty = request.form.get(f'difficulty_{q_id}')
            model_answer = request.form.get(f'model_answer_{q_id}')
            
            cursor.execute('''
                UPDATE model_answers 
                SET question_text = ?, difficulty_level = ?,
                    model_answer_text = ?, marks = ?, is_approved = 1
                WHERE id = ?
            ''', (question_text, difficulty, model_answer, marks, q_id))
        
        # Handle action
        if action == 'approve':
            # Recalculate total marks
            total_marks = conn.execute(
                'SELECT SUM(marks) as total FROM model_answers WHERE exam_id = ?',
                (exam_id,)
            ).fetchone()['total'] or 0
            
            # Count remaining questions
            question_count = conn.execute(
                'SELECT COUNT(*) as count FROM model_answers WHERE exam_id = ?',
                (exam_id,)
            ).fetchone()['count']
            
            if question_count == 0:
                flash('Cannot approve exam with no questions!', 'danger')
                conn.close()
                return redirect(url_for('review_exam', exam_id=exam_id))
            
            cursor.execute('''
                UPDATE exams 
                SET status = 'Approved', total_marks = ?, approved_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (total_marks, exam_id))
            
            # Log activity
            cursor.execute('''
                INSERT INTO activity_logs (user_id, action)
                VALUES (?, ?)
            ''', (session['user_id'], f'Approved AI-generated exam ID: {exam_id}'))
            
            flash('✓ Exam approved and published successfully!', 'success')
            conn.commit()
            conn.close()
            return redirect(url_for('create_exam'))
        
        elif action == 'save_draft':
            cursor.execute('''
                UPDATE exams SET status = 'Draft' WHERE id = ?
            ''', (exam_id,))
            flash('✓ Exam saved as draft', 'info')
        
        conn.commit()
        conn.close()
        return redirect(url_for('review_exam', exam_id=exam_id))
    
    # GET request - show review page
    exam = conn.execute('''
        SELECT e.*, s.subject_name, c.class_name
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        JOIN classes c ON e.class_id = c.id
        WHERE e.id = ? AND e.created_by = ?
    ''', (exam_id, session['user_id'])).fetchone()
    
    if not exam:
        flash('Exam not found or access denied', 'danger')
        conn.close()
        return redirect(url_for('create_exam'))
    
    questions = conn.execute('''
        SELECT * FROM model_answers 
        WHERE exam_id = ?
        ORDER BY question_id
    ''', (exam_id,)).fetchall()
    
    # Get AI generation info
    ai_history = conn.execute('''
        SELECT * FROM ai_generation_history 
        WHERE exam_id = ?
        ORDER BY generated_at DESC
        LIMIT 1
    ''', (exam_id,)).fetchone()
    
    conn.close()
    
    return render_template('teacher/review_exam.html', 
                         exam=exam, 
                         questions=questions,
                         ai_history=ai_history)


@app.route('/teacher/regenerate_question/<int:exam_id>/<int:question_id>', methods=['POST'])
@login_required
@teacher_required
def regenerate_question(exam_id, question_id):
    """Regenerate a single question using AI - Subjective Only"""
    
    conn = get_db_connection()
    
    # Get exam and question details
    exam = conn.execute('SELECT * FROM exams WHERE id = ?', (exam_id,)).fetchone()
    question = conn.execute('SELECT * FROM model_answers WHERE id = ?', (question_id,)).fetchone()
    syllabus = conn.execute('SELECT * FROM syllabus WHERE id = ?', (exam['syllabus_id'],)).fetchone()
    
    if not all([exam, question, syllabus]):
        conn.close()
        return jsonify({'success': False, 'message': 'Data not found'})
    
    # Only allow subjective question regeneration
    if question['question_type'] != 'Subjective':
        conn.close()
        return jsonify({'success': False, 'message': 'Only subjective questions can be regenerated'})
    
    try:
        new_questions = question_generator.generate_subjective_questions(
            syllabus['extracted_text'], 1, question['marks'], question['difficulty_level']
        )
        new_q = new_questions[0]
        
        conn.execute('''
            UPDATE model_answers 
            SET question_text = ?, model_answer_text = ?
            WHERE id = ?
        ''', (new_q['question'], new_q['model_answer'], question_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Question regenerated successfully'})
    
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': str(e)})


@app.route('/teacher/download_question_paper/<int:exam_id>')
@login_required
@teacher_required
def download_question_paper(exam_id):
    """Generate and download question paper PDF with model answers"""

    conn = get_db_connection()

    # Get exam details
    exam = conn.execute('''
        SELECT e.*, s.subject_name, c.class_name
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        JOIN classes c ON e.class_id = c.id
        WHERE e.id = ? AND e.created_by = ?
    ''', (exam_id, session['user_id'])).fetchone()

    if not exam:
        flash('Exam not found or access denied', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))

    # Get questions
    questions = conn.execute('''
        SELECT * FROM model_answers 
        WHERE exam_id = ?
        ORDER BY question_id
    ''', (exam_id,)).fetchall()

    conn.close()


    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch
    )

    styles = getSampleStyleSheet()
    elements = []

    # -------- Styles --------
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=18,
        alignment=TA_CENTER,
        spaceAfter=15
    )

    subtitle_style = ParagraphStyle(
        'SubtitleStyle',
        parent=styles['Normal'],
        fontSize=12,
        alignment=TA_CENTER,
        spaceAfter=15
    )

    question_style = ParagraphStyle(
        'QuestionStyle',
        parent=styles['Normal'],
        fontSize=11,
        leading=14,
        spaceAfter=6
    )

    answer_style = ParagraphStyle(
        'AnswerStyle',
        parent=styles['Normal'],
        fontSize=10,
        leading=13,
        leftIndent=15,
        spaceAfter=12,
        textColor=colors.HexColor('#444444')
    )

    # -------- Header --------
    elements.append(Paragraph(exam['exam_title'], title_style))
    elements.append(Paragraph(
        f"Subject: {exam['subject_name']} | "
        f"Class: {exam['class_name']} | "
        f"Duration: {exam['duration_minutes']} mins",
        subtitle_style
    ))

    elements.append(Spacer(1, 0.2 * inch))

    instructions = f"""
    <b>Instructions:</b><br/>
    1. Answer all questions.<br/>
    2. Write answers clearly.<br/>
    3. Total Marks: {exam['total_marks']}<br/>
    4. Difficulty Level: {exam['difficulty_level']}<br/>
    """

    elements.append(Paragraph(instructions, styles['Normal']))
    elements.append(Spacer(1, 0.3 * inch))

    # -------- Questions --------
    for q in questions:
        elements.append(Paragraph(
            f"<b>{q['question_id']}. [{q['marks']} Marks]</b>",
            question_style
        ))

        elements.append(Paragraph(q['question_text'], question_style))

        elements.append(Paragraph("<b>Model Answer:</b>", styles['Normal']))

        elements.append(Paragraph(
            q['model_answer_text'] or "Answer not available.",
            answer_style
        ))

        elements.append(Spacer(1, 0.25 * inch))

    # -------- Footer --------
    elements.append(Spacer(1, 0.3 * inch))
    elements.append(Paragraph(
        f"<b>Total Marks: {exam['total_marks']}</b>",
        subtitle_style
    ))

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"{exam['exam_title'].replace(' ', '_')}_Question_Paper.pdf"
    )




# =====================================================
# STUDENT EXAM ACCESS (with date validation)
# =====================================================

# @app.route('/available_exams')
# def available_exams():
#     """Show available exams for students"""
#     if 'user_id' not in session or session.get('role') != 'Student':
#         flash('Access denied. Students only.', 'danger')
#         return redirect(url_for('login'))
    
#     conn = get_db_connection()
#     current_time = datetime.now()
    
#     exams = conn.execute('''
#         SELECT e.*, s.subject_name, c.class_name
#         FROM exams e
#         JOIN subjects s ON e.subject_id = s.id
#         JOIN classes c ON e.class_id = c.id
#         WHERE e.status = 'Approved' 
#         AND datetime(e.start_date) <= datetime(?)
#         AND datetime(e.end_date) >= datetime(?)
#     ''', (current_time, current_time)).fetchall()
    
#     conn.close()
    
#     return render_template('available_exams.html', exams=exams)

@app.route('/take_exam/<int:exam_id>')
def take_exam(exam_id):
    """Check if exam is accessible and redirect to exam page"""
    if 'user_id' not in session or session.get('role') != 'Student':
        flash('Access denied. Students only.', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    current_time = datetime.now()
    
    exam = conn.execute('''
        SELECT * FROM exams WHERE id = ? AND status = 'Approved'
    ''', (exam_id,)).fetchone()
    
    if not exam:
        flash('Exam not found', 'danger')
        return redirect(url_for('available_exams'))
    
    # Check if exam is within date range
    start_date = datetime.strptime(exam['start_date'], '%Y-%m-%d %H:%M:%S')
    end_date = datetime.strptime(exam['end_date'], '%Y-%m-%d %H:%M:%S')
    
    if current_time < start_date:
        flash('This exam has not started yet', 'warning')
        return redirect(url_for('available_exams'))
    
    if current_time > end_date:
        flash('This exam has ended', 'danger')
        return redirect(url_for('available_exams'))
    
    conn.close()
    
    # Redirect to exam taking page (implement separately)
    return redirect(url_for('exam_interface', exam_id=exam_id))   

#chatbot for students
@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message', '')

    groq_api_key = os.getenv('GROQ_API_KEY')
    if not groq_api_key:
        return jsonify({'error': 'GROQ_API_KEY not configured in .env'}), 500

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": "You are a helpful AI assistant specializing in exam and syllabus-related questions. Keep answers concise and helpful."},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.7,
        "max_tokens": 1000
    }

    response = requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        json=payload,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {groq_api_key}'
        },
        timeout=30
    )

    if response.status_code == 200:
        result = response.json()
        ai_response = result['choices'][0]['message']['content']
        return jsonify({'response': ai_response})
    else:
        return jsonify({'error': 'Failed to get AI response'}), 500 


# ==================== STUDENT FEEDBACK ROUTES ====================
@app.route('/student/submit_feedback/<int:exam_id>', methods=['GET', 'POST'])
@login_required
@student_required
def submit_feedback(exam_id):
    """Submit feedback for a completed exam"""
    conn = get_db_connection()
    
    # Get student profile
    student_profile = conn.execute(
        'SELECT id FROM student_profile WHERE user_id = ?',
        (session['user_id'],)
    ).fetchone()
    
    # Check if student has submitted this exam
    submission = conn.execute('''
        SELECT sa.id, e.exam_title, s.subject_name
        FROM student_answers sa
        JOIN exams e ON sa.exam_id = e.id
        JOIN subjects s ON e.subject_id = s.id
        WHERE sa.student_id = ? AND sa.exam_id = ?
        LIMIT 1
    ''', (student_profile['id'], exam_id)).fetchone()
    
    if not submission:
        flash('You have not submitted this exam yet!', 'warning')
        conn.close()
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        rating = request.form.get('rating')
        difficulty_rating = request.form.get('difficulty_rating')
        feedback_text = request.form.get('feedback_text')
        suggestions = request.form.get('suggestions', '')
        
        # Check if feedback already exists
        existing_feedback = conn.execute('''
            SELECT id FROM exam_feedback 
            WHERE student_id = ? AND exam_id = ?
        ''', (student_profile['id'], exam_id)).fetchone()
        
        cursor = conn.cursor()
        
        if existing_feedback:
            # Update existing feedback
            cursor.execute('''
                UPDATE exam_feedback 
                SET rating = ?, difficulty_rating = ?, feedback_text = ?, 
                    suggestions = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (rating, difficulty_rating, feedback_text, suggestions, existing_feedback['id']))
            flash('Feedback updated successfully!', 'success')
        else:
            # Insert new feedback
            cursor.execute('''
                INSERT INTO exam_feedback 
                (student_id, exam_id, rating, difficulty_rating, feedback_text, suggestions)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (student_profile['id'], exam_id, rating, difficulty_rating, feedback_text, suggestions))
            flash('Feedback submitted successfully!', 'success')
        
        # Log activity
        cursor.execute('''
            INSERT INTO activity_logs (user_id, action)
            VALUES (?, ?)
        ''', (session['user_id'], f'Submitted feedback for exam ID: {exam_id}'))
        
        conn.commit()
        conn.close()
        return redirect(url_for('my_submissions'))
    
    # GET - Check if feedback already exists
    existing_feedback = conn.execute('''
        SELECT * FROM exam_feedback 
        WHERE student_id = ? AND exam_id = ?
    ''', (student_profile['id'], exam_id)).fetchone()
    
    # Get exam details
    exam = conn.execute('''
        SELECT e.*, s.subject_name, c.class_name
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        JOIN classes c ON e.class_id = c.id
        WHERE e.id = ?
    ''', (exam_id,)).fetchone()
    
    conn.close()
    
    return render_template('student/submit_feedback.html', 
                         exam=exam, 
                         existing_feedback=existing_feedback)


@app.route('/student/my_feedback')
@login_required
@student_required
def my_feedback():
    """View all feedback submitted by student"""
    conn = get_db_connection()
    
    student_profile = conn.execute(
        'SELECT id FROM student_profile WHERE user_id = ?',
        (session['user_id'],)
    ).fetchone()
    
    feedbacks = conn.execute('''
        SELECT 
            ef.*,
            e.exam_title,
            s.subject_name,
            c.class_name
        FROM exam_feedback ef
        JOIN exams e ON ef.exam_id = e.id
        JOIN subjects s ON e.subject_id = s.id
        JOIN classes c ON e.class_id = c.id
        WHERE ef.student_id = ?
        ORDER BY ef.submitted_at DESC
    ''', (student_profile['id'],)).fetchall()
    
    conn.close()
    
    return render_template('student/my_feedback.html', feedbacks=feedbacks)


# ==================== TEACHER FEEDBACK VIEW ROUTES ====================
@app.route('/teacher/view_feedback')
@login_required
@teacher_required
def view_feedback():
    """View all feedback for teacher's exams"""
    conn = get_db_connection()
    
    # Get all exams created by this teacher
    feedbacks = conn.execute('''
        SELECT 
            ef.*,
            e.exam_title,
            e.id as exam_id,
            s.subject_name,
            c.class_name,
            u.full_name as student_name,
            sp.roll_no
        FROM exam_feedback ef
        JOIN exams e ON ef.exam_id = e.id
        JOIN student_profile sp ON ef.student_id = sp.id
        JOIN users u ON sp.user_id = u.id
        JOIN subjects s ON e.subject_id = s.id
        JOIN classes c ON e.class_id = c.id
        WHERE e.created_by = ?
        ORDER BY ef.submitted_at DESC
    ''', (session['user_id'],)).fetchall()
    
    # Get feedback statistics
    stats = conn.execute('''
        SELECT 
            COUNT(*) as total_feedback,
            AVG(ef.rating) as avg_rating,
            AVG(ef.difficulty_rating) as avg_difficulty
        FROM exam_feedback ef
        JOIN exams e ON ef.exam_id = e.id
        WHERE e.created_by = ?
    ''', (session['user_id'],)).fetchone()
    
    conn.close()
    
    return render_template('teacher/view_feedback.html', 
                         feedbacks=feedbacks, 
                         stats=stats)


@app.route('/teacher/exam_feedback/<int:exam_id>')
@login_required
@teacher_required
def exam_feedback(exam_id):
    """View feedback for a specific exam"""
    conn = get_db_connection()
    
    # Verify exam belongs to teacher
    exam = conn.execute('''
        SELECT e.*, s.subject_name, c.class_name
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        JOIN classes c ON e.class_id = c.id
        WHERE e.id = ? AND e.created_by = ?
    ''', (exam_id, session['user_id'])).fetchone()
    
    if not exam:
        flash('Exam not found or access denied', 'danger')
        conn.close()
        return redirect(url_for('view_feedback'))
    
    # Get all feedback for this exam
    feedbacks = conn.execute('''
        SELECT 
            ef.*,
            u.full_name as student_name,
            sp.roll_no
        FROM exam_feedback ef
        JOIN student_profile sp ON ef.student_id = sp.id
        JOIN users u ON sp.user_id = u.id
        WHERE ef.exam_id = ?
        ORDER BY ef.submitted_at DESC
    ''', (exam_id,)).fetchall()
    
    # Calculate statistics
    stats = {}
    if feedbacks:
        stats = {
            'total_feedback': len(feedbacks),
            'avg_rating': round(sum(f['rating'] for f in feedbacks) / len(feedbacks), 2),
            'avg_difficulty': round(sum(f['difficulty_rating'] for f in feedbacks) / len(feedbacks), 2),
            'rating_distribution': {
                5: len([f for f in feedbacks if f['rating'] == 5]),
                4: len([f for f in feedbacks if f['rating'] == 4]),
                3: len([f for f in feedbacks if f['rating'] == 3]),
                2: len([f for f in feedbacks if f['rating'] == 2]),
                1: len([f for f in feedbacks if f['rating'] == 1]),
            }
        }
    
    conn.close()
    
    return render_template('teacher/exam_feedback.html', 
                         exam=exam, 
                         feedbacks=feedbacks, 
                         stats=stats)


# ==================== ANSWER EVALUATION ROUTE ====================
@app.route('/student/submit_exam/<int:exam_id>', methods=['POST'])
@login_required
@student_required
def submit_exam(exam_id):
    """Submit exam answers and evaluate"""
    conn = get_db_connection()
    
    # Get student profile
    student_profile = conn.execute(
        'SELECT id FROM student_profile WHERE user_id = ?',
        (session['user_id'],)
    ).fetchone()
    
    # Check if already submitted
    existing_submission = conn.execute('''
        SELECT id FROM student_answers 
        WHERE student_id = ? AND exam_id = ?
    ''', (student_profile['id'], exam_id)).fetchone()
    
    if existing_submission:
        flash('You have already submitted this exam!', 'warning')
        conn.close()
        return redirect(url_for('dashboard'))
    
    # Get uploaded file
    answer_file = request.files.get('answer_file')
    
    if not answer_file or answer_file.filename == '':
        flash('Please upload an answer sheet!', 'danger')
        conn.close()
        return redirect(url_for('upload_answer', exam_id=exam_id))
    
    if not answer_file.filename.endswith('.pdf'):
        flash('Only PDF files are allowed!', 'danger')
        conn.close() 
        return redirect(url_for('upload_answer', exam_id=exam_id))
    
    try:
        # Save uploaded PDF
        upload_dir = STUDENT_ANSWERS_FOLDER
        
        filename = secure_filename(answer_file.filename)
        timestamp = int(time.time())
        file_path = os.path.join(upload_dir, f"{session['user_id']}_{timestamp}_{filename}")
        answer_file.save(file_path)
        
        # Extract text from PDF
        extracted_text = extract_text_from_pdf(file_path)
        
        # Get all questions for this exam
        questions = conn.execute('''
            SELECT id, question_id, question_text, model_answer_text, marks
            FROM model_answers
            WHERE exam_id = ?
            ORDER BY question_id
        ''', (exam_id,)).fetchall()
        
        cursor = conn.cursor()
        total_scored = 0
        total_possible = 0
        
        for question in questions:
            # Simple answer matching (you can enhance this)
            student_answer = extract_answer_for_question(extracted_text, question['question_id'])
            
            # Calculate similarity percentage
            score_percentage = calculate_answer_similarity(
                student_answer, 
                question['model_answer_text']
            )
            
            awarded_marks = round((score_percentage / 100) * question['marks'], 2)
            total_scored += awarded_marks
            total_possible += question['marks']
            
            # Insert student answer
            cursor.execute('''
                INSERT INTO student_answers 
                (student_id, exam_id, question_id, answer_text, file_path, status)
                VALUES (?, ?, ?, ?, ?, 'Attempted')
            ''', (student_profile['id'], exam_id, question['question_id'], 
                  student_answer, file_path))
            
            student_answer_id = cursor.lastrowid
            
            # Insert evaluation result
            cursor.execute('''
                INSERT INTO evaluation_results
                (student_answer_id, model_answer_id, total_score, evaluated_by_ai)
                VALUES (?, ?, ?, 1)
            ''', (student_answer_id, question['id'], awarded_marks))
            
            evaluation_id = cursor.lastrowid
            
            # Generate feedback
            feedback_text = generate_feedback(score_percentage, student_answer, question['model_answer_text'])
            
            cursor.execute('''
                INSERT INTO feedback
                (evaluation_id, feedback_text)
                VALUES (?, ?)
            ''', (evaluation_id, feedback_text))
        
        # Log activity
        cursor.execute('''
            INSERT INTO activity_logs (user_id, action)
            VALUES (?, ?)
        ''', (session['user_id'], f'Submitted exam ID: {exam_id}'))
        
        conn.commit()
        conn.close()
        
        flash(f'Exam submitted successfully! You scored {total_scored}/{total_possible} marks', 'success')
        return redirect(url_for('submit_feedback', exam_id=exam_id))
        
    except Exception as e:
        flash(f'Error submitting exam: {str(e)}', 'danger')
        if os.path.exists(file_path):
            os.remove(file_path)
        conn.close()
        return redirect(url_for('upload_answer', exam_id=exam_id))


# ==================== HELPER FUNCTIONS FOR EVALUATION ====================
# (Defined later in the file — enhanced versions with multiple scoring metrics)


# Update my_submissions route to include feedback link
@app.route('/student/my_submissions')
@login_required
@student_required
def my_submissions():

    conn = get_db_connection()

    student_profile = conn.execute(
        'SELECT id FROM student_profile WHERE user_id = ?',
        (session['user_id'],)
    ).fetchone()

    submissions = conn.execute('''
        SELECT 
            e.id as exam_id,
            e.exam_title,
            s.subject_name,
            c.class_name,
            COUNT(DISTINCT sa.id) as questions_attempted,
            SUM(er.total_score) as total_scored,
            e.total_marks,
            MAX(sa.uploaded_at) as uploaded_at,
            MAX(sa.file_path) as file_name,
            CASE 
                WHEN SUM(er.total_score) IS NOT NULL THEN 'Evaluated'
                ELSE 'Pending'
            END as status,
            SUM(er.total_score) as score,
            (SELECT COUNT(*) FROM exam_feedback ef 
             WHERE ef.student_id = ? AND ef.exam_id = e.id) as feedback_given
        FROM student_answers sa
        JOIN exams e ON sa.exam_id = e.id
        JOIN subjects s ON e.subject_id = s.id
        JOIN classes c ON e.class_id = c.id
        LEFT JOIN evaluation_results er 
            ON sa.id = er.student_answer_id
        WHERE sa.student_id = ?
        GROUP BY e.id
        ORDER BY uploaded_at DESC
    ''', (
        student_profile['id'],
        student_profile['id']
    )).fetchall()

    conn.close()

    return render_template(
        'student/submissions.html',
        submissions=submissions
    )


@app.route('/student/download_submission/<int:exam_id>')
@login_required
@student_required
def download_submission(exam_id):
    """Download the latest uploaded answer sheet for the given exam by the current student"""
    conn = get_db_connection()
    student_profile = conn.execute(
        'SELECT id FROM student_profile WHERE user_id = ?',
        (session['user_id'],)
    ).fetchone()

    if not student_profile:
        conn.close()
        flash('Student profile not found.', 'danger')
        return redirect(url_for('dashboard'))

    row = conn.execute('''
        SELECT file_path FROM student_answers
        WHERE student_id = ? AND exam_id = ? AND file_path IS NOT NULL
        ORDER BY uploaded_at DESC
        LIMIT 1
    ''', (student_profile['id'], exam_id)).fetchone()

    conn.close()

    if not row or not row['file_path']:
        flash('No uploaded answer sheet available for download.', 'warning')
        return redirect(url_for('my_submissions'))

    file_path = row['file_path']
    if not os.path.exists(file_path):
        flash('File not found on server.', 'danger')
        return redirect(url_for('my_submissions'))

    return send_file(file_path, as_attachment=True, download_name=os.path.basename(file_path))

# ==================== STUDENT EXAM SUBMISSION ROUTES ====================

@app.route('/student/available_exams')
@login_required
@student_required
def available_exams():
    """Show all available exams for student"""
    conn = get_db_connection()
    
    # Get student profile
    student_profile = conn.execute(
        'SELECT id, class_id FROM student_profile WHERE user_id = ?',
        (session['user_id'],)
    ).fetchone()
    
    if not student_profile:
        flash('Student profile not found!', 'danger')
        conn.close()
        return redirect(url_for('dashboard'))
    
    current_time = datetime.now()
    
    # Get all approved exams for student's class
    exams = conn.execute('''
        SELECT 
            e.*,
            s.subject_name,
            c.class_name,
            COUNT(ma.id) as total_questions,
            (SELECT COUNT(*) FROM student_answers sa 
             WHERE sa.exam_id = e.id AND sa.student_id = ?) as is_submitted
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        JOIN classes c ON e.class_id = c.id
        LEFT JOIN model_answers ma ON e.id = ma.exam_id
        WHERE e.class_id = ? 
        AND e.status = 'Approved'
      
        GROUP BY e.id
        ORDER BY e.start_date DESC
    ''', (student_profile['id'], student_profile['class_id'])).fetchall()
    
    conn.close()
    
    return render_template('student/available_exams.html', exams=exams)


@app.route('/student/exam_details/<int:exam_id>')
@login_required
@student_required
def exam_details(exam_id):
    """View exam details before submission"""
    conn = get_db_connection()
    
    # Get student profile
    student_profile = conn.execute(
        'SELECT id, class_id FROM student_profile WHERE user_id = ?',
        (session['user_id'],)
    ).fetchone()
    
    # Get exam details
    exam = conn.execute('''
        SELECT 
            e.*,
            s.subject_name,
            c.class_name,
            COUNT(ma.id) as total_questions
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        JOIN classes c ON e.class_id = c.id
        LEFT JOIN model_answers ma ON e.id = ma.exam_id
        WHERE e.id = ? AND e.class_id = ?
        GROUP BY e.id
    ''', (exam_id, student_profile['class_id'])).fetchone()
    
    if not exam:
        flash('Exam not found or not accessible!', 'danger')
        conn.close()
        return redirect(url_for('available_exams'))
    
    # Check if already submitted
    submission = conn.execute('''
        SELECT id, uploaded_at FROM student_answers 
        WHERE student_id = ? AND exam_id = ?
        LIMIT 1
    ''', (student_profile['id'], exam_id)).fetchone()
    
    # Get exam questions (just count and marks, not actual questions)
    question_stats = conn.execute('''
        SELECT 
            question_type,
            COUNT(*) as count,
            SUM(marks) as total_marks
        FROM model_answers
        WHERE exam_id = ?
        GROUP BY question_type
    ''', (exam_id,)).fetchall()
    
    conn.close()
    
    return render_template('student/exam_details.html', 
                         exam=exam, 
                         submission=submission,
                         question_stats=question_stats)


@app.route('/student/download_question_paper1/<int:exam_id>')
@login_required
@student_required
def download_question_paper1(exam_id):
    """Download question paper PDF (without model answers)"""
    conn = get_db_connection()
    
    # Get student profile
    student_profile = conn.execute(
        'SELECT class_id FROM student_profile WHERE user_id = ?',
        (session['user_id'],)
    ).fetchone()
    
    # Get exam details
    exam = conn.execute('''
        SELECT e.*, s.subject_name, c.class_name
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        JOIN classes c ON e.class_id = c.id
        WHERE e.id = ? AND e.class_id = ? AND e.status = 'Approved'
    ''', (exam_id, student_profile['class_id'])).fetchone()
    
    if not exam:
        flash('Question paper not found!', 'danger')
        conn.close()
        return redirect(url_for('available_exams'))
    
    # Get questions (without model answers)
    questions = conn.execute('''
        SELECT question_id, question_text, marks, question_type
        FROM model_answers 
        WHERE exam_id = ?
        ORDER BY question_id
    ''', (exam_id,)).fetchall()
    
    conn.close()
    
    # Generate PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch
    )
    
    styles = getSampleStyleSheet()
    elements = []
    
    # Custom Styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#666666'),
        spaceAfter=20,
        alignment=TA_CENTER
    )
    
    info_style = ParagraphStyle(
        'InfoStyle',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=15,
        alignment=TA_LEFT
    )
    
    question_header_style = ParagraphStyle(
        'QuestionHeader',
        parent=styles['Normal'],
        fontSize=11,
        fontName='Helvetica-Bold',
        spaceAfter=8,
        textColor=colors.HexColor('#2c3e50')
    )
    
    question_style = ParagraphStyle(
        'QuestionStyle',
        parent=styles['Normal'],
        fontSize=11,
        leading=16,
        spaceAfter=10,
        leftIndent=10
    )
    
    # Header Section
    elements.append(Paragraph(f"<b>{exam['exam_title']}</b>", title_style))
    elements.append(Paragraph(
        f"{exam['subject_name']} | {exam['class_name']}", 
        subtitle_style
    ))
    elements.append(Spacer(1, 0.2*inch))
    
    # Exam Information Table
    info_data = [
        ['Total Marks:', str(exam['total_marks']), 'Duration:', f"{exam['duration_minutes']} minutes"],
        ['Date:', exam['start_date'][:10], 'Difficulty:', exam['difficulty_level']]
    ]
    
    info_table = Table(info_data, colWidths=[1.5*inch, 2*inch, 1.5*inch, 2*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
    ]))
    
    elements.append(info_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Instructions Box
    instructions = """
    <b>INSTRUCTIONS:</b><br/>
    1. Read all questions carefully before answering.<br/>
    2. Answer all questions in the space provided or on separate answer sheets.<br/>
    3. Write clearly and legibly.<br/>
    4. Each question carries marks as indicated.<br/>
    5. Upload your answer sheet as a PDF file after completion.<br/>
    6. Ensure all pages are properly scanned and uploaded before the deadline.
    """
    
    instruction_box = Paragraph(instructions, info_style)
    elements.append(instruction_box)
    elements.append(Spacer(1, 0.3*inch))
    
    # Divider Line
    elements.append(Table([['']], colWidths=[7*inch], rowHeights=[2]))
    elements[-1].setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, 0), 2, colors.HexColor('#3498db'))
    ]))
    elements.append(Spacer(1, 0.2*inch))
    
    # Questions Section
    for idx, q in enumerate(questions, 1):
        # Question Header with Number and Marks
        q_header = f"<b>Q{idx}. [{q['marks']} Marks] {q['question_type']}</b>"
        elements.append(Paragraph(q_header, question_header_style))
        
        # Question Text
        q_text = q['question_text']
        elements.append(Paragraph(q_text, question_style))
        
        # Answer Space (lines for students to write)
        elements.append(Spacer(1, 0.15*inch))
        
        # Draw answer lines based on marks
        num_lines = min(int(q['marks'] / 2) + 2, 8)  # More marks = more lines
        for _ in range(num_lines):
            line_table = Table([['_' * 120]], colWidths=[6.5*inch])
            line_table.setStyle(TableStyle([
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.grey),
                ('FONTSIZE', (0, 0), (-1, -1), 8)
            ]))
            elements.append(line_table)
            elements.append(Spacer(1, 0.05*inch))
        
        elements.append(Spacer(1, 0.3*inch))
    
    # Footer
    elements.append(Spacer(1, 0.3*inch))
    footer_data = [
        ['', 'END OF QUESTION PAPER', ''],
        ['', f'Total Marks: {exam["total_marks"]}', '']
    ]
    
    footer_table = Table(footer_data, colWidths=[2*inch, 3*inch, 2*inch])
    footer_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2c3e50'))
    ]))
    
    elements.append(footer_table)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    # Log download activity
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO activity_logs (user_id, action)
        VALUES (?, ?)
    ''', (session['user_id'], f'Downloaded question paper: {exam["exam_title"]}'))
    conn.commit()
    conn.close()
    
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"{exam['exam_title'].replace(' ', '_')}_Question_Paper.pdf"
    )

"""
Replacement for the upload_answer_sheet Flask route.
Drop this into your routes file — it uses pdf_llm_extractor instead of
the old OCR pipeline.
"""

"""
Replacement for the upload_answer_sheet Flask route.
Drop this into your routes file — it uses pdf_llm_extractor instead of
the old OCR pipeline.
"""

@app.route('/student/upload_answer_sheet/<int:exam_id>', methods=['GET', 'POST'])
@login_required
@student_required
def upload_answer_sheet(exam_id):
    """Upload and auto-evaluate a student answer sheet via Claude Vision."""
    conn = get_db_connection()

    # ── Fetch student & exam ──────────────────────────────────────────────────
    student_profile = conn.execute(
        'SELECT id, class_id FROM student_profile WHERE user_id = ?',
        (session['user_id'],)
    ).fetchone()

    exam = conn.execute('''
        SELECT e.*, s.subject_name, c.class_name
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        JOIN classes c ON e.class_id = c.id
        WHERE e.id = ? AND e.class_id = ?
    ''', (exam_id, student_profile['class_id'])).fetchone()

    if not exam:
        flash('Exam not found!', 'danger')
        conn.close()
        return redirect(url_for('available_exams'))

    # ── Guard: already submitted ──────────────────────────────────────────────
    existing = conn.execute(
        'SELECT id FROM student_answers WHERE student_id = ? AND exam_id = ? LIMIT 1',
        (student_profile['id'], exam_id)
    ).fetchone()

    if existing:
        flash('You have already submitted this exam!', 'warning')
        conn.close()
        return redirect(url_for('available_exams'))

    # ── POST ──────────────────────────────────────────────────────────────────
    if request.method == 'POST':
        answer_file = request.files.get('answer_file')

        if not answer_file or answer_file.filename == '':
            flash('Please upload an answer sheet!', 'danger')
            conn.close()
            return redirect(request.url)

        if not answer_file.filename.lower().endswith('.pdf'):
            flash('Only PDF files are allowed!', 'danger')
            conn.close()
            return redirect(request.url)

        file_path = None
        try:
            # ── Save PDF ──────────────────────────────────────────────────────
            upload_dir = STUDENT_ANSWERS_FOLDER

            filename  = secure_filename(answer_file.filename)
            timestamp = int(time.time())
            file_path = os.path.join(
                upload_dir,
                f"student_{session['user_id']}_exam_{exam_id}_{timestamp}.pdf"
            )
            answer_file.save(file_path)

            # ── Fetch questions ───────────────────────────────────────────────
            questions = conn.execute('''
                SELECT id, question_id, question_text, model_answer_text, marks
                FROM model_answers
                WHERE exam_id = ?
                ORDER BY question_id
            ''', (exam_id,)).fetchall()

            if not questions:
                flash('No questions found for this exam.', 'danger')
                os.remove(file_path)
                conn.close()
                return redirect(request.url)

            # ── LLM pipeline (extract + evaluate in one call) ─────────────────
            from pdf_llm_extractor import process_answer_sheet

            results = process_answer_sheet(
                pdf_path=file_path,
                questions=[dict(q) for q in questions],
            )

            # ── Persist results ───────────────────────────────────────────────
            cursor = conn.cursor()
            total_scored   = 0.0
            total_possible = 0.0

            for res in results:
                total_scored   += res['awarded_marks']
                total_possible += res['max_marks']

                # student_answers row
                cursor.execute('''
                    INSERT INTO student_answers
                        (student_id, exam_id, question_id, answer_text,
                         file_path, status, uploaded_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    student_profile['id'],
                    exam_id,
                    res['question_id'],
                    res['student_answer'][:5000],   # cap to column limit
                    file_path,
                    res['status'],
                ))
                student_answer_id = cursor.lastrowid

                # evaluation_results row
                cursor.execute('''
                    INSERT INTO evaluation_results
                        (student_answer_id, model_answer_id,
                         content_score, concept_score, grammar_score,
                         total_score, evaluated_by_ai, evaluated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                ''', (
                    student_answer_id,
                    res['model_answer_id'],
                    res['score_percentage'],
                    res['score_percentage'],
                    85.0,                           # grammar placeholder
                    res['awarded_marks'],
                ))
                evaluation_id = cursor.lastrowid

                # feedback row
                missing_kw = ', '.join(res['missing_concepts'])
                cursor.execute('''
                    INSERT INTO feedback
                        (evaluation_id, feedback_text, missing_keywords, created_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ''', (evaluation_id, res['feedback'], missing_kw))

            # activity log
            cursor.execute(
                'INSERT INTO activity_logs (user_id, action) VALUES (?, ?)',
                (session['user_id'], f'Submitted exam: {exam["exam_title"]}')
            )

            conn.commit()
            conn.close()

            percentage = round((total_scored / total_possible) * 100, 2) if total_possible else 0
            flash(
                f'✅ Exam submitted! Score: {total_scored:.1f}/{total_possible:.1f} ({percentage}%)',
                'success'
            )
            return redirect(url_for('submission_result', exam_id=exam_id))

        except Exception as e:
            flash(f'❌ Error processing answer sheet: {str(e)}', 'danger')
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            conn.close()
            return redirect(request.url)

    # ── GET ───────────────────────────────────────────────────────────────────
    conn.close()
    return render_template('student/upload_answer_sheet.html', exam=exam)
# @app.route('/student/upload_answer_sheet/<int:exam_id>', methods=['GET', 'POST'])
# @login_required
# @student_required
# def upload_answer_sheet(exam_id):
#     """Upload answer sheet for evaluation"""
#     conn = get_db_connection()
    
#     # Get student profile
#     student_profile = conn.execute(
#         'SELECT id, class_id FROM student_profile WHERE user_id = ?',
#         (session['user_id'],)
#     ).fetchone()
    
#     # Get exam details
#     exam = conn.execute('''
#         SELECT e.*, s.subject_name, c.class_name
#         FROM exams e
#         JOIN subjects s ON e.subject_id = s.id
#         JOIN classes c ON e.class_id = c.id
#         WHERE e.id = ? AND e.class_id = ?
#     ''', (exam_id, student_profile['class_id'])).fetchone()
    
#     if not exam:
#         flash('Exam not found!', 'danger')
#         conn.close()
#         return redirect(url_for('available_exams'))
    
#     # Check if already submitted
#     existing_submission = conn.execute('''
#         SELECT id FROM student_answers 
#         WHERE student_id = ? AND exam_id = ?
#         LIMIT 1
#     ''', (student_profile['id'], exam_id)).fetchone()
    
#     if existing_submission:
#         flash('You have already submitted this exam!', 'warning')
#         conn.close()
#         return redirect(url_for('available_exams'))
    
#     if request.method == 'POST':
#         answer_file = request.files.get('answer_file')
        
#         if not answer_file or answer_file.filename == '':
#             flash('Please upload an answer sheet!', 'danger')
#             conn.close()
#             return redirect(request.url)
        
#         if not answer_file.filename.lower().endswith('.pdf'):
#             flash('Only PDF files are allowed!', 'danger')
#             conn.close()
#             return redirect(request.url)
        
#         try:
#             # Save uploaded PDF
#             upload_dir = 'uploads/student_answers'
#             os.makedirs(upload_dir, exist_ok=True)
            
#             filename = secure_filename(answer_file.filename)
#             timestamp = int(time.time())
#             file_path = os.path.join(upload_dir, f"student_{session['user_id']}_exam_{exam_id}_{timestamp}.pdf")
#             answer_file.save(file_path)
            
#             # Extract text from PDF
#             from pdf_text_extractor import extract_text_from_pdf
#             full_extracted_text = extract_text_from_pdf(file_path)
            
#             if not full_extracted_text or len(full_extracted_text.strip()) < 50:
#                 flash('Could not extract text from PDF. Please ensure your answer sheet is readable.', 'warning')
#                 os.remove(file_path)
#                 conn.close()
#                 return redirect(request.url)
            
#             # Get all questions for this exam
#             questions = conn.execute('''
#                 SELECT id, question_id, question_text, model_answer_text, marks
#                 FROM model_answers
#                 WHERE exam_id = ?
#                 ORDER BY question_id
#             ''', (exam_id,)).fetchall()
            
#             # Parse answers from PDF text - extract individual answers
#             parsed_answers = parse_student_answers(full_extracted_text, len(questions))
            
#             cursor = conn.cursor()
#             total_scored = 0
#             total_possible = 0
#             questions_evaluated = 0
            
#             for idx, question in enumerate(questions):
#                 # Get student's answer for this specific question
#                 question_number = idx + 1
#                 student_answer = parsed_answers.get(question_number, '')
                
#                 # If we couldn't parse by number, try matching by question_id
#                 if not student_answer:
#                     student_answer = extract_answer_by_question_id(full_extracted_text, question['question_id'])
                
#                 # Calculate similarity percentage only if answer exists
#                 if student_answer.strip():
#                     score_percentage = calculate_answer_similarity(
#                         student_answer, 
#                         question['model_answer_text']
#                     )
                    
#                     # Calculate awarded marks
#                     awarded_marks = max(0, round((score_percentage / 100) * question['marks'], 2))
#                     status = 'Attempted'
#                 else:
#                     score_percentage = 0
#                     awarded_marks = 0
#                     status = 'Not Attempted'
                
#                 total_scored += awarded_marks
#                 total_possible += question['marks']
                
#                 # Insert student answer
#                 cursor.execute('''
#                     INSERT INTO student_answers 
#                     (student_id, exam_id, question_id, answer_text, file_path, status, uploaded_at)
#                     VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
#                 ''', (student_profile['id'], exam_id, question['question_id'], 
#                       student_answer[:5000], file_path, status))  # Limit to 5000 chars
                
#                 student_answer_id = cursor.lastrowid
                
#                 # Insert evaluation result
#                 cursor.execute('''
#                     INSERT INTO evaluation_results
#                     (student_answer_id, model_answer_id, content_score, concept_score, 
#                      grammar_score, total_score, evaluated_by_ai, evaluated_at)
#                     VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
#                 ''', (student_answer_id, question['id'], score_percentage, 
#                       score_percentage, 85.0, awarded_marks))
                
#                 evaluation_id = cursor.lastrowid
#                 questions_evaluated += 1
                
#                 # Generate and insert feedback
#                 feedback_text = generate_feedback(score_percentage, student_answer, question['model_answer_text'])
#                 missing_keywords = find_missing_keywords(student_answer, question['model_answer_text'])
                
#                 cursor.execute('''
#                     INSERT INTO feedback
#                     (evaluation_id, feedback_text, missing_keywords, created_at)
#                     VALUES (?, ?, ?, CURRENT_TIMESTAMP)
#                 ''', (evaluation_id, feedback_text, missing_keywords))
            
#             # Log activity
#             cursor.execute('''
#                 INSERT INTO activity_logs (user_id, action)
#                 VALUES (?, ?)
#             ''', (session['user_id'], f'Submitted exam: {exam["exam_title"]}'))
            
#             conn.commit()
#             conn.close()
            
#             percentage = round((total_scored / total_possible) * 100, 2) if total_possible > 0 else 0
            
#             flash(f'✅ Exam submitted successfully! Score: {total_scored}/{total_possible} ({percentage}%)', 'success')
#             return redirect(url_for('submission_result', exam_id=exam_id))
            
#         except Exception as e:
#             flash(f'❌ Error processing answer sheet: {str(e)}', 'danger')
#             if 'file_path' in locals() and os.path.exists(file_path):
#                 os.remove(file_path)
#             conn.close()
#             return redirect(request.url)
    
#     # GET request
#     conn.close()
#     return render_template('student/upload_answer_sheet.html', exam=exam)

@app.route('/student/submission_result/<int:exam_id>')
@login_required
@student_required
def submission_result(exam_id):
    """View submission results after evaluation"""
    conn = get_db_connection()
    
    # Get student profile
    student_profile = conn.execute(
        'SELECT id FROM student_profile WHERE user_id = ?',
        (session['user_id'],)
    ).fetchone()
    
    # Get exam details
    exam = conn.execute('''
        SELECT e.*, s.subject_name, c.class_name
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        JOIN classes c ON e.class_id = c.id
        WHERE e.id = ?
    ''', (exam_id,)).fetchone()
    
    # Get submission results
    results = conn.execute('''
        SELECT 
            sa.question_id,
            sa.answer_text,
            sa.status,
            sa.uploaded_at,
            ma.question_text,
            ma.model_answer_text,
            ma.marks as max_marks,
            er.total_score,
            er.content_score,
            er.concept_score,
            er.grammar_score,
            f.feedback_text,
            f.missing_keywords
        FROM student_answers sa
        JOIN model_answers ma ON sa.question_id = ma.question_id AND sa.exam_id = ma.exam_id
        LEFT JOIN evaluation_results er ON sa.id = er.student_answer_id
        LEFT JOIN feedback f ON er.id = f.evaluation_id
        WHERE sa.student_id = ? AND sa.exam_id = ?
        ORDER BY sa.question_id
    ''', (student_profile['id'], exam_id)).fetchall()
    
    # Calculate total score
    total_scored = sum(r['total_score'] or 0 for r in results)
    total_possible = exam['total_marks']
    percentage = round((total_scored / total_possible) * 100, 2) if total_possible > 0 else 0
    
    conn.close()
    
    return render_template('student/submission_result.html', 
                         exam=exam, 
                         results=results,
                         total_scored=total_scored,
                         total_possible=total_possible,
                         percentage=percentage)


# ==================== HELPER FUNCTIONS FOR TEXT EXTRACTION ====================

# ==================== IMPROVED ANSWER EXTRACTION FUNCTIONS ====================

def parse_student_answers(full_text, total_questions):
    """
    Parse student answers from PDF text by detecting question patterns.
    Supports multiple formats: Q1, 1), 1., Question 1, etc.
    """
    import re
    
    answers = {}
    
    # Clean up the text
    text = re.sub(r'\s+', ' ', full_text)  # Remove extra whitespace
    
    # Try multiple question patterns
    patterns = [
        # Pattern 1: Q1, Q2, etc.
        r'Q(\d+)[:\.\)]\s*(.+?)(?=Q\d+[:\.\)]|$)',
        # Pattern 2: 1), 2), etc.
        r'(\d+)\)\s*(.+?)(?=\d+\)|$)',
        # Pattern 3: 1., 2., etc.
        r'(\d+)\.\s*(.+?)(?=\d+\.|$)',
        # Pattern 4: Question 1, Question 2, etc.
        r'Question\s+(\d+)[:\.]?\s*(.+?)(?=Question\s+\d+|$)',
        # Pattern 5: Ans 1, Ans 2, etc.
        r'(?:Ans|Answer)\s*(\d+)[:\.]?\s*(.+?)(?=(?:Ans|Answer)\s*\d+|$)',
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE | re.DOTALL)
        
        for match in matches:
            question_num = int(match.group(1))
            answer_text = match.group(2).strip()
            
            # Only store if we haven't found this question yet or if this answer is longer
            if question_num not in answers or len(answer_text) > len(answers.get(question_num, '')):
                # Clean the answer text
                answer_text = clean_answer_text(answer_text)
                answers[question_num] = answer_text
        
        # If we found answers with this pattern, stop trying other patterns
        if answers:
            break
    
    # If no pattern matched, try to split by common delimiters
    if not answers:
        answers = split_by_delimiters(text, total_questions)
    
    return answers


def extract_answer_by_question_id(full_text, question_id):
    """
    Extract answer for a specific question_id (like Q1, Q2, etc.)
    """
    import re
    
    # Remove 'Q' prefix if exists
    q_num = question_id.replace('Q', '').replace('q', '').strip()
    
    # Try multiple patterns specific to this question
    patterns = [
        rf'(?:Q|q){q_num}[:\.\)]\s*(.+?)(?=(?:Q|q)\d+[:\.\)]|$)',
        rf'{q_num}\)\s*(.+?)(?=\d+\)|$)',
        rf'{q_num}\.\s*(.+?)(?=\d+\.|$)',
        rf'Question\s+{q_num}[:\.]?\s*(.+?)(?=Question\s+\d+|$)',
        rf'(?:Ans|Answer)\s*{q_num}[:\.]?\s*(.+?)(?=(?:Ans|Answer)\s*\d+|$)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, full_text, re.IGNORECASE | re.DOTALL)
        if match:
            answer = match.group(1).strip()
            return clean_answer_text(answer)
    
    return ""


def clean_answer_text(text):
    """
    Clean extracted answer text
    """
    import re
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove common artifacts
    text = re.sub(r'_{3,}', '', text)  # Remove underscores (answer lines)
    text = re.sub(r'-{3,}', '', text)  # Remove dashes
    
    # Remove page numbers
    text = re.sub(r'Page\s+\d+', '', text, flags=re.IGNORECASE)
    
    # Limit length
    text = text[:3000]  # Limit to 3000 characters
    
    return text.strip()


def split_by_delimiters(text, total_questions):
    """
    Fallback method: Split text into equal parts if no pattern detected
    """
    # Remove common headers/footers
    import re
    text = re.sub(r'Page\s+\d+', '', text, flags=re.IGNORECASE)
    
    # Split text into approximately equal parts
    text_length = len(text)
    chunk_size = text_length // total_questions if total_questions > 0 else text_length
    
    answers = {}
    for i in range(total_questions):
        start = i * chunk_size
        end = start + chunk_size if i < total_questions - 1 else text_length
        
        chunk = text[start:end].strip()
        if chunk:
            answers[i + 1] = clean_answer_text(chunk)
    
    return answers


def calculate_answer_similarity(student_answer, model_answer):
    """
    Calculate similarity percentage between student and model answer.
    Enhanced version with multiple scoring metrics.
    """
    if not student_answer or not model_answer:
        return 0
    
    # Convert to lowercase
    student_lower = student_answer.lower()
    model_lower = model_answer.lower()
    
    # 1. Word-based Jaccard Similarity (40% weight)
    student_words = set(word for word in student_lower.split() if len(word) > 2)
    model_words = set(word for word in model_lower.split() if len(word) > 2)
    
    # Remove common stop words
    stop_words = {
        'the', 'is', 'at', 'which', 'on', 'a', 'an', 'and', 'or', 'but', 
        'in', 'with', 'to', 'for', 'of', 'as', 'by', 'from', 'this', 'that',
        'are', 'was', 'were', 'been', 'be', 'have', 'has', 'had', 'do', 'does',
        'did', 'will', 'would', 'should', 'could', 'may', 'might', 'can'
    }
    
    student_words = student_words - stop_words
    model_words = model_words - stop_words
    
    if not model_words:
        return 0
    
    # Jaccard similarity
    intersection = student_words.intersection(model_words)
    union = student_words.union(model_words)
    jaccard_score = (len(intersection) / len(union)) * 100 if union else 0
    
    # 2. Key Phrase Matching (30% weight)
    key_phrases = extract_key_phrases(model_answer)
    phrase_matches = sum(1 for phrase in key_phrases if phrase.lower() in student_lower)
    phrase_score = (phrase_matches / len(key_phrases)) * 100 if key_phrases else 0
    
    # 3. Important Keywords Matching (20% weight)
    important_words = find_important_words(model_answer)
    keyword_matches = sum(1 for word in important_words if word.lower() in student_lower)
    keyword_score = (keyword_matches / len(important_words)) * 100 if important_words else 0
    
    # 4. Length Adequacy (10% weight)
    length_ratio = len(student_answer) / len(model_answer) if model_answer else 0
    if length_ratio >= 0.7:
        length_score = 100
    elif length_ratio >= 0.5:
        length_score = 80
    elif length_ratio >= 0.3:
        length_score = 60
    else:
        length_score = 40
    
    # Calculate weighted final score
    final_score = (
        (jaccard_score * 0.4) +
        (phrase_score * 0.3) +
        (keyword_score * 0.2) +
        (length_score * 0.1)
    )
    
    return round(min(100, final_score), 2)


def extract_key_phrases(text):
    """
    Extract important phrases (sentences or clauses) from model answer
    """
    import re
    
    # Split by sentence delimiters
    sentences = re.split(r'[.!?;]', text)
    
    # Filter sentences: keep those that are substantial
    key_phrases = [
        s.strip() for s in sentences 
        if len(s.strip()) > 20 and len(s.strip().split()) >= 4
    ]
    
    # Return top 5 longest phrases
    key_phrases.sort(key=len, reverse=True)
    return key_phrases[:5]


def find_important_words(text):
    """
    Extract important words from text (longer words, likely to be domain-specific)
    """
    import re
    
    # Split into words
    words = re.findall(r'\b[a-z]+\b', text.lower())
    
    # Filter: words longer than 5 characters (likely important)
    important = [w for w in words if len(w) > 5]
    
    # Remove duplicates while preserving order
    seen = set()
    unique_important = []
    for word in important:
        if word not in seen:
            seen.add(word)
            unique_important.append(word)
    
    return unique_important[:15]  # Top 15 important words


def find_missing_keywords(student_answer, model_answer):
    """
    Find important keywords missing in student answer
    """
    if not student_answer or not model_answer:
        return ""
    
    # Get important words from model answer
    model_important = set(find_important_words(model_answer))
    
    # Get words from student answer
    student_words = set(word.lower() for word in student_answer.split() if len(word) > 5)
    
    # Find missing important words
    missing = model_important - student_words
    
    # Return top 8 missing keywords
    return ', '.join(sorted(list(missing))[:8])


def generate_feedback(score_percentage, student_answer, model_answer):
    """
    Generate detailed feedback based on score and answer quality
    """
    feedback_parts = []
    
    # Overall performance feedback
    if score_percentage >= 90:
        feedback_parts.append("🌟 Excellent work! Your answer demonstrates comprehensive understanding of the topic.")
    elif score_percentage >= 75:
        feedback_parts.append("✅ Very good answer! You've covered most of the key concepts effectively.")
    elif score_percentage >= 60:
        feedback_parts.append("👍 Good effort! Your answer addresses the question but could be more detailed.")
    elif score_percentage >= 40:
        feedback_parts.append("⚠️ Satisfactory attempt. However, several important points are missing.")
    elif score_percentage >= 20:
        feedback_parts.append("❌ Needs significant improvement. Please review the topic thoroughly.")
    else:
        feedback_parts.append("❌ Insufficient answer. The response does not adequately address the question.")
    
    # Length-based feedback
    if not student_answer or len(student_answer.strip()) == 0:
        feedback_parts.append("No answer was provided for this question.")
    elif len(student_answer) < len(model_answer) * 0.3:
        feedback_parts.append("Your answer is too brief. Provide more detailed explanation with examples.")
    elif len(student_answer) < len(model_answer) * 0.5:
        feedback_parts.append("Consider expanding your answer with more details and explanations.")
    
    # Content coverage feedback
    missing_keywords = find_missing_keywords(student_answer, model_answer)
    if missing_keywords and score_percentage < 80:
        keywords_list = missing_keywords.split(',')[:5]  # Show top 5
        feedback_parts.append(f"Important concepts to include: {', '.join(keywords_list)}.")
    
    # Improvement suggestions
    if score_percentage < 60:
        feedback_parts.append("Suggestion: Review the model answer and identify key concepts you missed.")
    
    return " ".join(feedback_parts)


def extract_answer_for_question(full_text, question_id):
    """Extract answer for specific question from PDF text. Delegates to enhanced version."""
    return extract_answer_by_question_id(full_text, question_id)


# ==================== TEACHER: STUDENT RESULTS + PLAGIARISM ====================

def compute_similarity(text1, text2):
    """Compute cosine-like similarity between two texts using word overlap (no external libs needed)."""
    if not text1 or not text2:
        return 0.0
    stop = {'the','is','at','which','on','a','an','and','or','but','in','with',
            'to','for','of','it','this','that','are','was','were','be','been',
            'as','by','from','have','has','had','not','we','they','he','she'}
    def tokenize(t):
        words = t.lower().split()
        return [w.strip('.,;:!?()[]"\'') for w in words if w.strip('.,;:!?()[]"\'') not in stop and len(w) > 2]

    w1 = tokenize(text1)
    w2 = tokenize(text2)
    if not w1 or not w2:
        return 0.0

    # Build tf vectors
    vocab = set(w1) | set(w2)
    def tf(words):
        c = {}
        for w in words:
            c[w] = c.get(w, 0) + 1
        return c
    v1, v2 = tf(w1), tf(w2)

    dot = sum(v1.get(w, 0) * v2.get(w, 0) for w in vocab)
    norm1 = sum(x**2 for x in v1.values()) ** 0.5
    norm2 = sum(x**2 for x in v2.values()) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return round((dot / (norm1 * norm2)) * 100, 1)


@app.route('/teacher/student_results')
@login_required
@teacher_required
def teacher_student_results():
    """Show all student exam results for teacher's exams with plagiarism detection."""
    conn = get_db_connection()
    teacher_id = session['user_id']

    # Get all exams by this teacher
    exams = conn.execute('''
        SELECT e.id, e.exam_title, e.status, e.total_marks,
               s.subject_name, c.class_name, e.created_at
        FROM exams e
        JOIN subjects s ON e.subject_id = s.id
        JOIN classes c ON e.class_id = c.id
        WHERE e.created_by = ?
        ORDER BY e.created_at DESC
    ''', (teacher_id,)).fetchall()

    # Filter by exam if requested
    selected_exam_id = request.args.get('exam_id', type=int)

    exam_filter_clause = ''
    exam_filter_params = [teacher_id]
    if selected_exam_id:
        exam_filter_clause = 'AND e.id = ?'
        exam_filter_params.append(selected_exam_id)

    # Get student submissions with scores
    rows = conn.execute(f'''
        SELECT
            sa.id as answer_id,
            sa.student_id,
            sa.exam_id,
            sa.question_id,
            sa.answer_text,
            sa.status,
            sa.uploaded_at,
            er.total_score,
            er.content_score,
            er.evaluated_at,
            u.full_name as student_name,
            sp.roll_no,
            e.exam_title,
            e.total_marks,
            s.subject_name,
            c.class_name,
            ma.question_text,
            ma.marks as question_marks,
            ma.model_answer_text
        FROM student_answers sa
        JOIN evaluation_results er ON sa.id = er.student_answer_id
        JOIN student_profile sp ON sa.student_id = sp.id
        JOIN users u ON sp.user_id = u.id
        JOIN exams e ON sa.exam_id = e.id
        JOIN subjects s ON e.subject_id = s.id
        JOIN classes c ON e.class_id = c.id
        LEFT JOIN model_answers ma ON sa.exam_id = ma.exam_id AND sa.question_id = ma.question_id
        WHERE e.created_by = ? {exam_filter_clause}
        ORDER BY e.id, u.full_name, sa.question_id
    ''', exam_filter_params).fetchall()

    conn.close()

    # ---- Plagiarism detection ----
    # Group answers by (exam_id, question_id), sorted by upload time (earliest first)
    from collections import defaultdict
    groups = defaultdict(list)
    for r in rows:
        key = (r['exam_id'], r['question_id'])
        if r['answer_text']:
            groups[key].append({
                'answer_id': r['answer_id'],
                'student_id': r['student_id'],
                'student_name': r['student_name'],
                'answer_text': r['answer_text'],
                'uploaded_at': r['uploaded_at'] or ''
            })

    # Sort each group by upload time so earliest submission is index 0
    for key in groups:
        groups[key].sort(key=lambda x: x['uploaded_at'])

    # For each answer only compare against EARLIER submissions (those already in the system)
    # The first submitter always gets 0% plag. Later submitters get flagged if similar.
    plag_scores = {}
    for key, submissions in groups.items():
        for i, a in enumerate(submissions):
            earlier = submissions[:i]   # only previously submitted answers
            best_score = 0.0
            best_match = None
            for b in earlier:
                sim = compute_similarity(a['answer_text'], b['answer_text'])
                if sim > best_score:
                    best_score = sim
                    best_match = b['student_name']
            plag_scores[a['answer_id']] = {
                'score': best_score,
                'matched_student': best_match,
                'flag': best_score >= 70
            }

    # Build structured data per student per exam
    student_exam_map = defaultdict(lambda: defaultdict(list))
    for r in rows:
        plag = plag_scores.get(r['answer_id'], {'score': 0, 'matched_student': None, 'flag': False})
        student_exam_map[(r['exam_id'], r['exam_title'], r['subject_name'], r['class_name'], r['total_marks'])]\
            [( r['student_id'], r['student_name'], r['roll_no'])].append({
                'answer_id': r['answer_id'],
                'question_id': r['question_id'],
                'question_text': r['question_text'],
                'answer_text': r['answer_text'],
                'model_answer': r['model_answer_text'],
                'content_score': r['content_score'],
                'total_score': r['total_score'],
                'question_marks': r['question_marks'],
                'evaluated_at': r['evaluated_at'],
                'plag_score': plag['score'],
                'plag_match': plag['matched_student'],
                'plag_flag': plag['flag']
        })

    # Flatten into list for template
    result_data = []
    for (exam_id, exam_title, subject_name, class_name, total_marks), students in student_exam_map.items():
        student_list = []
        for (student_id, student_name, roll_no), answers in students.items():
            earned = sum(a['total_score'] or 0 for a in answers)
            max_possible = sum(a['question_marks'] or 0 for a in answers)
            pct = round((earned / max_possible * 100), 1) if max_possible else 0
            max_plag = max((a['plag_score'] for a in answers), default=0)
            student_list.append({
                'student_id': student_id,
                'student_name': student_name,
                'roll_no': roll_no,
                'answers': answers,
                'earned_marks': round(earned, 2),
                'max_marks': max_possible,
                'percentage': pct,
                'max_plag_score': max_plag,
                'any_plag_flag': any(a['plag_flag'] for a in answers)
            })
        student_list.sort(key=lambda x: x['percentage'], reverse=True)
        result_data.append({
            'exam_id': exam_id,
            'exam_title': exam_title,
            'subject_name': subject_name,
            'class_name': class_name,
            'total_marks': total_marks,
            'students': student_list
        })

    result_data.sort(key=lambda x: x['exam_id'], reverse=True)

    return render_template('teacher/student_results.html',
                           result_data=result_data,
                           exams=exams,
                           selected_exam_id=selected_exam_id)


if __name__ == '__main__':
    # Use waitress for production, Flask dev server for development
    port = int(os.getenv('PORT', 5000))
    debug_mode = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    
    if debug_mode:
        # Development mode
        import webbrowser
        from threading import Timer
        Timer(1, lambda: webbrowser.open_new(f"http://127.0.0.1:{port}")).start()
        app.run(debug=True, use_reloader=False, port=port)
    else:
        # Production mode — use waitress if available, otherwise Flask
        try:
            from waitress import serve
            print(f"Starting production server on http://0.0.0.0:{port}")
            serve(app, host='0.0.0.0', port=port, threads=8)
        except ImportError:
            print("Waitress not installed. Running Flask dev server (not recommended for production).")
            print("Install waitress: pip install waitress")
            app.run(host='0.0.0.0', port=port, debug=False)