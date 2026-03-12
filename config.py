"""Конфігурація додатку Тренажер для судноводіїв"""
import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Базова конфігурація"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'navirver-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'data', 'navirver.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # JWT налаштування
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'jwt-secret-key'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    
    # Налаштування сесії
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # Налаштування тестування
    DEFAULT_QUESTIONS_COUNT = 50
    EXAM_QUESTIONS_COUNT = 10  # Кількість питань для іспиту
    EXAM_DURATION_MINUTES = 20  # Час на іспит
    QUESTION_TIME_LIMIT_MINUTES = 2  # Час на одне питання
    MAX_CONCURRENT_USERS = 50
    
    # Режими роботи
    MODES = {
        'sections': 'По розділах',
        'random': 'Випадкові питання',
        'exam': 'Іспит',
        'mistakes': 'Помилки',
        'study': 'Навчання',
        'category': 'За категорією',
        'unanswered': 'Непройдені питання'
    }
    
    # Ролі користувачів
    ROLES = {
        'system_admin': 'Системний адміністратор',
        'school_admin': 'Адміністратор школи',
        'teacher': 'Викладач',
        'student': 'Слухач'
    }
    
    # Категорії питань
    CATEGORIES = {
        'MS': 'Моторні судна',
        'GC': 'Гідроцикли'
    }
    
    # Дані школи
    SCHOOL_NAME = 'Курси судноводіїв "Навірівер"'
    SCHOOL_ADDRESS = '32302, Хмельницька область, м. Кам\'янець-Подільський, вул. Нігинське шосе, 3'
    SCHOOL_PHONE = '+380 96 358 0694'
    SCHOOL_EMAIL = 'tovnaviriver@ukr.net'
    
    # Термін дії аккаунта слухача за замовчуванням (днів)
    STUDENT_ACCOUNT_DAYS = 10
    
    # Пароль за замовчуванням для нових користувачів
    DEFAULT_PASSWORD = 'Navirver2024!'
