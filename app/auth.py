"""Автентифікація та авторизація"""
from functools import wraps
from flask import session, redirect, url_for, flash, request
from flask_login import LoginManager, current_user
from datetime import datetime
from .models import User, db, School

login_manager = LoginManager()


def init_auth(app):
    """Ініціалізація системи авторизації"""
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'
    login_manager.login_message = 'Будь ласка, увійдіть для доступу до цієї сторінки'
    login_manager.login_message_category = 'warning'


@login_manager.user_loader
def load_user(user_id):
    """Завантаження користувача за ID"""
    user = User.query.get(int(user_id))
    # Перевірка терміну дії аккаунта
    if user and user.is_account_expired():
        user.is_active = False
        db.session.commit()
    return user


def role_required(*roles):
    """Декоратор для перевірки ролі користувача"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('main.login', next=request.url))
            
            if current_user.role not in roles:
                flash('У вас немає доступу до цієї сторінки', 'danger')
                return redirect(url_for('main.dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """Декоратор для адміністраторів"""
    return role_required('system_admin', 'school_admin')(f)


def teacher_required(f):
    """Декоратор для викладачів та адміністраторів"""
    return role_required('system_admin', 'school_admin', 'teacher')(f)


def create_default_school():
    """Створення школи за замовчуванням"""
    from flask import current_app
    school = School.query.filter_by(name=current_app.config['SCHOOL_NAME']).first()
    
    if not school:
        school = School(
            name=current_app.config['SCHOOL_NAME'],
            address=current_app.config['SCHOOL_ADDRESS'],
            phone=current_app.config['SCHOOL_PHONE'],
            email=current_app.config['SCHOOL_EMAIL'],
            is_active=True
        )
        db.session.add(school)
        db.session.commit()
        print(f"Створено школу: {school.name}")
    return school


def create_default_admin():
    """Створення адміністратора за замовчуванням"""
    from flask import current_app
    admin = User.query.filter_by(username='admin').first()
    
    if not admin:
        admin = User(
            username='admin',
            last_name='Адміністратор',
            first_name='Системний',
            email='admin@navirver.local',
            role='system_admin',
            is_active=True,
            data_processing_consent=True,
            consent_date=datetime.utcnow()
        )
        admin.set_password(current_app.config['DEFAULT_PASSWORD'])
        db.session.add(admin)
        db.session.commit()
        print(f"Створено системного адміністратора: admin / {current_app.config['DEFAULT_PASSWORD']}")
        return True
    return False


def create_default_categories():
    """Створення категорій питань"""
    from flask import current_app
    categories = current_app.config['CATEGORIES']
    
    for code, name in categories.items():
        cat = Category.query.filter_by(code=code).first()
        if not cat:
            cat = Category(code=code, name=name)
            db.session.add(cat)
    db.session.commit()
    print("Категорії створено")


def create_default_question_bank():
    """Створення системної бази питань за замовчуванням"""
    from .models import QuestionBank
    
    bank = QuestionBank.query.filter_by(level='system', is_default=True).first()
    
    if not bank:
        bank = QuestionBank(
            name='Загальна база питань',
            level='system',
            is_default=True,
            is_active=True
        )
        db.session.add(bank)
        db.session.commit()
        print("Створено системну базу питань")
    return bank
    
    db.session.commit()
    print("Категорії створено")


def get_user_statistics(user_id):
    """Отримує статистику користувача"""
    from .models import TestSession, Answer, UserMistake, AnsweredQuestion
    
    # Загальна статистика
    total_tests = TestSession.query.filter_by(user_id=user_id, is_completed=True).count()
    
    # Середній результат
    sessions = TestSession.query.filter_by(user_id=user_id, is_completed=True).all()
    avg_score = 0
    if sessions:
        avg_score = sum(s.get_score_percent() for s in sessions) / len(sessions)
    
    # Кількість помилок
    mistakes_count = UserMistake.query.filter_by(user_id=user_id).count()
    
    # Кількість пройдених питань
    answered_count = AnsweredQuestion.query.filter_by(user_id=user_id).count()
    
    # Останні тести
    recent_tests = TestSession.query.filter_by(user_id=user_id, is_completed=True)\
        .order_by(TestSession.completed_at.desc()).limit(10).all()
    
    return {
        'total_tests': total_tests,
        'average_score': round(avg_score, 1),
        'mistakes_count': mistakes_count,
        'answered_count': answered_count,
        'recent_tests': recent_tests
    }


# Імпорт Category для create_default_categories
from .models import Category
