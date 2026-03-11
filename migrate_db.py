"""Скрипт міграції бази даних"""
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'navirver.db')

def migrate():
    """Додавання нових колонок та таблиць"""
    if not os.path.exists(DB_PATH):
        print("База даних ще не існує. Міграція не потрібна.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Перевіряємо чи існує колонка teacher_id
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'teacher_id' not in columns:
        print("Додавання колонки teacher_id...")
        cursor.execute("ALTER TABLE users ADD COLUMN teacher_id INTEGER REFERENCES users(id)")
        print("✓ Колонка teacher_id додана")
    
    # Створюємо таблицю teacher_questions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teacher_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL REFERENCES users(id),
            section VARCHAR(10) NOT NULL,
            text TEXT NOT NULL,
            option1 VARCHAR(500) NOT NULL,
            option2 VARCHAR(500) NOT NULL,
            option3 VARCHAR(500) NOT NULL,
            correct INTEGER NOT NULL,
            image_base64 TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    """)
    print("✓ Таблиця teacher_questions створена")
    
    # Створюємо таблицю зв'язку teacher_question_categories
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teacher_question_categories (
            question_id INTEGER NOT NULL REFERENCES teacher_questions(id),
            category_id INTEGER NOT NULL REFERENCES categories(id),
            PRIMARY KEY (question_id, category_id)
        )
    """)
    print("✓ Таблиця teacher_question_categories створена")
    
    # Створюємо таблицю teacher_students
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teacher_students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL REFERENCES users(id),
            student_id INTEGER NOT NULL REFERENCES users(id),
            assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            assigned_by_id INTEGER REFERENCES users(id),
            UNIQUE (teacher_id, student_id)
        )
    """)
    print("✓ Таблиця teacher_students створена")
    
    conn.commit()
    conn.close()
    print("\nМіграція завершена успішно!")

if __name__ == '__main__':
    migrate()
