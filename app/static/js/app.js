/**
 * АЛЛІН Тренажер - JavaScript функціонал
 */

// ==================== ТАЙМЕР ====================

class TestTimer {
    constructor(mode, duration = null) {
        this.mode = mode; // 'unlimited' або 'limited'
        this.duration = duration; // в секундах для limited режиму
        this.elapsed = 0;
        this.element = document.getElementById('timer');
        this.interval = null;
    }
    
    start() {
        if (this.mode === 'unlimited') {
            this.startCountUp();
        } else {
            this.startCountDown();
        }
    }
    
    startCountUp() {
        this.interval = setInterval(() => {
            this.elapsed++;
            this.updateDisplay(this.elapsed);
        }, 1000);
    }
    
    startCountDown() {
        this.remaining = this.duration;
        this.updateDisplay(this.remaining);
        
        this.interval = setInterval(() => {
            this.remaining--;
            this.elapsed++;
            this.updateDisplay(this.remaining);
            
            // Попередження
            if (this.remaining <= 60) {
                this.element.classList.add('danger');
            } else if (this.remaining <= 180) {
                this.element.classList.add('warning');
            }
            
            // Час вичерпано
            if (this.remaining <= 0) {
                this.stop();
                this.onTimeUp();
            }
        }, 1000);
    }
    
    updateDisplay(seconds) {
        const mins = Math.floor(Math.abs(seconds) / 60);
        const secs = Math.abs(seconds) % 60;
        const sign = seconds < 0 ? '-' : '';
        this.element.textContent = `${sign}${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    
    stop() {
        if (this.interval) {
            clearInterval(this.interval);
            this.interval = null;
        }
    }
    
    onTimeUp() {
        // Перевизначається ззовні
        alert('Час вичерпано! Тест буде завершено.');
        document.getElementById('finish-test-form').submit();
    }
    
    getElapsedTime() {
        return this.elapsed;
    }
}

// ==================== ТЕСТУВАННЯ ====================

class TestManager {
    constructor() {
        this.currentQuestion = 0;
        this.totalQuestions = parseInt(document.getElementById('total-questions')?.value || 0);
        this.answers = {};
        this.showFeedback = document.getElementById('show-feedback')?.value === 'instant';
        this.mode = document.getElementById('test-mode')?.value || 'random';
        this.timer = null;
        
        this.init();
    }
    
    init() {
        // Ініціалізація таймера
        const timerMode = document.getElementById('timer-mode')?.value || 'unlimited';
        const timerDuration = timerMode === 'limited' ? this.totalQuestions * 60 : null;
        this.timer = new TestTimer(timerMode, timerDuration);
        this.timer.start();
        
        // Обробники подій
        this.bindEvents();
        
        // Оновлення карти питань
        this.updateQuestionMap();
    }
    
    bindEvents() {
        // Вибір варіанту відповіді
        document.querySelectorAll('.option-item').forEach(option => {
            option.addEventListener('click', (e) => this.selectOption(e));
        });
        
        // Навігація
        document.getElementById('btn-prev')?.addEventListener('click', () => this.prevQuestion());
        document.getElementById('btn-next')?.addEventListener('click', () => this.nextQuestion());
        document.getElementById('btn-finish')?.addEventListener('click', () => this.finishTest());
        
        // Карта питань
        document.querySelectorAll('.question-map-item').forEach(item => {
            item.addEventListener('click', (e) => this.goToQuestion(e));
        });
    }
    
    selectOption(e) {
        const option = e.currentTarget;
        const questionId = option.dataset.questionId || option.getAttribute('data-question-id');
        const optionIndex = option.dataset.originalIndex || option.getAttribute('data-original-index');
        
        // Знімаємо вибір з інших
        document.querySelectorAll('.option-item').forEach(opt => {
            opt.classList.remove('selected');
        });
        
        // Вибираємо поточний
        option.classList.add('selected');
        
        // Зберігаємо відповідь
        this.answers[questionId] = parseInt(optionIndex);
        
        // Відправляємо на сервер
        this.submitAnswer(questionId, parseInt(optionIndex));
        
        // Оновлюємо карту
        this.updateQuestionMap();
        
        // Показуємо зворотній зв'язок якщо потрібно
        if (this.showFeedback) {
            this.showFeedbackForOption(option, questionId);
        }
    }
    
    async submitAnswer(questionId, selectedOption) {
        // Конвертуємо індекс в ключ (0->A, 1->B, 2->C)
        const keyMap = ['A', 'B', 'C'];
        const selectedKey = keyMap[selectedOption];
        
        try {
            const response = await fetch('/test/answer', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    question_id: parseInt(questionId),
                    selected_key: selectedKey,
                    selected_index: selectedOption
                })
            });
            
            const data = await response.json();
            
            if (this.showFeedback && data.correct_answer !== undefined) {
                this.highlightCorrectAnswer(data.correct_answer);
            }
            
        } catch (error) {
            console.error('Помилка відправки відповіді:', error);
        }
    }
    
    showFeedbackForOption(option, questionId) {
        // Блокуємо подальший вибір
        document.querySelectorAll('.option-item').forEach(opt => {
            opt.style.pointerEvents = 'none';
        });
        
        // Автоматичний перехід через 2 секунди
        setTimeout(() => {
            this.nextQuestion();
        }, 2000);
    }
    
    highlightCorrectAnswer(correctIndex) {
        document.querySelectorAll('.option-item').forEach((opt, index) => {
            if (index === correctIndex) {
                opt.classList.add('correct');
            } else if (opt.classList.contains('selected')) {
                opt.classList.add('wrong');
            }
        });
    }
    
    prevQuestion() {
        window.location.href = '/test/prev';
    }
    
    nextQuestion() {
        window.location.href = '/test/next';
    }
    
    goToQuestion(e) {
        const index = e.currentTarget.dataset.index;
        // TODO: реалізувати прямий перехід до питання
    }
    
    updateQuestionMap() {
        document.querySelectorAll('.question-map-item').forEach(item => {
            const questionId = item.dataset.questionId;
            if (this.answers[questionId] !== undefined) {
                item.classList.add('answered');
            }
        });
    }
    
    finishTest() {
        // Перевіряємо чи всі питання відповіді
        const answered = Object.keys(this.answers).length;
        
        if (answered < this.totalQuestions) {
            const confirmed = confirm(
                `Ви відповіли на ${answered} з ${this.totalQuestions} питань. ` +
                'Бажаєте завершити тест?'
            );
            if (!confirmed) return;
        }
        
        this.timer.stop();
        document.getElementById('finish-test-form').submit();
    }
}

// ==================== МОДАЛЬНІ ВІКНА ====================

function openModal(modalId) {
    document.getElementById(modalId).classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
    document.body.style.overflow = '';
}

// Закриття по кліку поза модальним вікном
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.classList.remove('active');
        document.body.style.overflow = '';
    }
});

// Закриття по Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay.active').forEach(modal => {
            modal.classList.remove('active');
        });
        document.body.style.overflow = '';
    }
});

// ==================== ПІДТВЕРДЖЕННЯ ДІЙ ====================

function confirmDelete(message = 'Ви впевнені, що хочете видалити?') {
    return confirm(message);
}

// ==================== ФІЛЬТРИ ТА ПОШУК ====================

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// ==================== ПОПЕРЕДНІЙ ПЕРЕГЛЯД ЗОБРАЖЕННЯ ====================

function previewImage(input, previewId) {
    const preview = document.getElementById(previewId);
    const file = input.files[0];
    
    if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            preview.src = e.target.result;
            preview.style.display = 'block';
        };
        reader.readAsDataURL(file);
    } else {
        preview.style.display = 'none';
    }
}

// ==================== ЕКСПОРТ ДАНИХ ====================

function exportData(format) {
    window.location.href = `/export/${format}`;
}

// ==================== СТАТИСТИКА ====================

async function loadUserStats() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();
        
        // Оновлення відображення статистики
        document.getElementById('stat-total-tests').textContent = data.total_tests;
        document.getElementById('stat-avg-score').textContent = data.average_score + '%';
        document.getElementById('stat-mistakes').textContent = data.mistakes_count;
        
    } catch (error) {
        console.error('Помилка завантаження статистики:', error);
    }
}

// ==================== ІНІЦІАЛІЗАЦІЯ ====================

document.addEventListener('DOMContentLoaded', () => {
    // Ініціалізація тестування - ВИМКНЕНО (використовується inline JavaScript в test.html)
    // if (document.getElementById('test-container')) {
    //     window.testManager = new TestManager();
    // }
    
    // Автоматичне приховування повідомлень
    document.querySelectorAll('.alert').forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });
    
    // Завантаження статистики
    if (document.getElementById('stat-total-tests')) {
        loadUserStats();
    }
    
    // Обробка форм з підтвердженням
    document.querySelectorAll('form[data-confirm]').forEach(form => {
        form.addEventListener('submit', (e) => {
            const message = form.dataset.confirm;
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });
});

// ==================== СКОРОЧЕННЯ ТЕКСТУ ====================

function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

// ==================== ФОРМАТУВАННЯ ЧАСУ ====================

function formatDuration(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('uk-UA', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// ==================== ДРУК ====================

function printResults() {
    window.print();
}

// ==================== ПОВНОЕКРАННИЙ РЕЖИМ ====================

function toggleFullscreen() {
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen();
    } else {
        document.exitFullscreen();
    }
}

// ==================== ДОСТУПНІСТЬ ====================

// Навігація клавіатурою для варіантів відповідей
document.addEventListener('keydown', (e) => {
    if (e.key >= '1' && e.key <= '3') {
        const options = document.querySelectorAll('.option-item');
        const index = parseInt(e.key) - 1;
        if (options[index]) {
            options[index].click();
        }
    }
    
    if (e.key === 'ArrowLeft') {
        document.getElementById('btn-prev')?.click();
    }
    
    if (e.key === 'ArrowRight') {
        document.getElementById('btn-next')?.click();
    }
});

// ==================== СПІВАКТИВНІСТЬ ====================

let inactivityTimer;
const INACTIVITY_TIMEOUT = 30 * 60 * 1000; // 30 хвилин

function resetInactivityTimer() {
    clearTimeout(inactivityTimer);
    inactivityTimer = setTimeout(() => {
        // Попередження про неактивність
        if (confirm('Ви довго неактивні. Бажаєте продовжити сесію?')) {
            resetInactivityTimer();
        } else {
            window.location.href = '/logout';
        }
    }, INACTIVITY_TIMEOUT);
}

// Скидання таймера при активності
document.addEventListener('mousemove', resetInactivityTimer);
document.addEventListener('keypress', resetInactivityTimer);
document.addEventListener('click', resetInactivityTimer);

// Запуск таймера
resetInactivityTimer();
