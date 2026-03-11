"""Ініціалізація Flask додатку"""
from flask import Flask
import os

def create_app(config_name='development'):
    """Фабрична функція створення додатку"""
    
    app = Flask(__name__, 
                template_folder='templates',
                static_folder='static')
    
    # Завантаження конфігурації
    app.config.from_object('config.Config')
    
    # Ініціалізація бази даних
    from .models import db
    db.init_app(app)
    
    # Ініціалізація авторизації
    from .auth import init_auth, create_default_admin, create_default_school, create_default_categories, create_default_question_bank
    init_auth(app)
    
    # Реєстрація маршрутів
    from .routes import main_bp
    app.register_blueprint(main_bp)
    
    # Створення таблиць та початкових даних
    with app.app_context():
        # Переконуємось що папка data існує
        os.makedirs('data', exist_ok=True)
        os.makedirs('export', exist_ok=True)
        os.makedirs('logs', exist_ok=True)
        
        # Створюємо таблиці
        db.create_all()
        
        # Створюємо школу за замовчуванням
        create_default_school()
        
        # Створюємо категорії
        create_default_categories()
        
        # Створюємо системну базу питань
        create_default_question_bank()
        
        # Створюємо адміністратора за замовчуванням
        create_default_admin()
        
        # Імпортуємо питання якщо база порожня
        from .models import Question
        if Question.query.count() == 0:
            import_questions_on_startup(app)
    
    return app


def import_questions_on_startup(app):
    """Імпортує питання при першому запуску"""
    import os
    from .import_data import import_from_json, import_from_csv
    from .models import QuestionBank
    
    # Отримуємо системну базу питань
    system_bank = QuestionBank.query.filter_by(level='system', is_default=True).first()
    if not system_bank:
        print("Системна база питань не знайдена")
        return
    
    import_paths = [
        ('import/питання з фото.json', 'json'),
        ('import/questions_photo.json', 'json'),
        ('import/questions.csv', 'csv'),
        ('import/questions 300 питань.csv', 'csv'),
    ]
    
    for path, format_type in import_paths:
        if os.path.exists(path):
            try:
                if format_type == 'json':
                    imported, skipped, msg = import_from_json(path, bank_id=system_bank.id)
                else:
                    imported, skipped, msg = import_from_csv(path, delimiter=';', bank_id=system_bank.id)
                
                print(f"Імпорт з {path}: {msg}")
                
                if imported > 0:
                    break
            except Exception as e:
                print(f"Помилка імпорту {path}: {e}")
