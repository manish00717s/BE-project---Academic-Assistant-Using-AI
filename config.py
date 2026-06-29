"""
Configuration file for AI Evaluation System
"""
import os
from datetime import timedelta

class Config:
    """Base configuration"""
    
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
    
    # Database Configuration
    DATABASE_PATH = 'database/database/evaluation_system.db'
    
    # Upload Configuration
    UPLOAD_FOLDER = 'uploads'
    SYLLABUS_FOLDER = os.path.join(UPLOAD_FOLDER, 'syllabus')
    ANSWER_SHEETS_FOLDER = os.path.join(UPLOAD_FOLDER, 'answer_sheets')
    
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    ALLOWED_EXTENSIONS = {
        'pdf': ['pdf'],
        'excel': ['xlsx', 'xls'],
        'images': ['jpg', 'jpeg', 'png']
    }
    
    # AI Configuration
    HUGGINGFACE_TOKEN = os.getenv('HUGGINGFACE_TOKEN', '')
    AI_MODEL = "mistralai/Mixtral-8x7B-Instruct-v0.1"  # Free model
    
    # Alternative models (if Mixtral is slow)
    ALTERNATIVE_MODELS = [
        "mistralai/Mistral-7B-Instruct-v0.2",
        "google/flan-t5-large",
        "facebook/opt-1.3b"
    ]
    
    # AI Generation Settings
    AI_TIMEOUT = 60  # seconds
    AI_MAX_TOKENS = 2000
    AI_TEMPERATURE = 0.7
    
    # Question Generation Limits
    MAX_MCQ_QUESTIONS = 50
    MAX_SUBJECTIVE_QUESTIONS = 30
    MAX_MARKS_PER_QUESTION = 20
    MIN_MARKS_PER_QUESTION = 1
    
    # Exam Settings
    MIN_EXAM_DURATION = 15  # minutes
    MAX_EXAM_DURATION = 300  # minutes (5 hours)
    
    # Evaluation Settings
    KEYWORD_WEIGHT = 0.4
    CONCEPT_WEIGHT = 0.4
    CLARITY_WEIGHT = 0.2
    
    # PDF Processing
    MAX_PDF_PAGES = 100
    MAX_PDF_SIZE_MB = 10
    
    # Session Configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    SESSION_COOKIE_SECURE = False  # Set True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Pagination
    ITEMS_PER_PAGE = 20
    
    # Date Format
    DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
    DATE_FORMAT = '%Y-%m-%d'
    TIME_FORMAT = '%H:%M'
    
    # Logging
    LOG_LEVEL = 'INFO'
    LOG_FILE = 'logs/app.log'
    
    # Email Configuration (for future notifications)
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')
    
    @staticmethod
    def init_app(app):
        """Initialize application with config"""
        # Create required folders
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.SYLLABUS_FOLDER, exist_ok=True)
        os.makedirs(Config.ANSWER_SHEETS_FOLDER, exist_ok=True)
        os.makedirs('database', exist_ok=True)
        os.makedirs('logs', exist_ok=True)
        
        # Set Flask configuration
        app.config.from_object(Config)


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    
    # Use stronger secret key in production
    SECRET_KEY = os.getenv('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY must be set in production!")


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DATABASE_PATH = 'database/test_evaluation_system.db'


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config(env='development'):
    """Get configuration based on environment"""
    return config.get(env, config['default'])