"""Моделі бази даних"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta
import bcrypt
import json

db = SQLAlchemy()

# Таблиця зв'язку питань з категоріями
question_categories = db.Table('question_categories',
    db.Column('question_id', db.Integer, db.ForeignKey('questions.id'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('categories.id'), primary_key=True)
)

class Category(db.Model):
    """Категорії питань (МС - моторні судна, ГЦ - гідроцикли)"""
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)  # MS, GC
    name = db.Column(db.String(100), nullable=False)  # Малі судна, Гідроцикли
    description = db.Column(db.String(200))
    
    def __repr__(self):
        return f'<Category {self.code}: {self.name}>'


class School(db.Model):
    """Модель навчального закладу"""
    __tablename__ = 'schools'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(300))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    logo_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Зв'язки
    users = db.relationship('User', backref='school', lazy=True)
    
    def __repr__(self):
        return f'<School {self.name}>'


class User(UserMixin, db.Model):
    """Модель користувача"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    
    # Особисті дані
    last_name = db.Column(db.String(100))  # Прізвище
    first_name = db.Column(db.String(100))  # Ім'я
    middle_name = db.Column(db.String(100))  # По батькові
    phone = db.Column(db.String(20))  # Номер телефону
    email = db.Column(db.String(120))  # Електронна пошта
    avatar_url = db.Column(db.String(500))  # URL аватара
    
    # Роль та належність
    role = db.Column(db.String(20), default='student')  # system_admin, school_admin, teacher, student
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Для слухачів - їх викладач
    
    # Статус та термін дії
    is_active = db.Column(db.Boolean, default=True)
    account_created_at = db.Column(db.DateTime, default=datetime.utcnow)
    account_expires_at = db.Column(db.DateTime)  # Термін дії аккаунта
    first_login_at = db.Column(db.DateTime)  # Перший вхід (для активації)
    
    # Погодження на обробку даних
    data_processing_consent = db.Column(db.Boolean, default=False)
    consent_date = db.Column(db.DateTime)
    
    # Прапорець зміни пароля при першому вході
    must_change_password = db.Column(db.Boolean, default=False)
    
    # Статистика
    last_login = db.Column(db.DateTime)
    login_count = db.Column(db.Integer, default=0)
    
    # Зв'язки
    test_sessions = db.relationship('TestSession', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Хешування паролю"""
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def check_password(self, password):
        """Перевірка паролю"""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    def has_role(self, role):
        """Перевірка ролі"""
        return self.role == role
    
    def can_access_admin(self):
        """Чи має доступ до адмін-панелі"""
        return self.role in ['system_admin', 'school_admin']
    
    def can_edit_questions(self):
        """Чи може редагувати питання"""
        return self.role in ['system_admin', 'school_admin', 'teacher']
    
    def can_edit_user(self, user):
        """Чи може редагувати дані користувача"""
        # Системний адміністратор може редагувати всіх, крім інших системних адміністраторів
        if self.role == 'system_admin':
            return user.role != 'system_admin' or user.id == self.id
        
        # Адміністратор школи може редагувати тільки користувачів своєї школи
        if self.role == 'school_admin':
            # Не може редагувати системних адміністраторів та адміністраторів інших шкіл
            if user.role == 'system_admin':
                return False
            if user.role == 'school_admin' and user.id != self.id:
                return False
            # Може редагувати тільки користувачів своєї школи
            return user.school_id == self.school_id
        
        # Викладач може редагувати тільки своїх слухачів
        if self.role == 'teacher':
            return user.role == 'student' and user.teacher_id == self.id
        
        return False
    
    def get_full_name(self):
        """Повертає повне ім'я"""
        parts = [self.last_name, self.first_name, self.middle_name]
        return ' '.join(filter(None, parts)) or self.username
    
    def get_role_display(self):
        """Повертає назву ролі українською"""
        roles = {
            'system_admin': 'Системний адміністратор',
            'school_admin': 'Адміністратор школи',
            'teacher': 'Викладач',
            'student': 'Слухач'
        }
        return roles.get(self.role, self.role)
    
    def is_account_expired(self):
        """Чи закінчився термін дії аккаунта"""
        if self.account_expires_at:
            return datetime.utcnow() > self.account_expires_at
        return False
    
    def activate_for_days(self, days):
        """Активувати аккаунт на вказану кількість днів"""
        self.account_expires_at = datetime.utcnow() + timedelta(days=days)
        self.is_active = True
    
    def has_completed_profile(self):
        """Чи заповнив користувач профіль"""
        return all([
            self.last_name,
            self.first_name,
            self.phone,
            self.email,
            self.data_processing_consent
        ])
    
    def to_dict(self):
        """Конвертація в словник для експорту"""
        return {
            'id': self.id,
            'username': self.username,
            'last_name': self.last_name,
            'first_name': self.first_name,
            'middle_name': self.middle_name,
            'phone': self.phone,
            'email': self.email,
            'role': self.role,
            'school_id': self.school_id,
            'is_active': self.is_active,
            'account_expires_at': self.account_expires_at.isoformat() if self.account_expires_at else None,
            'data_processing_consent': self.data_processing_consent
        }
    
    def __repr__(self):
        return f'<User {self.username}>'


class QuestionBank(db.Model):
    """База питань (системна, школи, викладача)"""
    __tablename__ = 'question_banks'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    level = db.Column(db.String(20), nullable=False)  # system, school, teacher
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Власник (для teacher)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=True)  # Школа (для school)
    is_active = db.Column(db.Boolean, default=True)
    is_default = db.Column(db.Boolean, default=False)  # Чи є базою за замовчуванням
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Зв'язки
    owner = db.relationship('User', foreign_keys=[owner_id], backref='owned_banks')
    school = db.relationship('School', backref='question_banks')
    questions = db.relationship('Question', backref='bank', lazy=True, cascade='all, delete-orphan')
    
    def can_edit(self, user):
        """Перевірка чи користувач може редагувати цю базу"""
        if user.role == 'system_admin':
            return True
        if self.level == 'school' and user.role in ['school_admin', 'system_admin']:
            return self.school_id == user.school_id
        if self.level == 'teacher' and user.id == self.owner_id:
            return True
        return False
    
    def can_import_from(self, user):
        """Перевірка чи користувач може імпортувати з цієї бази"""
        if self.level == 'system':
            return True  # Всі можуть імпортувати з системної бази
        if self.level == 'school':
            return user.school_id == self.school_id
        if self.level == 'teacher':
            return user.id == self.owner_id
        return False
    
    def __repr__(self):
        return f'<QuestionBank {self.name} ({self.level})>'


class Question(db.Model):
    """Модель питання"""
    __tablename__ = 'questions'
    
    id = db.Column(db.Integer, primary_key=True)
    bank_id = db.Column(db.Integer, db.ForeignKey('question_banks.id'), nullable=False)
    section = db.Column(db.String(10), nullable=False, index=True)
    text = db.Column(db.Text, nullable=False)
    option1 = db.Column(db.String(500), nullable=False)
    option2 = db.Column(db.String(500), nullable=False)
    option3 = db.Column(db.String(500), nullable=False)
    correct = db.Column(db.Integer, nullable=False)  # 0, 1, або 2 (індекс правильної відповіді)
    correct_key = db.Column(db.String(10))  # Унікальний ключ правильної відповіді для перемішування
    image_base64 = db.Column(db.Text)  # Base64 зображення
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Зв'язки
    answers = db.relationship('Answer', backref='question', lazy=True)
    categories = db.relationship('Category', secondary=question_categories, backref='questions')
    
    def get_options(self):
        """Повертає список варіантів відповіді"""
        return [self.option1, self.option2, self.option3]
    
    def get_shuffled_options(self, seed=None):
        """Повертає перемішані варіанти відповіді з ключами"""
        import random
        options = [
            {'text': self.option1, 'key': 'A', 'original_index': 0},
            {'text': self.option2, 'key': 'B', 'original_index': 1},
            {'text': self.option3, 'key': 'C', 'original_index': 2}
        ]
        
        if seed:
            random.seed(seed)
        random.shuffle(options)
        
        return options
    
    def get_correct_answer_display(self):
        """Повертає номер правильної відповіді (1-3)"""
        return self.correct + 1
    
    def to_dict(self):
        """Конвертація в словник"""
        return {
            'id': self.id,
            'bank_id': self.bank_id,
            'section': self.section,
            'text': self.text,
            'options': self.get_options(),
            'correct': self.correct,
            'has_image': self.image_base64 is not None,
            'categories': [c.code for c in self.categories]
        }
    
    def __repr__(self):
        return f'<Question {self.id}: {self.text[:50]}...>'


class TestSession(db.Model):
    """Модель сесії тестування"""
    __tablename__ = 'test_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    mode = db.Column(db.String(20), nullable=False)  # sections, random, exam, mistakes, study, category
    category_code = db.Column(db.String(10))  # MS, GC для режиму категорій
    questions_count = db.Column(db.Integer, default=0)
    correct_count = db.Column(db.Integer, default=0)
    duration_seconds = db.Column(db.Integer, default=0)
    is_completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    # Налаштування тесту
    timer_mode = db.Column(db.String(10), default='unlimited')  # unlimited, limited
    show_feedback = db.Column(db.String(10), default='instant')  # instant, end
    shuffle_questions = db.Column(db.Boolean, default=False)
    shuffle_options = db.Column(db.Boolean, default=False)
    
    # Зв'язки
    answers = db.relationship('Answer', backref='session', lazy=True, cascade='all, delete-orphan')
    
    def get_score_percent(self):
        """Відсоток правильних відповідей"""
        if self.questions_count == 0:
            return 0
        return round((self.correct_count / self.questions_count) * 100, 1)
    
    def get_duration_formatted(self):
        """Форматований час проходження"""
        minutes = self.duration_seconds // 60
        seconds = self.duration_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"
    
    def __repr__(self):
        return f'<TestSession {self.id}: {self.mode}>'


class Answer(db.Model):
    """Модель відповіді на питання"""
    __tablename__ = 'answers'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('test_sessions.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    selected_option = db.Column(db.Integer, nullable=True)  # 0, 1, 2 або None (пропущено)
    selected_key = db.Column(db.String(10))  # Ключ вибраної відповіді (A, B, C)
    is_correct = db.Column(db.Boolean, default=False)
    answered_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Answer {self.id}: Q{self.question_id} = {self.selected_option}>'


class UserMistake(db.Model):
    """Модель помилок користувача (для режиму 'Помилки')"""
    __tablename__ = 'user_mistakes'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    mistake_count = db.Column(db.Integer, default=1)
    last_mistake_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Унікальний індекс для пари користувач-питання
    __table_args__ = (db.UniqueConstraint('user_id', 'question_id', name='unique_user_mistake'),)
    
    def __repr__(self):
        return f'<UserMistake U{self.user_id}:Q{self.question_id}>'


class AnsweredQuestion(db.Model):
    """Модель для відстеження пройдених питань (без повторень)"""
    __tablename__ = 'answered_questions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)
    answered_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Унікальний індекс
    __table_args__ = (db.UniqueConstraint('user_id', 'question_id', name='unique_answered_question'),)
    
    def __repr__(self):
        return f'<AnsweredQuestion U{self.user_id}:Q{self.question_id}>'


class SystemSetting(db.Model):
    """Системні налаштування"""
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text)
    description = db.Column(db.String(200))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Setting {self.key}>'


class TeacherStudent(db.Model):
    """Зв'язок викладач - слухач"""
    __tablename__ = 'teacher_students'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # Хто призначив
    
    # Зв'язки
    teacher = db.relationship('User', foreign_keys=[teacher_id], backref='assigned_students')
    student = db.relationship('User', foreign_keys=[student_id], backref='my_teacher')
    assigned_by = db.relationship('User', foreign_keys=[assigned_by_id])
    
    # Унікальний індекс
    __table_args__ = (db.UniqueConstraint('teacher_id', 'student_id', name='unique_teacher_student'),)
    
    def __repr__(self):
        return f'<TeacherStudent T{self.teacher_id}:S{self.student_id}>'


class TeacherQuestion(db.Model):
    """Питання викладача (особиста база)"""
    __tablename__ = 'teacher_questions'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    section = db.Column(db.String(10), nullable=False, index=True)
    text = db.Column(db.Text, nullable=False)
    option1 = db.Column(db.String(500), nullable=False)
    option2 = db.Column(db.String(500), nullable=False)
    option3 = db.Column(db.String(500), nullable=False)
    correct = db.Column(db.Integer, nullable=False)  # 0, 1, або 2
    image_base64 = db.Column(db.Text)  # Base64 зображення
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Зв'язки
    teacher = db.relationship('User', backref='personal_questions')
    categories = db.relationship('Category', secondary='teacher_question_categories', backref='teacher_questions')
    
    def get_options(self):
        """Повертає список варіантів відповіді"""
        return [self.option1, self.option2, self.option3]
    
    def get_shuffled_options(self, seed=None):
        """Повертає перемішані варіанти відповіді з ключами"""
        import random
        options = [
            {'text': self.option1, 'key': 'A', 'original_index': 0},
            {'text': self.option2, 'key': 'B', 'original_index': 1},
            {'text': self.option3, 'key': 'C', 'original_index': 2}
        ]
        
        if seed:
            random.seed(seed)
        random.shuffle(options)
        
        return options
    
    def __repr__(self):
        return f'<TeacherQuestion {self.id}: {self.text[:50]}...>'


class LoginLog(db.Model):
    """Лог входів користувачів"""
    __tablename__ = 'login_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ip_address = db.Column(db.String(45))  # IPv6 може бути до 45 символів
    user_agent = db.Column(db.String(500))
    login_at = db.Column(db.DateTime, default=datetime.utcnow)
    logout_at = db.Column(db.DateTime)
    is_successful = db.Column(db.Boolean, default=True)
    
    # Зв'язок з користувачем
    user = db.relationship('User', backref='login_logs', lazy=True)
    
    def __repr__(self):
        return f'<LoginLog U{self.user_id} from {self.ip_address}>'


# Таблиця зв'язку групи зі слухачами
group_students = db.Table('group_students',
    db.Column('group_id', db.Integer, db.ForeignKey('groups.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True)
)


class Group(db.Model):
    """Група слухачів для навчання"""
    __tablename__ = 'groups'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Зв'язки
    school = db.relationship('School', backref='groups', lazy=True)
    teacher = db.relationship('User', backref='teacher_groups', lazy=True)
    students = db.relationship('User', secondary=group_students, backref='student_groups', lazy=True)
    exams = db.relationship('SchoolExam', backref='group', lazy=True, cascade='all, delete-orphan')
    
    def get_students_count(self):
        """Кількість слухачів у групі"""
        return len(self.students)
    
    def __repr__(self):
        return f'<Group {self.name}>'


class SchoolExam(db.Model):
    """Внутрішній шкільний іспит"""
    __tablename__ = 'school_exams'
    
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    
    # Параметри іспиту
    question_count = db.Column(db.Integer, default=10)
    time_minutes = db.Column(db.Integer, default=20)
    max_errors = db.Column(db.Integer, default=2)
    
    # Тип вибору питань: 'random' - випадково, 'manual' - вручну
    question_selection_type = db.Column(db.String(20), default='random')
    
    # Статус
    is_active = db.Column(db.Boolean, default=False)
    activated_at = db.Column(db.DateTime)
    activated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Часові обмеження
    available_from = db.Column(db.DateTime)
    available_until = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Зв'язки
    category = db.relationship('Category', backref='school_exams', lazy=True)
    activated_by = db.relationship('User', backref='activated_exams', lazy=True)
    questions = db.relationship('SchoolExamQuestion', backref='exam', lazy=True, cascade='all, delete-orphan')
    results = db.relationship('SchoolExamResult', backref='exam', lazy=True, cascade='all, delete-orphan')
    
    def is_available(self):
        """Чи доступний іспит для проходження"""
        if not self.is_active:
            return False
        now = datetime.utcnow()
        if self.available_from and now < self.available_from:
            return False
        if self.available_until and now > self.available_until:
            return False
        return True
    
    def __repr__(self):
        return f'<SchoolExam {self.name}>'


class SchoolExamQuestion(db.Model):
    """Питання для шкільного іспиту (для ручного формування білетів)"""
    __tablename__ = 'school_exam_questions'
    
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('school_exams.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    order = db.Column(db.Integer, default=0)
    
    # Зв'язок з питанням
    question = db.relationship('Question', lazy=True)
    
    def __repr__(self):
        return f'<SchoolExamQuestion E{self.exam_id} Q{self.question_id}>'


class SchoolExamResult(db.Model):
    """Результат проходження шкільного іспиту"""
    __tablename__ = 'school_exam_results'
    
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('school_exams.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Часові мітки
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    # Результати
    total_questions = db.Column(db.Integer, default=0)
    correct_answers = db.Column(db.Integer, default=0)
    errors_count = db.Column(db.Integer, default=0)
    
    # Час проходження в секундах
    time_spent_seconds = db.Column(db.Integer)
    
    # Статус: 'in_progress', 'completed', 'failed'
    status = db.Column(db.String(20), default='in_progress')
    
    # Чи складено іспит
    is_passed = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Зв'язки
    user = db.relationship('User', backref='school_exam_results', lazy=True)
    answers = db.relationship('SchoolExamAnswer', backref='result', lazy=True, cascade='all, delete-orphan')
    
    def get_time_spent_formatted(self):
        """Форматований час проходження"""
        if not self.time_spent_seconds:
            return '—'
        minutes = self.time_spent_seconds // 60
        seconds = self.time_spent_seconds % 60
        return f'{minutes:02d}:{seconds:02d}'
    
    def __repr__(self):
        return f'<SchoolExamResult E{self.exam_id} U{self.user_id}>'


class SchoolExamAnswer(db.Model):
    """Відповідь слухача на питання іспиту"""
    __tablename__ = 'school_exam_answers'
    
    id = db.Column(db.Integer, primary_key=True)
    result_id = db.Column(db.Integer, db.ForeignKey('school_exam_results.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    
    # Вибрана відповідь (0, 1, 2)
    selected_answer = db.Column(db.Integer)
    
    # Чи правильна відповідь
    is_correct = db.Column(db.Boolean, default=False)
    
    # Час відповіді
    answered_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Зв'язок з питанням
    question = db.relationship('Question', lazy=True)
    
    def __repr__(self):
        return f'<SchoolExamAnswer R{self.result_id} Q{self.question_id}>'


# Таблиця зв'язку питань викладача з категоріями
teacher_question_categories = db.Table('teacher_question_categories',
    db.Column('question_id', db.Integer, db.ForeignKey('teacher_questions.id'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('categories.id'), primary_key=True)
)
