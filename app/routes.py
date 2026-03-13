"""Маршрути додатку"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, send_file, current_app
from flask_login import login_required, login_user, logout_user, current_user
from sqlalchemy import func
from datetime import datetime, timedelta
import random
import json
import csv
import io
import os

from .models import db, User, School, Question, TestSession, Answer, UserMistake, SystemSetting, Category, AnsweredQuestion, QuestionBank, LoginLog, Group, SchoolExam, SchoolExamQuestion, SchoolExamResult, SchoolExamAnswer
from .auth import admin_required, teacher_required, get_user_statistics
from .import_data import import_from_json, import_from_csv, get_statistics, export_to_json, export_to_csv, export_users_to_json, import_users_from_json

main_bp = Blueprint('main', __name__)

def get_available_question_banks(user):
    """Отримує список доступних баз питань для користувача"""
    banks = []

    # Системна база (доступна всім)
    system_banks = QuestionBank.query.filter_by(level='system', is_active=True).all()
    banks.extend(system_banks)

    # Бази школи (для користувачів школи)
    if user.school_id:
        school_banks = QuestionBank.query.filter_by(
            level='school',
            school_id=user.school_id,
            is_active=True
        ).all()
        banks.extend(school_banks)

    # Бази викладача (для викладача та його слухачів)
    if user.role == 'teacher':
        teacher_banks = QuestionBank.query.filter_by(
            level='teacher',
            owner_id=user.id,
            is_active=True
        ).all()
        banks.extend(teacher_banks)
    elif user.role == 'student' and user.teacher_id:
        # Слухач може бачити бази свого викладача
        teacher_banks = QuestionBank.query.filter_by(
            level='teacher',
            owner_id=user.teacher_id,
            is_active=True
        ).all()
        banks.extend(teacher_banks)

    return banks

# ==================== ГОЛОВНІ СТОРІНКИ ====================

@main_bp.route('/')
def index():
    """Головна сторінка"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('main.login'))

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Сторінка входу"""
    # Перевіряємо чи це перенаправлення після logout
    just_logged_out = request.args.get('logout') == '1'

    if current_user.is_authenticated and not just_logged_out:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            if not user.is_active:
                flash('Обліковий запис деактивовано', 'danger')
                return render_template('login.html')

            if user.is_account_expired():
                flash('Термін дії облікового запису закінчився. Зверніться до адміністратора.', 'danger')
                return render_template('login.html')

            login_user(user, remember=True)
            user.last_login = datetime.utcnow()
            user.login_count += 1

            # Записуємо лог входу
            login_log = LoginLog(
                user_id=user.id,
                ip_address=request.remote_addr,
                user_agent=request.user_agent.string[:500] if request.user_agent else None,
                is_successful=True
            )
            db.session.add(login_log)
            session['login_log_id'] = login_log.id

            # Перший вхід для слухача - записуємо час першого входу
            if user.role == 'student' and not user.first_login_at:
                user.first_login_at = datetime.utcnow()
                db.session.commit()
                return redirect(url_for('main.complete_profile'))

            # Перевірка чи потрібно змінити пароль
            if user.must_change_password:
                db.session.commit()
                flash('Будь ласка, змініть пароль', 'warning')
                return redirect(url_for('main.change_password'))

            db.session.commit()

            flash(f'Ласкаво просимо, {user.get_full_name() or user.username}!', 'success')

            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
        else:
            flash('Невірне ім\'я користувача або пароль', 'danger')

    return render_template('login.html')

@main_bp.route('/logout')
@login_required
def logout():
    """Вихід з системи"""
    # Оновлюємо лог входу - записуємо час виходу
    login_log_id = session.get('login_log_id')
    if login_log_id:
        login_log = LoginLog.query.get(login_log_id)
        if login_log:
            login_log.logout_at = datetime.utcnow()
            db.session.commit()

    logout_user()
    session.clear()
    flash('Ви вийшли з системи', 'info')
    response = redirect(url_for('main.login', logout='1'))
    # Видаляємо cookie remember me
    response.delete_cookie('remember_token')
    return response

@main_bp.route('/complete-profile', methods=['GET', 'POST'])
@login_required
def complete_profile():
    """Заповнення профілю при першому вході"""
    if current_user.role != 'student' or current_user.has_completed_profile():
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        current_user.last_name = request.form.get('last_name')
        current_user.first_name = request.form.get('first_name')
        current_user.middle_name = request.form.get('middle_name')
        current_user.phone = request.form.get('phone')
        current_user.email = request.form.get('email')

        consent = request.form.get('data_processing_consent')
        if consent:
            current_user.data_processing_consent = True
            current_user.consent_date = datetime.utcnow()

        db.session.commit()
        flash('Профіль успішно заповнено!', 'success')
        return redirect(url_for('main.dashboard'))

    user_stats = get_user_statistics(current_user.id)
    return render_template('complete_profile.html', user_stats=user_stats)

@main_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Зміна пароля"""
    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not current_user.check_password(old_password):
            flash('Невірний поточний пароль', 'danger')
        elif new_password != confirm_password:
            flash('Паролі не співпадають', 'danger')
        elif len(new_password) < 6:
            flash('Пароль має бути не менше 6 символів', 'danger')
        else:
            current_user.set_password(new_password)
            current_user.must_change_password = False
            db.session.commit()
            flash('Пароль успішно змінено!', 'success')
            return redirect(url_for('main.dashboard'))

    user_stats = get_user_statistics(current_user.id)
    return render_template('change_password.html', user_stats=user_stats)

@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Панель керування"""
    # Перевірка для слухачів
    if current_user.role == 'student':
        if not current_user.has_completed_profile():
            return redirect(url_for('main.complete_profile'))
        if current_user.is_account_expired():
            flash('Термін дії аккаунта закінчився. Зверніться до адміністратора.', 'danger')

    user_stats = get_user_statistics(current_user.id)

    # Отримуємо доступні бази питань
    available_banks = get_available_question_banks(current_user)

    # Отримуємо категорії
    categories = Category.query.all()

    # Отримуємо розділи з активної бази (або системної)
    active_bank_id = session.get('active_bank_id')
    if active_bank_id:
        sections = db.session.query(Question.section).filter_by(bank_id=active_bank_id).distinct().order_by(Question.section).all()
    else:
        system_bank = QuestionBank.query.filter_by(level='system', is_default=True).first()
        if system_bank:
            sections = db.session.query(Question.section).filter_by(bank_id=system_bank.id).distinct().order_by(Question.section).all()
        else:
            sections = []
    sections = [s[0] for s in sections]

    # Кількість питань в активній базі
    total_questions = 0
    if active_bank_id:
        total_questions = Question.query.filter_by(bank_id=active_bank_id).count()
    elif system_bank:
        total_questions = Question.query.filter_by(bank_id=system_bank.id).count()

    # Статистика слухачів для викладачів та адміністраторів
    students_stats = []
    if current_user.role in ['teacher', 'school_admin', 'system_admin']:
        # Отримуємо список слухачів
        if current_user.role == 'teacher':
            # Слухачі, закріплені за викладачем
            students = User.query.filter_by(role='student', teacher_id=current_user.id).all()
        elif current_user.role == 'school_admin':
            # Слухачі з закладу адміністратора
            students = User.query.filter_by(role='student', school_id=current_user.school_id).all()
        else:  # system_admin
            # Всі слухачі
            students = User.query.filter_by(role='student').all()

        # Формуємо статистику для кожного слухача
        for student in students:
            student_stats = get_user_statistics(student.id)
            students_stats.append({
                'user': student,
                'total_tests': student_stats.get('total_tests', 0),
                'average_score': student_stats.get('average_score', 0),
                'answered_count': student_stats.get('answered_count', 0),
                'mistakes_count': student_stats.get('mistakes_count', 0)
            })

        # Сортуємо за прізвищем
        students_stats.sort(key=lambda x: x['user'].last_name or x['user'].username)

    return render_template('dashboard.html',
                         user_stats=user_stats,
                         total_questions=total_questions,
                         categories=categories,
                         sections=sections,
                         modes=current_app.config['MODES'],
                         available_banks=available_banks,
                         active_bank_id=active_bank_id,
                         students_stats=students_stats)

@main_bp.route('/select-bank', methods=['POST'])
@login_required
def select_bank():
    """Вибір активної бази питань"""
    bank_id = request.form.get('bank_id')
    if bank_id:
        bank = QuestionBank.query.get(bank_id)
        if bank:
            session['active_bank_id'] = int(bank_id)
            flash(f'Обрано базу: {bank.name}', 'success')
        else:
            flash('Базу не знайдено', 'danger')
    else:
        session.pop('active_bank_id', None)
        flash('Вибрано базу за замовчуванням', 'info')
    return redirect(url_for('main.dashboard'))

# ==================== ТЕСТУВАННЯ ====================

@main_bp.route('/test/start', methods=['POST'])
@login_required
def start_test():
    """Початок тестування"""
    # Очищуємо стару сесію тестування
    session.pop('test_session_id', None)
    session.pop('questions', None)
    session.pop('current_index', None)
    session.pop('answers', None)
    session.pop('shuffle_options', None)
    session.pop('start_time', None)
    session.pop('duration_seconds', None)

    mode = request.form.get('mode', 'random')
    section = request.form.get('section', '')
    category_code = request.form.get('category', '')
    count = int(request.form.get('count', 50))
    timer_mode = request.form.get('timer_mode', 'unlimited')
    show_feedback = request.form.get('show_feedback', 'instant')
    # Checkbox повертає 'on' якщо вибрано, None якщо не вибрано
    shuffle = request.form.get('shuffle') == 'on'
    shuffle_options = request.form.get('shuffle_options') == 'on'

    # Отримуємо bank_id з сесії або використовуємо системну базу
    bank_id = session.get('active_bank_id')
    if not bank_id:
        system_bank = QuestionBank.query.filter_by(level='system', is_default=True).first()
        bank_id = system_bank.id if system_bank else None

    print(f"DEBUG: bank_id={bank_id}, shuffle={shuffle}, shuffle_options={shuffle_options}")

    # Дебаг - виводимо в консоль
    print(f"DEBUG: mode={mode}, section={section}, category={category_code}, count={count}")

    # Базовий запит для питань
    base_query = Question.query
    if bank_id:
        base_query = base_query.filter_by(bank_id=bank_id)

    # Отримуємо питання відповідно до режиму
    questions = []

    if mode == 'mistakes':
        # Питання з помилок користувача
        mistakes = UserMistake.query.filter_by(user_id=current_user.id).all()
        question_ids = [m.question_id for m in mistakes]
        questions = base_query.filter(Question.id.in_(question_ids)).all()
        print(f"DEBUG: mistakes mode, found {len(questions)} questions with mistakes")

    elif mode == 'unanswered':
        # Непройдені питання
        answered_ids = db.session.query(AnsweredQuestion.question_id).filter_by(user_id=current_user.id).all()
        answered_ids = [a[0] for a in answered_ids]
        if answered_ids:
            questions = base_query.filter(~Question.id.in_(answered_ids)).all()
        else:
            questions = base_query.all()
        print(f"DEBUG: unanswered mode, found {len(questions)} unanswered questions")

    elif mode == 'sections':
        # Питання з конкретного розділу (або всі якщо не вказано)
        if section and section.strip():
            questions = base_query.filter_by(section=section).all()
            print(f"DEBUG: sections mode, section={section}, found {len(questions)} questions")
        else:
            questions = base_query.all()
            print(f"DEBUG: sections mode, no section selected, using all {len(questions)} questions")

    elif mode == 'category':
        # Питання за категорією
        if category_code and category_code.strip():
            category = Category.query.filter_by(code=category_code).first()
            if category:
                # Отримуємо питання з бази які належать до цієї категорії
                all_cat_questions = category.questions
                if bank_id:
                    all_cat_questions = [q for q in all_cat_questions if q.bank_id == bank_id]
                questions = all_cat_questions
                print(f"DEBUG: category mode, category={category_code}, found {len(questions)} questions")
            else:
                questions = base_query.all()
                print(f"DEBUG: category mode, category not found, using all {len(questions)} questions")
        else:
            questions = base_query.all()
            print(f"DEBUG: category mode, no category selected, using all {len(questions)} questions")

    elif mode == 'exam':
        # Іспит - 10 питань, 20 хвилин
        all_questions = base_query.all()
        # Фільтруємо за категорією якщо вказана
        if category_code and category_code.strip():
            category = Category.query.filter_by(code=category_code).first()
            if category:
                all_questions = [q for q in all_questions if category in q.categories]
                print(f"DEBUG: exam mode, category={category_code}, filtered to {len(all_questions)} questions")
        questions = random.sample(all_questions, min(10, len(all_questions)))
        timer_mode = 'limited'
        count = 10
        print(f"DEBUG: exam mode, selected {len(questions)} questions")

    elif mode == 'study':
        # Навчання - всі питання
        questions = base_query.all()
        if category_code and category_code.strip():
            category = Category.query.filter_by(code=category_code).first()
            if category:
                questions = [q for q in questions if category in q.categories]
                print(f"DEBUG: study mode, category={category_code}, found {len(questions)} questions")
            else:
                print(f"DEBUG: study mode, category not found, using all {len(questions)} questions")
        else:
            print(f"DEBUG: study mode, no category, using all {len(questions)} questions")

    else:
        # Випадкові питання (режим random)
        all_questions = base_query.all()
        if count == 0 or count >= len(all_questions):
            # Всі питання
            questions = all_questions
            print(f"DEBUG: random mode, using all {len(questions)} questions")
        else:
            questions = random.sample(all_questions, count)
            print(f"DEBUG: random mode, selected {len(questions)} random questions")

    if not questions:
        flash('Немає доступних питань для цього режиму', 'warning')
        return redirect(url_for('main.dashboard'))

    print(f"DEBUG: Final questions count: {len(questions)}, mode: {mode}")

    # Перемішуємо якщо потрібно
    if shuffle:
        random.shuffle(questions)

    # Для іспиту обмежуємо час
    duration_seconds = None
    if mode == 'exam':
        duration_seconds = current_app.config['EXAM_DURATION_MINUTES'] * 60
    elif timer_mode == 'limited':
        duration_seconds = len(questions) * current_app.config['QUESTION_TIME_LIMIT_MINUTES'] * 60

    # Створюємо сесію тестування
    test_session = TestSession(
        user_id=current_user.id,
        mode=mode,
        category_code=category_code,
        questions_count=len(questions),
        timer_mode=timer_mode,
        show_feedback=show_feedback,
        shuffle_questions=shuffle,
        shuffle_options=shuffle_options
    )
    db.session.add(test_session)
    db.session.commit()

    # Зберігаємо питання в сесії (тільки ID, не об'єкти!)
    session['test_session_id'] = test_session.id
    session['questions'] = [q.id for q in questions]
    session['current_index'] = 0
    session['answers'] = {}
    session['shuffle_options'] = shuffle_options  # Тільки прапорець
    session['start_time'] = datetime.utcnow().isoformat()
    session['duration_seconds'] = duration_seconds

    return redirect(url_for('main.test_question'))

@main_bp.route('/test/question')
@login_required
def test_question():
    """Сторінка з питанням"""
    test_session_id = session.get('test_session_id')
    if not test_session_id:
        return redirect(url_for('main.dashboard'))

    test_session = TestSession.query.get(test_session_id)
    if not test_session or test_session.is_completed:
        session.pop('test_session_id', None)
        return redirect(url_for('main.dashboard'))

    questions = session.get('questions', [])
    current_index = session.get('current_index', 0)

    if current_index >= len(questions):
        return redirect(url_for('main.test_finish'))

    question = Question.query.get(questions[current_index])
    if not question:
        flash('Помилка: питання не знайдено', 'danger')
        return redirect(url_for('main.dashboard'))

    # Режим навчання - показуємо лише питання і правильну відповідь
    if test_session.mode == 'study':
        return render_template('study.html',
                               question=question,
                               current_index=current_index + 1,
                               total=len(questions),
                               test_session=test_session)

    # Перевіряємо чи вже була відповідь
    existing_answer = session.get('answers', {}).get(str(question.id))

    # Отримуємо варіанти відповідей (перемішані або звичайні)
    if test_session.shuffle_options:
        # Генеруємо перемішування на льоту (детерміновано)
        options = question.get_shuffled_options(seed=question.id + test_session.id)
    else:
        options = [
            {'text': question.option1, 'key': 'A', 'original_index': 0},
            {'text': question.option2, 'key': 'B', 'original_index': 1},
            {'text': question.option3, 'key': 'C', 'original_index': 2}
        ]

    # Отримуємо об'єкти питань для карти (для кольорового кодування)
    question_objects = [Question.query.get(qid) for qid in questions]

    # Формуємо дані відповідей для карти питань
    answers_data = session.get('answers', {})

    return render_template('test.html',
                           question=question,
                           questions=questions,
                           question_objects=question_objects,
                           options=options,
                           current_index=current_index + 1,
                           total=len(questions),
                           existing_answer=existing_answer,
                           test_session=test_session,
                           answers_data=answers_data,
                           show_feedback=test_session.show_feedback)

@main_bp.route('/test/go-to/<int:index>')
@login_required
def test_go_to(index):
    """Перехід до конкретного питання"""
    questions = session.get('questions', [])
    if 0 <= index < len(questions):
        session['current_index'] = index
    return redirect(url_for('main.test_question'))

@main_bp.route('/test/answer', methods=['POST'])
@login_required
def test_answer():
    """Обробка відповіді"""
    test_session_id = session.get('test_session_id')
    if not test_session_id:
        return jsonify({'error': 'No active test session'}), 400

    # Детальне логування для діагностики
    print(f"DEBUG: Content-Type={request.content_type}")
    raw_data = request.get_data(as_text=True)
    print(f"DEBUG: raw data type={type(raw_data)}")
    print(f"DEBUG: raw data={repr(raw_data)}")

    data = request.get_json(silent=True)
    print(f"DEBUG: parsed json={data}")
    print(f"DEBUG: parsed json type={type(data)}")

    # Якщо JSON не парситься, спробуємо розпарсити вручну
    if data is None and raw_data:
        try:
            data = json.loads(raw_data)
            print(f"DEBUG: manually parsed json={data}")
            print(f"DEBUG: manually parsed json type={type(data)}")
        except json.JSONDecodeError as e:
            print(f"DEBUG: JSON decode error: {e}")

    if data is None:
        # Спробуємо отримати дані як form data
        data = request.form.to_dict() or request.values.to_dict()
        print(f"DEBUG: form data={data}")

    if not data:
        return jsonify({'error': 'No data received'}), 400

    # Перевіряємо всі ключі в даних
    print(f"DEBUG: data keys={list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
    print(f"DEBUG: data type={type(data)}")
    print(f"DEBUG: full data={data}")

    # Якщо дані - це рядок, спробуємо розпарсити його як JSON
    if isinstance(data, str):
        try:
            data = json.loads(data)
            print(f"DEBUG: parsed string to dict: {data}")
        except:
            pass

    # Перевіряємо чи дані - це словник
    if not isinstance(data, dict):
        return jsonify({'error': 'Invalid data format'}), 400

    question_id = data.get('question_id')
    selected_key = data.get('selected_key')  # A, B, C
    selected_index = data.get('selected_index')  # 0, 1, 2

    print(f"DEBUG: extracted question_id={question_id}, selected_key={selected_key}, selected_index={selected_index}")

    if question_id is None:
        return jsonify({'error': 'Question ID required'}), 400

    question = Question.query.get(question_id)
    test_session = TestSession.query.get(test_session_id)

    # Знаходимо оригінальний індекс за ключем
    selected_option = None
    print(f"DEBUG: Looking for selected_option with key='{selected_key}', index={selected_index}")

    if test_session and test_session.shuffle_options:
        # Генеруємо те саме перемішування що і в test_question
        shuffled = question.get_shuffled_options(seed=question.id + test_session.id)
        print(f"DEBUG: Shuffled options: {[(opt['key'], opt['original_index']) for opt in shuffled]}")
        for opt in shuffled:
            if opt['key'] == selected_key:
                selected_option = opt['original_index']
                print(f"DEBUG: Found match! key={selected_key} -> original_index={selected_option}")
                break
    else:
        # Без перемішування - використовуємо ключ безпосередньо
        if selected_key and selected_key in ['A', 'B', 'C']:
            selected_option = ['A', 'B', 'C'].index(selected_key)
            print(f"DEBUG: Using key directly: {selected_key} -> {selected_option}")
        elif selected_index is not None:
            selected_option = int(selected_index)
            print(f"DEBUG: Using index: {selected_index}")

    print(f"DEBUG: shuffle_options={test_session.shuffle_options if test_session else 'N/A'}, selected_option={selected_option}")

    # Перевіряємо правильність (перетворюємо на int для порівняння)
    correct_index = int(question.correct) if question.correct is not None else None
    is_correct = selected_option == correct_index if selected_option is not None and correct_index is not None else False

    print(f"DEBUG: selected_option={selected_option}, correct={correct_index}, is_correct={is_correct}")

    # Зберігаємо відповідь в сесії з інформацією про правильність
    answers = session.get('answers', {})
    answers[str(question_id)] = {
        'option': selected_option,
        'key': selected_key,
        'is_correct': is_correct
    }
    session['answers'] = answers

    # Зберігаємо в базу пройдених питань
    if test_session_id:
        try:
            answered = AnsweredQuestion.query.filter_by(
                user_id=current_user.id,
                question_id=question_id
            ).first()

            if not answered:
                answered = AnsweredQuestion(
                    user_id=current_user.id,
                    question_id=question_id,
                    is_correct=is_correct
                )
                db.session.add(answered)
            else:
                answered.is_correct = is_correct
                answered.answered_at = datetime.utcnow()

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            # Якщо запис вже існує - оновлюємо його
            answered = AnsweredQuestion.query.filter_by(
                user_id=current_user.id,
                question_id=question_id
            ).first()
            if answered:
                answered.is_correct = is_correct
                answered.answered_at = datetime.utcnow()
                db.session.commit()

    return jsonify({
        'correct': is_correct,
        'correct_answer': question.correct,
        'next_url': url_for('main.test_next')
    })

@main_bp.route('/test/next')
@login_required
def test_next():
    """Наступне питання"""
    current_index = session.get('current_index', 0)
    session['current_index'] = current_index + 1
    return redirect(url_for('main.test_question'))

@main_bp.route('/test/prev')
@login_required
def test_prev():
    """Попереднє питання"""
    current_index = session.get('current_index', 0)
    if current_index > 0:
        session['current_index'] = current_index - 1
    return redirect(url_for('main.test_question'))

@main_bp.route('/test/finish', methods=['GET', 'POST'])
@login_required
def test_finish():
    """Завершення тестування"""
    test_session_id = session.get('test_session_id')
    if not test_session_id:
        return redirect(url_for('main.dashboard'))

    test_session = TestSession.query.get(test_session_id)
    if not test_session:
        session.pop('test_session_id', None)
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST' or test_session.is_completed:
        # Підраховуємо результати
        answers_data = session.get('answers', {})
        questions = session.get('questions', [])

        # Спочатку видаляємо старі відповіді для цієї сесії (щоб уникнути дублікатів)
        Answer.query.filter_by(session_id=test_session.id).delete()

        correct_count = 0
        for qid, ans_data in answers_data.items():
            question = Question.query.get(int(qid))
            if not question:
                continue

            selected_option = ans_data.get('option') if isinstance(ans_data, dict) else ans_data
            selected_key = ans_data.get('key') if isinstance(ans_data, dict) else None

            # Перевіряємо правильність (перетворюємо на int для порівняння)
            correct_index = int(question.correct) if question.correct is not None else None
            is_correct = selected_option == correct_index if selected_option is not None and correct_index is not None else False

            # Зберігаємо відповідь в БД
            answer = Answer(
                session_id=test_session.id,
                question_id=int(qid),
                selected_option=selected_option,
                selected_key=selected_key,
                is_correct=is_correct
            )
            db.session.add(answer)

            if is_correct:
                correct_count += 1
            else:
                # Додаємо в помилки користувача
                mistake = UserMistake.query.filter_by(
                    user_id=current_user.id,
                    question_id=int(qid)
                ).first()

                if mistake:
                    mistake.mistake_count += 1
                    mistake.last_mistake_at = datetime.utcnow()
                else:
                    mistake = UserMistake(
                        user_id=current_user.id,
                        question_id=int(qid),
                        mistake_count=1
                    )
                    db.session.add(mistake)

        # Оновлюємо сесію
        test_session.correct_count = correct_count
        test_session.is_completed = True
        test_session.completed_at = datetime.utcnow()

        # Розраховуємо тривалість
        start_time = datetime.fromisoformat(session.get('start_time', datetime.utcnow().isoformat()))
        test_session.duration_seconds = int((datetime.utcnow() - start_time).total_seconds())

        db.session.commit()

        # Очищаємо сесію
        session.pop('test_session_id', None)
        session.pop('questions', None)
        session.pop('current_index', None)
        session.pop('answers', None)
        session.pop('shuffle_options', None)
        session.pop('start_time', None)
        session.pop('duration_seconds', None)

        return redirect(url_for('main.test_results', session_id=test_session.id))

    # Показуємо огляд перед завершенням
    questions = session.get('questions', [])
    answers = session.get('answers', {})
    question_objects = [Question.query.get(qid) for qid in questions]

    return render_template('test_finish.html',
                           questions=question_objects,
                           answers=answers,
                           test_session=test_session)

@main_bp.route('/test/results/<int:session_id>')
@login_required
def test_results(session_id):
    """Результати тестування"""
    test_session = TestSession.query.get_or_404(session_id)

    # Перевіряємо чи це сесія поточного користувача
    if test_session.user_id != current_user.id and not current_user.can_access_admin():
        flash('Доступ заборонено', 'danger')
        return redirect(url_for('main.dashboard'))

    answers = Answer.query.filter_by(session_id=session_id).all()

    return render_template('test_results.html',
                           test_session=test_session,
                           answers=answers)

# ==================== ЕКСПОРТ НАВЧАННЯ ====================

@main_bp.route('/study/export/<format>')
@login_required
def export_study(format):
    """Експорт питань для навчання"""
    questions = Question.query.all()

    # Фільтр за категорією якщо вказана
    category_code = request.args.get('category')
    if category_code:
        category = Category.query.filter_by(code=category_code).first()
        if category:
            questions = [q for q in questions if category in q.categories]

    if format == 'json':
        data = []
        for q in questions:
            data.append({
                'section': q.section,
                'text': q.text,
                'correct_answer': q.get_options()[q.correct],
                'image': q.image_base64
            })

        output = io.StringIO()
        json.dump(data, output, ensure_ascii=False, indent=2)
        output.seek(0)

        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='application/json',
            as_attachment=True,
            download_name='study_questions.json'
        )

    elif format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow(['section', 'question', 'correct_answer'])

        for q in questions:
            writer.writerow([q.section, q.text, q.get_options()[q.correct]])

        output.seek(0)

        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),
            mimetype='text/csv',
            as_attachment=True,
            download_name='study_questions.csv'
        )

    flash('Невідомий формат', 'danger')
    return redirect(url_for('main.dashboard'))

# ==================== СТАТИСТИКА ====================

@main_bp.route('/statistics')
@login_required
def statistics():
    """Сторінка статистики"""
    user_stats = get_user_statistics(current_user.id)

    # Статистика по розділах
    section_stats = db.session.query(
        Question.section,
        func.count(Question.id).label('total')
    ).group_by(Question.section).all()

    # Результати тестів
    test_sessions = TestSession.query.filter_by(
        user_id=current_user.id,
        is_completed=True
    ).order_by(TestSession.completed_at.desc()).all()

    return render_template('statistics.html',
                           user_stats=user_stats,
                           section_stats=section_stats,
                           test_sessions=test_sessions)

# ==================== РЕДАКТОР ПИТАНЬ ====================

@main_bp.route('/editor')
@login_required
@teacher_required
def editor():
    """Редактор питань"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    section_filter = request.args.get('section', '')
    category_filter = request.args.get('category', '')

    query = Question.query
    if section_filter:
        query = query.filter_by(section=section_filter)
    if category_filter:
        category = Category.query.filter_by(code=category_filter).first()
        if category:
            query = query.filter(Question.categories.contains(category))

    questions = query.order_by(Question.section, Question.id).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Отримуємо всі розділи для фільтра
    sections = db.session.query(Question.section).distinct().order_by(Question.section).all()
    sections = [s[0] for s in sections]

    # Отримуємо категорії
    categories = Category.query.all()

    return render_template('editor.html',
                           questions=questions,
                           sections=sections,
                           categories=categories,
                           section_filter=section_filter,
                           category_filter=category_filter)

@main_bp.route('/editor/add', methods=['GET', 'POST'])
@login_required
@teacher_required
def add_question():
    """Додавання нового питання"""
    if request.method == 'POST':
        correct_index = int(request.form.get('correct')) - 1  # 1-3 -> 0-2

        question = Question(
            section=request.form.get('section'),
            text=request.form.get('text'),
            option1=request.form.get('option1'),
            option2=request.form.get('option2'),
            option3=request.form.get('option3'),
            correct=correct_index,
            correct_key=['A', 'B', 'C'][correct_index],
            created_by=current_user.id
        )

        # Додаємо категорії
        categories = request.form.getlist('categories')
        for cat_code in categories:
            cat = Category.query.filter_by(code=cat_code).first()
            if cat:
                question.categories.append(cat)

        # Обробка зображення
        image_file = request.files.get('image')
        if image_file:
            import base64
            image_data = base64.b64encode(image_file.read()).decode('utf-8')
            question.image_base64 = f"data:{image_file.content_type};base64,{image_data}"

        db.session.add(question)
        db.session.commit()

        flash('Питання додано успішно', 'success')
        return redirect(url_for('main.editor'))

    categories = Category.query.all()
    return render_template('question_form.html', question=None, categories=categories)

@main_bp.route('/editor/edit/<int:question_id>', methods=['GET', 'POST'])
@login_required
@teacher_required
def edit_question(question_id):
    """Редагування питання"""
    question = Question.query.get_or_404(question_id)

    if request.method == 'POST':
        correct_index = int(request.form.get('correct')) - 1  # 1-3 -> 0-2

        question.section = request.form.get('section')
        question.text = request.form.get('text')
        question.option1 = request.form.get('option1')
        question.option2 = request.form.get('option2')
        question.option3 = request.form.get('option3')
        question.correct = correct_index
        question.correct_key = ['A', 'B', 'C'][correct_index]

        # Оновлюємо категорії
        question.categories = []
        categories = request.form.getlist('categories')
        for cat_code in categories:
            cat = Category.query.filter_by(code=cat_code).first()
            if cat:
                question.categories.append(cat)

        # Обробка зображення
        image_file = request.files.get('image')
        if image_file:
            import base64
            image_data = base64.b64encode(image_file.read()).decode('utf-8')
            question.image_base64 = f"data:{image_file.content_type};base64,{image_data}"

        # Видалення зображення
        if request.form.get('remove_image'):
            question.image_base64 = None

        db.session.commit()
        flash('Питання оновлено успішно', 'success')
        return redirect(url_for('main.editor'))

    categories = Category.query.all()
    return render_template('question_form.html', question=question, categories=categories)

@main_bp.route('/editor/delete/<int:question_id>', methods=['POST'])
@login_required
@teacher_required
def delete_question(question_id):
    """Видалення питання"""
    question = Question.query.get_or_404(question_id)

    try:
        # Спочатку видаляємо пов'язані записи
        # Відповіді користувачів
        Answer.query.filter_by(question_id=question_id).delete()

        # Помилки користувачів
        UserMistake.query.filter_by(question_id=question_id).delete()

        # Пройдені питання
        AnsweredQuestion.query.filter_by(question_id=question_id).delete()

        # Тепер видаляємо саме питання
        db.session.delete(question)
        db.session.commit()
        flash('Питання видалено', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Помилка видалення питання: {str(e)}', 'danger')

    return redirect(url_for('main.editor'))

@main_bp.route('/questions/delete-multiple', methods=['POST'])
@login_required
@teacher_required
def delete_multiple_questions():
    """Масове видалення питань"""
    from .models import Question, db
    
    # Отримуємо ID з прихованого поля (рядок з комами) або з чекбоксів
    question_ids_str = request.form.get('question_ids', '')
    if question_ids_str:
        question_ids = [int(id.strip()) for id in question_ids_str.split(',') if id.strip()]
    else:
        # Fallback на випадок, якщо прийшли окремі чекбокси
        question_ids = request.form.getlist('question_ids')
    
    if not question_ids:
        flash('Не вибрано жодного питання для видалення', 'warning')
        return redirect(url_for('main.editor'))
    
    deleted_count = 0
    errors = []
    
    for q_id in question_ids:
        try:
            question = Question.query.get(int(q_id))
            if question:
                db.session.delete(question)
                deleted_count += 1
            else:
                errors.append(f'Питання #{q_id} не знайдено')
        except Exception as e:
            errors.append(f'Помилка при видаленні #{q_id}: {str(e)}')
    
    try:
        db.session.commit()
        flash(f'Успішно видалено {deleted_count} питань', 'success')
        
        if errors:
            flash('Помилки: ' + '; '.join(errors[:3]), 'warning')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Помилка бази даних: {str(e)}', 'danger')
    
    return redirect(url_for('main.editor'))
    """Масове видалення питань"""
    question_ids = request.form.getlist('question_ids')

    if not question_ids:
        flash('Не вибрано жодного питання для видалення', 'warning')
        return redirect(url_for('main.editor'))

    deleted_count = 0
    errors = []

    for q_id in question_ids:
        try:
            question = Question.query.get(int(q_id))
            if question:
                # Видаляємо пов'язані записи
                Answer.query.filter_by(question_id=question.id).delete()
                UserMistake.query.filter_by(question_id=question.id).delete()
                AnsweredQuestion.query.filter_by(question_id=question.id).delete()

                db.session.delete(question)
                deleted_count += 1
            else:
                errors.append(f'Питання #{q_id} не знайдено')
        except Exception as e:
            errors.append(f'Помилка при видаленні #{q_id}: {str(e)}')

    try:
        db.session.commit()
        flash(f'Успішно видалено {deleted_count} питань', 'success')

        if errors:
            flash('Помилки: ' + '; '.join(errors[:3]), 'warning')

    except Exception as e:
        db.session.rollback()
        flash(f'Помилка бази даних: {str(e)}', 'danger')

    return redirect(url_for('main.editor'))

@main_bp.route('/questions/update-categories', methods=['POST'])
@login_required
@teacher_required
def update_categories():
    """Масове оновлення категорій питань"""
    from .models import Question, Category, db
    
    # Отримуємо список ID питань
    question_ids_str = request.form.get('question_ids', '')
    if not question_ids_str:
        flash('Не вибрано жодного питання', 'warning')
        return redirect(url_for('main.editor'))
    
    question_ids = [int(id.strip()) for id in question_ids_str.split(',') if id.strip()]
    
    # Отримуємо дію та категорію
    action = request.form.get('action')  # 'add' або 'remove'
    category_code = request.form.get('category_code')  # 'MS', 'GC' або 'all'
    
    if not action:
        flash('Не вказано дію', 'danger')
        return redirect(url_for('main.editor'))
    
    # Отримуємо об'єкти категорій
    categories_to_modify = []
    if category_code == 'MS':
        cat = Category.query.filter_by(code='MS').first()
        if cat:
            categories_to_modify.append(cat)
    elif category_code == 'GC':
        cat = Category.query.filter_by(code='GC').first()
        if cat:
            categories_to_modify.append(cat)
    
    updated_count = 0
    
    for qid in question_ids:
        question = Question.query.get(qid)
        if not question:
            continue
        
        if action == 'add':
            # Додаємо категорії (якщо ще немає)
            for cat in categories_to_modify:
                if cat not in question.categories:
                    question.categories.append(cat)
            updated_count += 1
            
        elif action == 'remove':
            if category_code == 'all':
                # Видаляємо всі категорії
                question.categories = []
            else:
                # Видаляємо конкретну категорію
                for cat in categories_to_modify:
                    if cat in question.categories:
                        question.categories.remove(cat)
            updated_count += 1
    
    db.session.commit()
    
    # Формуємо повідомлення
    if action == 'add':
        cat_names = ' + '.join([c.code for c in categories_to_modify])
        flash(f'Оновлено {updated_count} питань: додано категорію {cat_names}', 'success')
    else:
        if category_code == 'all':
            flash(f'Оновлено {updated_count} питань: категорії прибрано', 'success')
        else:
            cat_names = ' + '.join([c.code for c in categories_to_modify])
            flash(f'Оновлено {updated_count} питань: прибрано категорію {cat_names}', 'success')
    
    return redirect(url_for('main.editor'))

# ==================== ІМПОРТ/ЕКСПОРТ ====================

@main_bp.route('/import', methods=['GET', 'POST'])
@login_required
@teacher_required
def import_questions():
    """Імпорт питань з файлів (мульти-імпорт з категорією, зворотна сумісність)"""
    from .models import Question, QuestionBank, Category
    
    if request.method == 'POST':
        # 🔧 ЗВОРОТНЯ СУМІСНІСТЬ: підтримуємо і 'files' (новий), і 'file' (старий)
        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            # Спробуємо старий варіант з одним файлом
            single_file = request.files.get('file')
            if single_file and single_file.filename:
                files = [single_file]
            else:
                flash('Будь ласка, виберіть файл', 'warning')
                return redirect(url_for('main.import_questions'))
        
        category_code = request.form.get('category', 'MS')  # MS, GC, або BOTH
        delimiter = request.form.get('delimiter', ';')
        
        # Отримуємо категорії для призначення
        categories_to_add = []
        if category_code in ['MS', 'BOTH']:
            ms_cat = Category.query.filter_by(code='MS').first()
            if ms_cat:
                categories_to_add.append(ms_cat)
        if category_code in ['GC', 'BOTH']:
            gc_cat = Category.query.filter_by(code='GC').first()
            if gc_cat:
                categories_to_add.append(gc_cat)
        
        # Отримуємо системну базу
        system_bank = QuestionBank.query.filter_by(level='system', is_default=True).first()
        if not system_bank:
            flash('Системна база питань не знайдена', 'danger')
            return redirect(url_for('main.import_questions'))
        
        total_imported = 0
        file_results = []
        
        for file in files:
            if file.filename == '':
                continue
            
            # Зберігаємо файл
            filepath = f"import/{file.filename}"
            os.makedirs('import', exist_ok=True)
            file.save(filepath)
            
            imported = 0
            
            try:
                if file.filename.lower().endswith('.json'):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    for item in data:
                        question = Question(
                            bank_id=system_bank.id,
                            section=item.get('section', '1'),
                            text=item.get('text', ''),
                            option1=item.get('option1', item.get('options', ['', '', ''])[0] if isinstance(item.get('options'), list) else ''),
                            option2=item.get('option2', item.get('options', ['', '', ''])[1] if isinstance(item.get('options'), list) else ''),
                            option3=item.get('option3', item.get('options', ['', '', ''])[2] if isinstance(item.get('options'), list) else ''),
                            correct=int(item.get('correct', 0)),
                            image_base64=item.get('image_base64'),
                            created_by=current_user.id
                        )
                        # Призначаємо категорії
                        for cat in categories_to_add:
                            question.categories.append(cat)
                        
                        db.session.add(question)
                        imported += 1
                
                elif file.filename.lower().endswith('.csv'):
                    with open(filepath, 'r', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f, delimiter=delimiter)
                        
                        for row in reader:
                            question = Question(
                                bank_id=system_bank.id,
                                section=row.get('section', '1'),
                                text=row.get('text', row.get('question', '')),
                                option1=row.get('option1', ''),
                                option2=row.get('option2', ''),
                                option3=row.get('option3', ''),
                                correct=int(row.get('correct', 0)),
                                image_base64=row.get('image_base64'),
                                created_by=current_user.id
                            )
                            # Призначаємо категорії
                            for cat in categories_to_add:
                                question.categories.append(cat)
                            
                            db.session.add(question)
                            imported += 1
                
                db.session.commit()
                total_imported += imported
                file_results.append(f'{file.filename}: {imported} питань')
                
            except Exception as e:
                db.session.rollback()
                flash(f'Помилка в {file.filename}: {str(e)}', 'danger')
            
            # Видаляємо тимчасовий файл
            try:
                os.remove(filepath)
            except:
                pass
        
        # Повідомлення про результат
        cat_names = ' + '.join([c.code for c in categories_to_add]) if categories_to_add else 'без категорії'
        flash(f'Імпортовано {total_imported} питань (категорії: {cat_names})', 'success')
        
        for result in file_results:
            flash(result, 'info')
        
        return redirect(url_for('main.editor'))
    
    # GET - показуємо форму зі статистикою
    stats = {
        'total': Question.query.count(),
        'with_images': Question.query.filter(Question.image_base64.isnot(None)).count(),
        'ms_count': Question.query.filter(Question.categories.any(code='MS')).count(),
        'gc_count': Question.query.filter(Question.categories.any(code='GC')).count()
    }
    return render_template('import.html', stats=stats)

@main_bp.route('/export/<format>')
@login_required
@teacher_required
def export_questions(format):
    """Експорт питань з завантаженням файлу"""
    import tempfile

    if format == 'json':
        # Створюємо тимчасовий файл
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            filepath = f.name

        count = export_to_json(filepath)

        return send_file(
            filepath,
            mimetype='application/json',
            as_attachment=True,
            download_name=f'questions_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        )

    elif format == 'csv':
        # Створюємо тимчасовий файл
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8-sig', newline='') as f:
            filepath = f.name

        count = export_to_csv(filepath)

        return send_file(
            filepath,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'questions_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
    else:
        flash('Невідомий формат', 'danger')

    return redirect(url_for('main.editor'))

# ==================== АДМІНІСТРУВАННЯ ====================

@main_bp.route('/admin')
@login_required
@admin_required
def admin():
    """Адмін-панель"""
    # Фільтрація даних залежно від ролі
    if current_user.role == 'system_admin':
        # Системний адміністратор бачить все
        total_users = User.query.count()
        total_questions = Question.query.count()
        total_tests = TestSession.query.filter_by(is_completed=True).count()
        total_schools = School.query.count()

        # Користувачі (всі, крім інших системних адміністраторів для редагування)
        users = User.query.order_by(User.account_created_at.desc()).limit(50).all()

        # Заклади
        schools = School.query.all()

        # Викладачі для призначення
        teachers = User.query.filter(User.role.in_(['teacher', 'school_admin', 'system_admin'])).all()

    elif current_user.role == 'school_admin':
        # Адміністратор школи бачить тільки свою школу та її користувачів
        total_users = User.query.filter_by(school_id=current_user.school_id).count()
        total_questions = Question.query.count()
        total_tests = TestSession.query.filter_by(is_completed=True).count()
        total_schools = 1

        # Користувачі тільки зі своєї школи (не системні адміністратори)
        users = User.query.filter(
            User.school_id == current_user.school_id,
            User.role != 'system_admin'
        ).order_by(User.account_created_at.desc()).all()

        # Заклади (тільки своя)
        schools = School.query.filter_by(id=current_user.school_id).all()

        # Викладачі для призначення (тільки зі своєї школи)
        teachers = User.query.filter(
            User.school_id == current_user.school_id,
            User.role.in_(['teacher', 'school_admin'])
        ).all()
    else:
        # Викладач - перенаправляємо на дашборд
        return redirect(url_for('main.dashboard'))

    # Категорії
    categories = Category.query.all()

    return render_template('admin.html',

                           total_users=total_users,
                           total_questions=total_questions,
                           total_tests=total_tests,
                           total_schools=total_schools,
                           users=users,
                           schools=schools,
                           categories=categories,
                           teachers=teachers)

# Аліас для сумісності з admin.html
@main_bp.route('/admin/user/edit-compat', methods=['POST'])
@login_required
@admin_required
def admin_edit_user():
    """Сумісність: старе ім'я для edit_user"""
    return edit_user()
    
@main_bp.route('/admin/user/add', methods=['POST'])
@login_required
@admin_required
def add_user():
    """Додавання користувача"""
    from flask import current_app

    role = request.form.get('role')
    school_id = request.form.get('school_id') or None

    # Перевірки для адміністратора школи
    if current_user.role == 'school_admin':
        # Може додавати тільки слухачів та викладачів
        if role not in ['student', 'teacher']:
            flash('Ви можете додавати тільки слухачів та викладачів', 'danger')
            return redirect(url_for('main.admin'))

        # Прив'язуємо до своєї школи
        school_id = current_user.school_id

    user = User(
        username=request.form.get('username'),
        last_name=request.form.get('last_name'),
        first_name=request.form.get('first_name'),
        middle_name=request.form.get('middle_name'),
        phone=request.form.get('phone'),
        email=request.form.get('email'),
        role=role,
        school_id=school_id,
        is_active=request.form.get('is_active') == 'on',
        must_change_password=True
    )

    # Встановлюємо пароль за замовчуванням
    user.set_password(current_app.config['DEFAULT_PASSWORD'])

    # Термін дії
    expiry_type = request.form.get('expiry_type', 'unlimited')
    if expiry_type == 'days':
        days = int(request.form.get('expiry_days', 30))
        user.activate_for_days(days)
    elif expiry_type == 'date':
        date_str = request.form.get('expiry_date')
        if date_str:
            user.account_expires_at = datetime.fromisoformat(date_str)

    db.session.add(user)
    db.session.commit()

    flash(f'Користувача додано. Пароль: {current_app.config["DEFAULT_PASSWORD"]}', 'success')
    return redirect(url_for('main.admin'))

@main_bp.route('/admin/user/edit/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Редагування користувача"""
    user = User.query.get_or_404(user_id)

    # Перевірка прав доступу
    if not current_user.can_edit_user(user):
        flash('У вас немає прав для редагування цього користувача', 'danger')
        return redirect(url_for('main.admin'))

    # Для адміністратора школи - перевірка ролі
    if current_user.role == 'school_admin':
        new_role = request.form.get('role')
        if new_role not in ['student', 'teacher']:
            flash('Ви можете призначати тільки ролі слухача та викладача', 'danger')
            return redirect(url_for('main.admin'))

    user.last_name = request.form.get('last_name')
    user.first_name = request.form.get('first_name')
    user.middle_name = request.form.get('middle_name')
    user.phone = request.form.get('phone')
    user.email = request.form.get('email')
    user.role = request.form.get('role')

    # Для адміністратора школи - не змінюємо школу
    if current_user.role == 'system_admin':
        user.school_id = request.form.get('school_id') or None

    # Термін дії
    expiry_type = request.form.get('expiry_type', 'unlimited')
    if expiry_type == 'days':
        days = int(request.form.get('expiry_days', 30))
        user.activate_for_days(days)
    elif expiry_type == 'date':
        date_str = request.form.get('expiry_date')
        if date_str:
            user.account_expires_at = datetime.fromisoformat(date_str)
    elif expiry_type == 'unlimited':
        user.account_expires_at = None

    db.session.commit()
    flash('Дані користувача оновлено', 'success')
    return redirect(url_for('main.admin'))

@main_bp.route('/admin/user/reset-password/<int:user_id>')
@login_required
@admin_required
def reset_password(user_id):
    """Скидання пароля користувача"""
    from flask import current_app

    user = User.query.get_or_404(user_id)

    # Перевірка прав доступу
    if not current_user.can_edit_user(user):
        flash('У вас немає прав для скидання пароля цього користувача', 'danger')
        return redirect(url_for('main.admin'))

    user.set_password(current_app.config['DEFAULT_PASSWORD'])
    user.must_change_password = True
    db.session.commit()

    flash(f'Пароль скинуто. Новий пароль: {current_app.config["DEFAULT_PASSWORD"]}', 'success')
    return redirect(url_for('main.admin'))

@main_bp.route('/admin/user/toggle/<int:user_id>')
@login_required
@admin_required
def toggle_user(user_id):
    """Активація/деактивація користувача"""
    user = User.query.get_or_404(user_id)

    # Перевірка прав доступу
    if not current_user.can_edit_user(user):
        flash('У вас немає прав для зміни статусу цього користувача', 'danger')
        return redirect(url_for('main.admin'))

    user.is_active = not user.is_active
    db.session.commit()

    status = 'активовано' if user.is_active else 'деактивовано'
    flash(f'Користувача {status}', 'success')
    return redirect(url_for('main.admin'))

@main_bp.route('/admin/user/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Видалення користувача"""
    user = User.query.get_or_404(user_id)

    # Не дозволяємо видалити самого себе
    if user.id == current_user.id:
        flash('Ви не можете видалити власний обліковий запис', 'danger')
        return redirect(url_for('main.admin'))

    # Перевірка прав доступу
    if not current_user.can_edit_user(user):
        flash('У вас немає прав для видалення цього користувача', 'danger')
        return redirect(url_for('main.admin'))

    # Видаляємо пов'язані дані
    TestSession.query.filter_by(user_id=user.id).delete()
    UserMistake.query.filter_by(user_id=user.id).delete()
    AnsweredQuestion.query.filter_by(user_id=user.id).delete()
    LoginLog.query.filter_by(user_id=user.id).delete()

    username = user.username
    db.session.delete(user)
    db.session.commit()

    flash(f'Користувача {username} видалено', 'success')
    return redirect(url_for('main.admin'))

@main_bp.route('/admin/user/reset-stats/<int:user_id>')
@login_required
@admin_required
def reset_user_stats(user_id):
    """Скидання статистики користувача"""
    user = User.query.get_or_404(user_id)

    # Перевірка прав доступу
    if not current_user.can_edit_user(user):
        flash('У вас немає прав для скидання статистики цього користувача', 'danger')
        return redirect(url_for('main.admin'))

    # Видаляємо всі тести користувача
    TestSession.query.filter_by(user_id=user.id).delete()

    # Видаляємо помилки
    UserMistake.query.filter_by(user_id=user.id).delete()

    # Видаляємо пройдені питання
    AnsweredQuestion.query.filter_by(user_id=user.id).delete()

    db.session.commit()

    flash(f'Статистику користувача {user.username} скинуто', 'success')
    return redirect(url_for('main.admin'))

@main_bp.route('/admin/user/<int:user_id>/login-logs')
@login_required
@admin_required
def user_login_logs(user_id):
    """Логи входів користувача"""
    user = User.query.get_or_404(user_id)

    # Перевірка прав доступу для адміністратора школи
    if current_user.role == 'school_admin':
        # Може переглядати логи тільки користувачів своєї школи
        if user.school_id != current_user.school_id:
            flash('У вас немає прав для перегляду логів цього користувача', 'danger')
            return redirect(url_for('main.admin'))

    logs = LoginLog.query.filter_by(user_id=user.id).order_by(LoginLog.login_at.desc()).all()
    return render_template('login_logs.html', user=user, logs=logs)

@main_bp.route('/admin/user/assign-teacher', methods=['POST'])
@login_required
@admin_required
def assign_teacher():
    """Призначення викладача слухачу"""
    student_id = request.form.get('student_id')
    teacher_id = request.form.get('teacher_id')

    student = User.query.get_or_404(student_id)
    teacher = User.query.get_or_404(teacher_id)

    # Перевірка прав доступу для адміністратора школи
    if current_user.role == 'school_admin':
        # Може призначати викладачів тільки для слухачів своєї школи
        if student.school_id != current_user.school_id:
            flash('У вас немає прав для призначення викладача цьому слухачу', 'danger')
            return redirect(url_for('main.admin'))
        # Викладач має бути з тієї ж школи
        if teacher.school_id != current_user.school_id:
            flash('Викладач має бути з вашого закладу', 'danger')
            return redirect(url_for('main.admin'))

    # Перевіряємо що користувач - слухач
    if student.role != 'student':
        flash('Можна призначати викладача тільки для слухачів', 'danger')
        return redirect(url_for('main.admin'))

    # Перевіряємо що призначений користувач - викладач або адмін
    if teacher.role not in ['teacher', 'school_admin', 'system_admin']:
        flash('Викладачем може бути тільки користувач з відповідною роллю', 'danger')
        return redirect(url_for('main.admin'))

    # Оновлюємо teacher_id для слухача
    student.teacher_id = teacher.id
    db.session.commit()

    flash(f'Викладача {teacher.get_full_name() or teacher.username} призначено для слухача {student.get_full_name() or student.username}', 'success')
    return redirect(url_for('main.admin'))

@main_bp.route('/admin/user/<int:user_id>/data')
@login_required
@admin_required
def get_user_data(user_id):
    """Отримання даних користувача для редагування (AJAX)"""
    user = User.query.get_or_404(user_id)

    # Перевірка прав доступу для адміністратора школи
    if current_user.role == 'school_admin':
        # Може отримувати дані тільки користувачів своєї школи
        if user.school_id != current_user.school_id:
            return jsonify({'error': 'Access denied'}), 403

    return jsonify({
        'id': user.id,
        'username': user.username,
        'last_name': user.last_name,
        'first_name': user.first_name,
        'middle_name': user.middle_name,
        'phone': user.phone,
        'email': user.email,
        'role': user.role,
        'school_id': user.school_id,
        'is_active': user.is_active,
        'account_expires_at': user.account_expires_at.isoformat() if user.account_expires_at else None
    })

@main_bp.route('/admin/school/add', methods=['POST'])
@login_required
@admin_required
def add_school():
    """Додавання закладу (тільки для системного адміністратора)"""
    # Тільки системний адміністратор може додавати школи
    if current_user.role != 'system_admin':
        flash('У вас немає прав для додавання закладів', 'danger')
        return redirect(url_for('main.admin'))

    school = School(
        name=request.form.get('name'),
        address=request.form.get('address'),
        phone=request.form.get('phone'),
        email=request.form.get('email')
    )
    db.session.add(school)
    db.session.commit()

    flash('Заклад додано', 'success')
    return redirect(url_for('main.admin'))

@main_bp.route('/admin/users/export/<format>')
@login_required
@admin_required
def export_users(format):
    """Експорт користувачів (тільки для системного адміністратора)"""
    # Тільки системний адміністратор може експортувати користувачів
    if current_user.role != 'system_admin':
        flash('У вас немає прав для експорту користувачів', 'danger')
        return redirect(url_for('main.admin'))

    import tempfile

    if format == 'json':
        # Створюємо тимчасовий файл
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            filepath = f.name

        count = export_users_to_json(filepath)

        return send_file(
            filepath,
            mimetype='application/json',
            as_attachment=True,
            download_name=f'users_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        )

    elif format == 'csv':
        # Створюємо тимчасовий файл
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8-sig', newline='') as f:
            filepath = f.name
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['username', 'last_name', 'first_name', 'middle_name', 'phone', 'email', 'role', 'school_id', 'is_active'])
            for u in User.query.all():
                writer.writerow([u.username, u.last_name, u.first_name, u.middle_name, u.phone, u.email, u.role, u.school_id, u.is_active])

        return send_file(
            filepath,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'users_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )

    return redirect(url_for('main.admin'))

@main_bp.route('/admin/users/import', methods=['POST'])
@login_required
@admin_required
def import_users():
    """Імпорт користувачів (тільки для системного адміністратора)"""
    # Тільки системний адміністратор може імпортувати користувачів
    if current_user.role != 'system_admin':
        flash('У вас немає прав для імпорту користувачів', 'danger')
        return redirect(url_for('main.admin'))

    file = request.files.get('file')
    if not file:
        flash('Будь ласка, виберіть файл', 'warning')
        return redirect(url_for('main.admin'))

    filepath = f"import/{file.filename}"
    file.save(filepath)

    imported, skipped, msg = import_users_from_json(filepath)

    if imported > 0:
        flash(f'Імпорт завершено: {msg}', 'success')
    else:
        flash(f'Імпорт не вдався: {msg}', 'danger')

    return redirect(url_for('main.admin'))

# ==================== ПРОФІЛЬ КОРИСТУВАЧА ====================

@main_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Профіль користувача"""
    if request.method == 'POST':
        current_user.last_name = request.form.get('last_name')
        current_user.first_name = request.form.get('first_name')
        current_user.middle_name = request.form.get('middle_name')
        current_user.phone = request.form.get('phone')
        current_user.email = request.form.get('email')

        # Завантаження аватара
        avatar_file = request.files.get('avatar')
        if avatar_file:
            import base64
            avatar_data = base64.b64encode(avatar_file.read()).decode('utf-8')
            current_user.avatar_url = f"data:{avatar_file.content_type};base64,{avatar_data}"

        db.session.commit()
        flash('Профіль оновлено', 'success')
        return redirect(url_for('main.profile'))

    user_stats = get_user_statistics(current_user.id)
    return render_template('profile.html', user_stats=user_stats)

@main_bp.route('/profile/reset-stats', methods=['POST'])
@login_required
def reset_my_stats():
    """Скидання власної статистики"""
    # Видаляємо всі тести користувача
    TestSession.query.filter_by(user_id=current_user.id).delete()

    # Видаляємо помилки
    UserMistake.query.filter_by(user_id=current_user.id).delete()

    # Видаляємо пройдені питання
    AnsweredQuestion.query.filter_by(user_id=current_user.id).delete()

    db.session.commit()

    flash('Вашу статистику скинуто', 'success')
    return redirect(url_for('main.statistics'))

# ==================== API МАРШРУТИ ====================

@main_bp.route('/api/questions')
@login_required
def api_questions():
    """API: отримання списку питань"""
    section = request.args.get('section')
    category = request.args.get('category')

    query = Question.query
    if section:
        query = query.filter_by(section=section)
    if category:
        cat = Category.query.filter_by(code=category).first()
        if cat:
            query = query.filter(Question.categories.contains(cat))

    questions = query.all()
    return jsonify([q.to_dict() for q in questions])

@main_bp.route('/api/sections')
@login_required
def api_sections():
    """API: отримання списку розділів"""
    sections = db.session.query(Question.section).distinct().order_by(Question.section).all()
    return jsonify([s[0] for s in sections])

@main_bp.route('/api/categories')
@login_required
def api_categories():
    """API: отримання списку категорій"""
    categories = Category.query.all()
    return jsonify([{'code': c.code, 'name': c.name} for c in categories])

@main_bp.route('/api/stats')
@login_required
def api_stats():
    """API: статистика користувача"""
    stats = get_user_statistics(current_user.id)
    return jsonify({
        'total_tests': stats['total_tests'],
        'average_score': stats['average_score'],
        'mistakes_count': stats['mistakes_count'],
        'answered_count': stats['answered_count']
    })

# ==================== УПРАВЛІННЯ ГРУПАМИ ====================

@main_bp.route('/groups')
@login_required
@admin_required
def groups_list():
    """Список груп"""
    if current_user.role == 'system_admin':
        groups = Group.query.order_by(Group.created_at.desc()).all()
        schools = School.query.all()
    elif current_user.role == 'school_admin':
        groups = Group.query.filter_by(school_id=current_user.school_id).order_by(Group.created_at.desc()).all()
        schools = School.query.filter_by(id=current_user.school_id).all()
    else:  # teacher
        groups = Group.query.filter_by(teacher_id=current_user.id).order_by(Group.created_at.desc()).all()
        schools = []

    # Отримуємо список викладачів для фільтра
    if current_user.role == 'system_admin':
        teachers = User.query.filter(User.role.in_(['teacher', 'school_admin'])).all()
    elif current_user.role == 'school_admin':
        teachers = User.query.filter_by(school_id=current_user.school_id).filter(User.role.in_(['teacher', 'school_admin'])).all()
    else:
        teachers = [current_user]

    # Отримуємо список слухачів для додавання в групу
    if current_user.role == 'system_admin':
        students = User.query.filter_by(role='student').all()
    elif current_user.role == 'school_admin':
        students = User.query.filter_by(role='student', school_id=current_user.school_id).all()
    else:
        students = User.query.filter_by(role='student', teacher_id=current_user.id).all()

    return render_template('groups.html', groups=groups, teachers=teachers, students=students, schools=schools)

@main_bp.route('/groups/add', methods=['POST'])
@login_required
@admin_required
def add_group():
    """Додавання групи"""
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    teacher_id = request.form.get('teacher_id')
    student_ids = request.form.getlist('student_ids')

    if not name:
        flash('Назва групи обов\'язкова', 'danger')
        return redirect(url_for('main.groups_list'))

    # Визначаємо школу
    if current_user.role == 'school_admin':
        school_id = current_user.school_id
    elif current_user.role == 'teacher':
        school_id = current_user.school_id
        teacher_id = current_user.id
    else:  # system_admin
        school_id = request.form.get('school_id')
        if not school_id:
            flash('Будь ласка, виберіть школу', 'danger')
            return redirect(url_for('main.groups_list'))
        school_id = int(school_id)

    group = Group(
        name=name,
        description=description,
        school_id=school_id,
        teacher_id=teacher_id
    )

    # Додаємо слухачів з перевіркою школи (для системного адміністратора)
    for student_id in student_ids:
        student = User.query.get(int(student_id))
        if student and student.role == 'student':
            # Перевірка: слухач має бути з тієї ж школи
            if current_user.role == 'system_admin' and student.school_id != school_id:
                flash(f'Помилка: слухач {student.get_full_name() or student.username} не належить до вибраної школи', 'danger')
                return redirect(url_for('main.groups_list'))
            group.students.append(student)

    db.session.add(group)
    db.session.commit()

    flash(f'Групу "{name}" створено', 'success')
    return redirect(url_for('main.groups_list'))

@main_bp.route('/groups/<int:group_id>')
@login_required
@admin_required
def group_detail(group_id):
    """Деталі групи"""
    group = Group.query.get_or_404(group_id)

    # Перевірка прав доступу
    if current_user.role == 'school_admin' and group.school_id != current_user.school_id:
        flash('У вас немає прав для перегляду цієї групи', 'danger')
        return redirect(url_for('main.groups_list'))
    if current_user.role == 'teacher' and group.teacher_id != current_user.id:
        flash('У вас немає прав для перегляду цієї групи', 'danger')
        return redirect(url_for('main.groups_list'))

    # Отримуємо категорії для створення іспиту
    categories = Category.query.all()

    # Отримуємо доступні питання для ручного формування білетів
    questions = Question.query.filter_by(bank_id=1).all()  # system bank

    # Отримуємо список слухачів для додавання в групу
    if current_user.role == 'system_admin':
        students = User.query.filter_by(role='student').all()
    elif current_user.role == 'school_admin':
        students = User.query.filter_by(role='student', school_id=current_user.school_id).all()
    else:
        students = User.query.filter_by(role='student', teacher_id=current_user.id).all()

    return render_template('group_detail.html', group=group, categories=categories, questions=questions, students=students)

@main_bp.route('/groups/<int:group_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_group(group_id):
    """Редагування групи"""
    group = Group.query.get_or_404(group_id)

    # Перевірка прав доступу
    if current_user.role == 'school_admin' and group.school_id != current_user.school_id:
        flash('У вас немає прав для редагування цієї групи', 'danger')
        return redirect(url_for('main.groups_list'))
    if current_user.role == 'teacher' and group.teacher_id != current_user.id:
        flash('У вас немає прав для редагування цієї групи', 'danger')
        return redirect(url_for('main.groups_list'))

    group.name = request.form.get('name', '').strip()
    group.description = request.form.get('description', '').strip()

    # Оновлюємо викладача (тільки для адміністраторів)
    if current_user.role in ['system_admin', 'school_admin']:
        teacher_id = request.form.get('teacher_id')
        if teacher_id:
            group.teacher_id = int(teacher_id)

    db.session.commit()
    flash('Групу оновлено', 'success')
    return redirect(url_for('main.group_detail', group_id=group.id))

@main_bp.route('/groups/<int:group_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_group(group_id):
    """Видалення групи"""
    group = Group.query.get_or_404(group_id)

    # Перевірка прав доступу
    if current_user.role == 'school_admin' and group.school_id != current_user.school_id:
        flash('У вас немає прав для видалення цієї групи', 'danger')
        return redirect(url_for('main.groups_list'))
    if current_user.role == 'teacher' and group.teacher_id != current_user.id:
        flash('У вас немає прав для видалення цієї групи', 'danger')
        return redirect(url_for('main.groups_list'))

    name = group.name
    db.session.delete(group)
    db.session.commit()

    flash(f'Групу "{name}" видалено', 'success')
    return redirect(url_for('main.groups_list'))

@main_bp.route('/groups/<int:group_id>/students/add', methods=['POST'])
@login_required
@admin_required
def add_student_to_group(group_id):
    """Додавання слухача до групи"""
    group = Group.query.get_or_404(group_id)

    # Перевірка прав доступу
    if current_user.role == 'school_admin' and group.school_id != current_user.school_id:
        flash('У вас немає прав', 'danger')
        return redirect(url_for('main.group_detail', group_id=group.id))
    if current_user.role == 'teacher' and group.teacher_id != current_user.id:
        flash('У вас немає прав', 'danger')
        return redirect(url_for('main.group_detail', group_id=group.id))

    student_id = request.form.get('student_id')
    student = User.query.get_or_404(student_id)

    if student not in group.students:
        group.students.append(student)
        db.session.commit()
        flash(f'Слухача {student.get_full_name() or student.username} додано до групи', 'success')
    else:
        flash('Цей слухач вже в групі', 'warning')

    return redirect(url_for('main.group_detail', group_id=group.id))

@main_bp.route('/groups/<int:group_id>/students/<int:student_id>/remove', methods=['POST'])
@login_required
@admin_required
def remove_student_from_group(group_id, student_id):
    """Видалення слухача з групи"""
    group = Group.query.get_or_404(group_id)
    student = User.query.get_or_404(student_id)

    # Перевірка прав доступу
    if current_user.role == 'school_admin' and group.school_id != current_user.school_id:
        flash('У вас немає прав', 'danger')
        return redirect(url_for('main.group_detail', group_id=group.id))
    if current_user.role == 'teacher' and group.teacher_id != current_user.id:
        flash('У вас немає прав', 'danger')
        return redirect(url_for('main.group_detail', group_id=group.id))

    if student in group.students:
        group.students.remove(student)
        db.session.commit()
        flash(f'Слухача {student.get_full_name() or student.username} видалено з групи', 'success')

    return redirect(url_for('main.group_detail', group_id=group.id))

# ==================== УПРАВЛІННЯ ШКІЛЬНИМИ ІСПИТАМИ ====================

@main_bp.route('/groups/<int:group_id>/exams/add', methods=['POST'])
@login_required
@admin_required
def add_school_exam(group_id):
    """Створення шкільного іспиту"""
    group = Group.query.get_or_404(group_id)

    # Перевірка прав доступу
    if current_user.role == 'school_admin' and group.school_id != current_user.school_id:
        flash('У вас немає прав', 'danger')
        return redirect(url_for('main.group_detail', group_id=group.id))
    if current_user.role == 'teacher' and group.teacher_id != current_user.id:
        flash('У вас немає прав', 'danger')
        return redirect(url_for('main.group_detail', group_id=group.id))

    name = request.form.get('name', '').strip()
    category_id = request.form.get('category_id')
    question_count = int(request.form.get('question_count', 10))
    time_minutes = int(request.form.get('time_minutes', 20))
    max_errors = int(request.form.get('max_errors', 2))
    question_selection_type = request.form.get('question_selection_type', 'random')

    exam = SchoolExam(
        group_id=group_id,
        category_id=category_id,
        name=name,
        question_count=question_count,
        time_minutes=time_minutes,
        max_errors=max_errors,
        question_selection_type=question_selection_type,
        is_active=False
    )

    db.session.add(exam)
    db.session.commit()

    # Якщо вибрано ручний вибір питань, додаємо їх
    if question_selection_type == 'manual':
        question_ids = request.form.getlist('question_ids')
        for i, qid in enumerate(question_ids[:question_count]):
            exam_question = SchoolExamQuestion(
                exam_id=exam.id,
                question_id=int(qid),
                order=i
            )
            db.session.add(exam_question)
        db.session.commit()

    flash(f'Іспит "{name}" створено', 'success')
    return redirect(url_for('main.group_detail', group_id=group.id))

@main_bp.route('/school-exams/<int:exam_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_school_exam(exam_id):
    """Активація/деактивація іспиту"""
    exam = SchoolExam.query.get_or_404(exam_id)
    group = exam.group

    # Перевірка прав доступу
    if current_user.role == 'school_admin' and group.school_id != current_user.school_id:
        flash('У вас немає прав', 'danger')
        return redirect(url_for('main.group_detail', group_id=group.id))
    if current_user.role == 'teacher' and group.teacher_id != current_user.id:
        flash('У вас немає прав', 'danger')
        return redirect(url_for('main.group_detail', group_id=group.id))

    exam.is_active = not exam.is_active
    if exam.is_active:
        exam.activated_at = datetime.utcnow()
        exam.activated_by_id = current_user.id
    else:
        exam.activated_at = None
        exam.activated_by_id = None

    db.session.commit()

    status = 'активовано' if exam.is_active else 'деактивовано'
    flash(f'Іспит {status}', 'success')
    return redirect(url_for('main.group_detail', group_id=group.id))

@main_bp.route('/school-exams/<int:exam_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_school_exam(exam_id):
    """Видалення іспиту"""
    exam = SchoolExam.query.get_or_404(exam_id)
    group = exam.group
    group_id = group.id

    # Перевірка прав доступу
    if current_user.role == 'school_admin' and group.school_id != current_user.school_id:
        flash('У вас немає прав', 'danger')
        return redirect(url_for('main.group_detail', group_id=group_id))
    if current_user.role == 'teacher' and group.teacher_id != current_user.id:
        flash('У вас немає прав', 'danger')
        return redirect(url_for('main.group_detail', group_id=group_id))

    name = exam.name
    db.session.delete(exam)
    db.session.commit()

    flash(f'Іспит "{name}" видалено', 'success')
    return redirect(url_for('main.group_detail', group_id=group_id))

# ==================== ПРОХОДЖЕННЯ ІСПИТУ СЛУХАЧЕМ ====================

@main_bp.route('/school-exams')
@login_required
def my_school_exams():
    """Список доступних іспитів для слухача"""
    if current_user.role != 'student':
        return redirect(url_for('main.dashboard'))

    # Отримуємо всі активні іспити для груп, в яких є слухач
    available_exams = []
    for group in current_user.student_groups:
        for exam in group.exams:
            if exam.is_available():
                # Перевіряємо, чи слухач вже проходив цей іспит
                existing_result = SchoolExamResult.query.filter_by(
                    exam_id=exam.id,
                    user_id=current_user.id
                ).first()

                if not existing_result or existing_result.status != 'completed':
                    available_exams.append({
                        'exam': exam,
                        'group': group,
                        'result': existing_result
                    })

    # Отримуємо завершені іспити
    completed_results = SchoolExamResult.query.filter_by(
        user_id=current_user.id,
        status='completed'
    ).order_by(SchoolExamResult.completed_at.desc()).all()

    return render_template('my_school_exams.html',
                           available_exams=available_exams,
                           completed_results=completed_results)

@main_bp.route('/school-exams/<int:exam_id>/start')
@login_required
def start_school_exam(exam_id):
    """Початок іспиту"""
    if current_user.role != 'student':
        flash('Тільки слухачі можуть проходити іспити', 'danger')
        return redirect(url_for('main.dashboard'))

    exam = SchoolExam.query.get_or_404(exam_id)

    # Перевіряємо, чи слухач в групі
    if exam.group not in current_user.student_groups:
        flash('У вас немає доступу до цього іспиту', 'danger')
        return redirect(url_for('main.my_school_exams'))

    # Перевіряємо, чи іспит активний
    if not exam.is_available():
        flash('Цей іспит недоступний', 'danger')
        return redirect(url_for('main.my_school_exams'))

    # Перевіряємо, чи слухач вже проходив цей іспит
    existing_result = SchoolExamResult.query.filter_by(
        exam_id=exam.id,
        user_id=current_user.id
    ).first()

    if existing_result and existing_result.status == 'completed':
        flash('Ви вже проходили цей іспит', 'warning')
        return redirect(url_for('main.school_exam_result', result_id=existing_result.id))

    # Створюємо новий результат або використовуємо існуючий
    if existing_result:
        result = existing_result
    else:
        result = SchoolExamResult(
            exam_id=exam.id,
            user_id=current_user.id,
            total_questions=exam.question_count,
            status='in_progress'
        )
        db.session.add(result)
        db.session.commit()

    # Формуємо список питань
    if exam.question_selection_type == 'manual' and exam.questions:
        questions = [eq.question for eq in sorted(exam.questions, key=lambda x: x.order)]
    else:
        # Випадковий вибір питань з категорії
        # Спочатку отримуємо категорію за її ID
        category = Category.query.get(exam.category_id)
        
        # Перевіряємо чи категорія існує
        if category:
            # Фільтруємо питання, які належать до цієї категорії
            questions = Question.query.filter(
                Question.categories.contains(category),
                Question.bank_id == 1
            ).order_by(func.random()).limit(exam.question_count).all()
        else:
            # Якщо категорії немає — пустий список
            questions = []

    # Зберігаємо питання в сесії
    session['school_exam_id'] = exam.id
    session['school_exam_result_id'] = result.id
    session['school_exam_questions'] = [q.id for q in questions]
    session['school_exam_current'] = 0
    session['school_exam_start_time'] = datetime.utcnow().isoformat()

    return redirect(url_for('main.school_exam_question'))

@main_bp.route('/school-exams/question')
@login_required
def school_exam_question():
    """Сторінка питання іспиту"""
    if current_user.role != 'student':
        return redirect(url_for('main.dashboard'))

    exam_id = session.get('school_exam_id')
    result_id = session.get('school_exam_result_id')

    if not exam_id or not result_id:
        flash('Сесія іспиту закінчилася', 'warning')
        return redirect(url_for('main.my_school_exams'))

    exam = SchoolExam.query.get_or_404(exam_id)
    result = SchoolExamResult.query.get_or_404(result_id)

    # Перевіряємо час
    start_time = datetime.fromisoformat(session['school_exam_start_time'])
    elapsed = (datetime.utcnow() - start_time).total_seconds()
    remaining = exam.time_minutes * 60 - elapsed

    if remaining <= 0:
        # Час вийшов - завершуємо іспит
        return redirect(url_for('main.finish_school_exam'))

    current_idx = session.get('school_exam_current', 0)
    question_ids = session.get('school_exam_questions', [])

    if current_idx >= len(question_ids):
        return redirect(url_for('main.finish_school_exam'))

    question = Question.query.get(question_ids[current_idx])

    # Перевіряємо, чи вже була відповідь
    existing_answer = SchoolExamAnswer.query.filter_by(
        result_id=result.id,
        question_id=question.id
    ).first()

    return render_template('school_exam_question.html',
                           exam=exam,
                           question=question,
                           current_question=current_idx + 1,
                           total_questions=len(question_ids),
                           remaining_seconds=int(remaining),
                           existing_answer=existing_answer)

@main_bp.route('/school-exams/answer', methods=['POST'])
@login_required
def school_exam_answer():
    """Збереження відповіді на питання іспиту"""
    exam_id = session.get('school_exam_id')
    result_id = session.get('school_exam_result_id')

    if not exam_id or not result_id:
        return jsonify({'error': 'Session expired'}), 400

    data = request.get_json()
    question_id = data.get('question_id')
    selected_answer = data.get('selected_answer')

    question = Question.query.get_or_404(question_id)
    result = SchoolExamResult.query.get_or_404(result_id)

    # Перевіряємо, чи відповідь правильна
    is_correct = (selected_answer == question.correct)

    # Зберігаємо або оновлюємо відповідь
    existing_answer = SchoolExamAnswer.query.filter_by(
        result_id=result.id,
        question_id=question.id
    ).first()

    if existing_answer:
        existing_answer.selected_answer = selected_answer
        existing_answer.is_correct = is_correct
    else:
        answer = SchoolExamAnswer(
            result_id=result.id,
            question_id=question.id,
            selected_answer=selected_answer,
            is_correct=is_correct
        )
        db.session.add(answer)

    db.session.commit()

    return jsonify({'success': True})

@main_bp.route('/school-exams/next')
@login_required
def school_exam_next():
    """Наступне питання"""
    current_idx = session.get('school_exam_current', 0)
    question_ids = session.get('school_exam_questions', [])

    session['school_exam_current'] = current_idx + 1

    if current_idx + 1 >= len(question_ids):
        return redirect(url_for('main.finish_school_exam'))

    return redirect(url_for('main.school_exam_question'))

@main_bp.route('/school-exams/finish')
@login_required
def finish_school_exam():
    """Завершення іспиту"""
    exam_id = session.get('school_exam_id')
    result_id = session.get('school_exam_result_id')

    if not exam_id or not result_id:
        flash('Сесія іспиту закінчилася', 'warning')
        return redirect(url_for('main.my_school_exams'))

    exam = SchoolExam.query.get_or_404(exam_id)
    result = SchoolExamResult.query.get_or_404(result_id)

    # Підраховуємо результати
    answers = SchoolExamAnswer.query.filter_by(result_id=result.id).all()
    correct_count = sum(1 for a in answers if a.is_correct)
    error_count = len(answers) - correct_count

    # Час проходження
    start_time = datetime.fromisoformat(session['school_exam_start_time'])
    result.time_spent_seconds = int((datetime.utcnow() - start_time).total_seconds())

    result.correct_answers = correct_count
    result.errors_count = error_count
    result.status = 'completed'
    result.completed_at = datetime.utcnow()
    result.is_passed = error_count <= exam.max_errors

    db.session.commit()

    # Очищаємо сесію
    session.pop('school_exam_id', None)
    session.pop('school_exam_result_id', None)
    session.pop('school_exam_questions', None)
    session.pop('school_exam_current', None)
    session.pop('school_exam_start_time', None)

    return redirect(url_for('main.school_exam_result', result_id=result.id))

@main_bp.route('/school-exams/result/<int:result_id>')
@login_required
def school_exam_result(result_id):
    """Перегляд результату іспиту"""
    result = SchoolExamResult.query.get_or_404(result_id)
    exam = result.exam

    # Перевірка прав доступу
    if current_user.role == 'student' and result.user_id != current_user.id:
        flash('У вас немає прав для перегляду цього результату', 'danger')
        return redirect(url_for('main.my_school_exams'))

    if current_user.role == 'teacher' and exam.group.teacher_id != current_user.id:
        flash('У вас немає прав для перегляду цього результату', 'danger')
        return redirect(url_for('main.groups_list'))

    if current_user.role == 'school_admin' and exam.group.school_id != current_user.school_id:
        flash('У вас немає прав для перегляду цього результату', 'danger')
        return redirect(url_for('main.groups_list'))

    answers = SchoolExamAnswer.query.filter_by(result_id=result.id).all()

    return render_template('school_exam_result.html',
                           result=result,
                           exam=exam,
                           answers=answers)

# ==================== РЕЗУЛЬТАТИ ІСПИТІВ ДЛЯ ВИКЛАДАЧІВ ТА АДМІНІСТРАТОРІВ ====================

@main_bp.route('/school-exams/results')
@login_required
@admin_required
def school_exams_results():
    """Список результатів іспитів"""
    if current_user.role == 'system_admin':
        results = SchoolExamResult.query.order_by(SchoolExamResult.completed_at.desc()).all()
    elif current_user.role == 'school_admin':
        # Отримуємо всі групи школи
        group_ids = [g.id for g in Group.query.filter_by(school_id=current_user.school_id).all()]
        exam_ids = [e.id for e in SchoolExam.query.filter(SchoolExam.group_id.in_(group_ids)).all()]
        results = SchoolExamResult.query.filter(
            SchoolExamResult.exam_id.in_(exam_ids)
        ).order_by(SchoolExamResult.completed_at.desc()).all()
    else:  # teacher
        group_ids = [g.id for g in Group.query.filter_by(teacher_id=current_user.id).all()]
        exam_ids = [e.id for e in SchoolExam.query.filter(SchoolExam.group_id.in_(group_ids)).all()]
        results = SchoolExamResult.query.filter(
            SchoolExamResult.exam_id.in_(exam_ids)
        ).order_by(SchoolExamResult.completed_at.desc()).all()

    return render_template('school_exams_results.html', results=results)

@main_bp.route('/school-exams/result/<int:result_id>/reset', methods=['POST'])
@login_required
@admin_required
def reset_school_exam_result(result_id):
    """Скидання результату іспиту"""
    result = SchoolExamResult.query.get_or_404(result_id)
    exam = result.exam

    # Перевірка прав доступу - тільки адміністратор школи або системний адміністратор
    if current_user.role == 'teacher':
        flash('У вас немає прав для скидання результатів', 'danger')
        return redirect(url_for('main.school_exams_results'))

    if current_user.role == 'school_admin' and exam.group.school_id != current_user.school_id:
        flash('У вас немає прав для скидання цього результату', 'danger')
        return redirect(url_for('main.school_exams_results'))

    # Видаляємо відповіді
    SchoolExamAnswer.query.filter_by(result_id=result.id).delete()

    # Видаляємо результат
    db.session.delete(result)
    db.session.commit()

    flash('Результат іспиту скинуто', 'success')
    return redirect(url_for('main.school_exams_results'))

@main_bp.route('/groups/<int:group_id>/exam-dashboard')
@main_bp.route('/groups/<int:group_id>/exam-dashboard/<int:exam_id>')
@login_required
@admin_required
def exam_dashboard(group_id, exam_id=None):
    """Дашборд статистики іспиту для групи"""
    group = Group.query.get_or_404(group_id)

    # Перевірка прав доступу
    if current_user.role == 'school_admin' and group.school_id != current_user.school_id:
        flash('У вас немає прав для перегляду цієї групи', 'danger')
        return redirect(url_for('main.groups_list'))
    if current_user.role == 'teacher' and group.teacher_id != current_user.id:
        flash('У вас немає прав для перегляду цієї групи', 'danger')
        return redirect(url_for('main.groups_list'))

    # Отримуємо іспит (якщо вказано)
    exam = None
    if exam_id:
        exam = SchoolExam.query.get_or_404(exam_id)
        if exam.group_id != group.id:
            flash('Іспит не належить до цієї групи', 'danger')
            return redirect(url_for('main.exam_dashboard', group_id=group.id))

    # Статистика по групі
    total_students = group.get_students_count()

    # Статистика по іспитах
    exams_stats = []
    for ex in group.exams:
        results = SchoolExamResult.query.filter_by(exam_id=ex.id).all()
        completed_results = [r for r in results if r.status == 'completed']

        passed_count = sum(1 for r in completed_results if r.is_passed)
        failed_count = len(completed_results) - passed_count

        avg_time = 0
        if completed_results:
            avg_time = sum(r.time_spent_seconds or 0 for r in completed_results) / len(completed_results)

        exams_stats.append({
            'exam': ex,
            'total_students': total_students,
            'completed_count': len(completed_results),
            'passed_count': passed_count,
            'failed_count': failed_count,
            'in_progress_count': len([r for r in results if r.status == 'in_progress']),
            'not_started_count': total_students - len(results),
            'avg_time': avg_time,
            'completion_rate': (len(completed_results) / total_students * 100) if total_students > 0 else 0
        })

    # Детальна статистика по конкретному іспиту
    exam_details = None
    if exam:
        results = SchoolExamResult.query.filter_by(exam_id=exam.id).all()
        completed_results = [r for r in results if r.status == 'completed']

        # Статистика по кожному слухачу
        student_results = []
        for student in group.students:
            result = next((r for r in results if r.user_id == student.id), None)
            student_results.append({
                'student': student,
                'result': result
            })

        exam_details = {
            'exam': exam,
            'total_students': total_students,
            'completed_count': len(completed_results),
            'passed_count': sum(1 for r in completed_results if r.is_passed),
            'failed_count': sum(1 for r in completed_results if not r.is_passed),
            'in_progress_count': len([r for r in results if r.status == 'in_progress']),
            'not_started_count': total_students - len(results),
            'student_results': student_results
        }

    return render_template('exam_dashboard.html',
                           group=group,
                           exam=exam,
                           exams_stats=exams_stats,
                           exam_details=exam_details)

# Обробка помилок
@main_bp.app_errorhandler(404)
def not_found_error(error):
    return render_template('base.html', error='Сторінку не знайдено'), 404

@main_bp.app_errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('base.html', error='Внутрішня помилка сервера'), 500