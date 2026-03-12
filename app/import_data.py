"""Імпорт питань з CSV та JSON файлів"""
import json
import csv
from pathlib import Path
from .models import db, Question, Category, QuestionBank


def import_from_json(filepath, created_by=None, bank_id=None):
    """Імпортує питання з JSON файлу"""
    imported = 0
    skipped = 0
    
    # Якщо bank_id не вказано, використовуємо системну базу
    if bank_id is None:
        system_bank = QuestionBank.query.filter_by(level='system', is_default=True).first()
        bank_id = system_bank.id if system_bank else None
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            return 0, 0, "Помилка: JSON файл повинен містити масив об'єктів"
        
        for item in data:
            try:
                if not all(k in item for k in ['section', 'text', 'options', 'correct']):
                    skipped += 1
                    continue
                
                # Перевіряємо чи питання вже існує в цій базі
                existing = Question.query.filter_by(
                    bank_id=bank_id,
                    section=str(item['section']),
                    text=item['text']
                ).first()
                
                if existing:
                    skipped += 1
                    continue
                
                # Створюємо питання
                question = Question(
                    bank_id=bank_id,
                    section=str(item['section']),
                    text=item['text'],
                    option1=item['options'][0] if len(item['options']) > 0 else '',
                    option2=item['options'][1] if len(item['options']) > 1 else '',
                    option3=item['options'][2] if len(item['options']) > 2 else '',
                    correct=int(item['correct']),
                    correct_key='A',  # За замовчуванням
                    image_base64=item.get('image'),
                    created_by=created_by
                )
                
                # Додаємо категорії якщо вказані
                if 'categories' in item and item['categories']:
                    for cat_code in item['categories']:
                        cat = Category.query.filter_by(code=cat_code).first()
                        if cat:
                            question.categories.append(cat)
                
                db.session.add(question)
                imported += 1
                
            except Exception as e:
                skipped += 1
        
        db.session.commit()
        
        return imported, skipped, f"Імпортовано: {imported}, Пропущено: {skipped}"
        
    except Exception as e:
        return 0, 0, f"Помилка: {str(e)}"


def import_from_csv(filepath, created_by=None, delimiter=';', bank_id=None):
    """Імпортує питання з CSV файлу"""
    imported = 0
    skipped = 0
    
    # Якщо bank_id не вказано, використовуємо системну базу
    if bank_id is None:
        system_bank = QuestionBank.query.filter_by(level='system', is_default=True).first()
        bank_id = system_bank.id if system_bank else None
    
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f, delimiter=delimiter)
            header = next(reader, None)
            
            if not header:
                return 0, 0, "CSV файл порожній"
            
            # Знаходимо індекси колонок
            col_map = {}
            for i, col in enumerate(header):
                col_lower = col.lower().strip()
                if col_lower in ['section', 'розділ']:
                    col_map['section'] = i
                elif col_lower in ['question', 'питання', 'text']:
                    col_map['text'] = i
                elif col_lower in ['option1', 'варіант1', 'відповідь1']:
                    col_map['option1'] = i
                elif col_lower in ['option2', 'варіант2', 'відповідь2']:
                    col_map['option2'] = i
                elif col_lower in ['option3', 'варіант3', 'відповідь3']:
                    col_map['option3'] = i
                elif col_lower in ['correct', 'правильна', 'правильний']:
                    col_map['correct'] = i
                elif col_lower in ['categories', 'категорії']:
                    col_map['categories'] = i
            
            for row in reader:
                try:
                    if len(row) < max(col_map.values()) + 1:
                        skipped += 1
                        continue
                    
                    section = str(row[col_map.get('section', 0)])
                    text = row[col_map.get('text', 1)]
                    
                    # Перевіряємо чи питання вже існує в цій базі
                    existing = Question.query.filter_by(
                        bank_id=bank_id,
                        section=section,
                        text=text
                    ).first()
                    
                    if existing:
                        skipped += 1
                        continue
                    
                    correct = int(row[col_map.get('correct', 5)])
                    
                    question = Question(
                        bank_id=bank_id,
                        section=section,
                        text=text,
                        option1=row[col_map.get('option1', 2)],
                        option2=row[col_map.get('option2', 3)],
                        option3=row[col_map.get('option3', 4)],
                        correct=correct,
                        correct_key=['A', 'B', 'C'][correct],
                        created_by=created_by
                    )
                    
                    # Додаємо категорії якщо вказані
                    if 'categories' in col_map:
                        cat_codes = row[col_map['categories']].split(',')
                        for cat_code in cat_codes:
                            cat_code = cat_code.strip().upper()
                            if cat_code:
                                cat = Category.query.filter_by(code=cat_code).first()
                                if cat:
                                    question.categories.append(cat)
                    
                    db.session.add(question)
                    imported += 1
                    
                except Exception as e:
                    skipped += 1
        
        db.session.commit()
        
        return imported, skipped, f"Імпортовано: {imported}, Пропущено: {skipped}"
        
    except Exception as e:
        return 0, 0, f"Помилка: {str(e)}"


def get_statistics():
    """Отримує статистику бази питань"""
    total = Question.query.count()
    sections = db.session.query(Question.section).distinct().count()
    with_images = Question.query.filter(Question.image_base64.isnot(None)).count()
    
    # Статистика по розділах
    section_stats = db.session.query(
        Question.section,
        db.func.count(Question.id).label('count')
    ).group_by(Question.section).all()
    
    # Статистика по категоріях
    category_stats = {}
    categories = Category.query.all()
    for cat in categories:
        category_stats[cat.code] = len(cat.questions)
    
    return {
        'total': total,
        'sections': sections,
        'with_images': with_images,
        'section_breakdown': {s.section: s.count for s in section_stats},
        'category_stats': category_stats
    }


def export_to_json(filepath, questions=None):
    """Експортує питання в JSON файл"""
    if questions is None:
        questions = Question.query.all()
    
    data = []
    for q in questions:
        data.append({
            'section': q.section,
            'text': q.text,
            'options': q.get_options(),
            'correct': q.correct,
            'correct_key': q.correct_key,
            'image': q.image_base64,
            'categories': [c.code for c in q.categories]
        })
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    return len(data)


def export_to_csv(filepath, questions=None, delimiter=';'):
    """Експортує питання в CSV файл"""
    if questions is None:
        questions = Question.query.all()
    
    with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=delimiter)
        writer.writerow(['section', 'question', 'option1', 'option2', 'option3', 'correct', 'categories'])
        
        for q in questions:
            categories = ','.join([c.code for c in q.categories])
            writer.writerow([q.section, q.text, q.option1, q.option2, q.option3, q.correct, categories])
    
    return len(questions)


def export_users_to_json(filepath):
    """Експортує профілі користувачів в JSON"""
    from .models import User
    users = User.query.all()
    
    data = []
    for u in users:
        data.append(u.to_dict())
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    return len(data)


def import_users_from_json(filepath):
    """Імпортує профілі користувачів з JSON"""
    from .models import User
    imported = 0
    skipped = 0
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    for item in data:
        try:
            existing = User.query.filter_by(username=item['username']).first()
            if existing:
                skipped += 1
                continue
            
            user = User(
                username=item['username'],
                last_name=item.get('last_name'),
                first_name=item.get('first_name'),
                middle_name=item.get('middle_name'),
                phone=item.get('phone'),
                email=item.get('email'),
                role=item.get('role', 'student'),
                school_id=item.get('school_id'),
                is_active=item.get('is_active', True),
                data_processing_consent=item.get('data_processing_consent', False)
            )
            
            # Встановлюємо пароль за замовчуванням
            from flask import current_app
            user.set_password(current_app.config['DEFAULT_PASSWORD'])
            user.must_change_password = True
            
            db.session.add(user)
            imported += 1
            
        except Exception as e:
            skipped += 1
    
    db.session.commit()
    return imported, skipped, f"Імпортовано: {imported}, Пропущено: {skipped}"
