@echo off
chcp 65001 >nul
echo ==========================================
echo    Тренажер для судноводіїв
echo ==========================================
echo.

REM Перевірка наявності Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ПОМИЛКА] Python не знайдено!
    echo Будь ласка, встановіть Python 3.8 або новіше з https://python.org
    echo.
    pause
    exit /b 1
)

echo [OK] Python знайдено
echo.

REM Перевірка віртуального середовища
if not exist venv\Scripts\activate.bat (
    echo [INFO] Створення віртуального середовища...
    python -m venv venv
    if errorlevel 1 (
        echo [ПОМИЛКА] Не вдалося створити віртуальне середовище
        pause
        exit /b 1
    )
)

REM Активація віртуального середовища
call venv\Scripts\activate.bat

REM Встановлення залежностей
if not exist venv\Lib\site-packages\flask (
    echo [INFO] Встановлення залежностей...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ПОМИЛКА] Не вдалося встановити залежності
        pause
        exit /b 1
    )
)

echo.
echo ==========================================
echo    Запуск сервера...
echo ==========================================
echo.
echo Відкрийте браузер та перейдіть за адресою:
echo http://localhost:5000
echo.
echo Для зупинки натисніть Ctrl+C
echo.

python run.py

echo.
echo Сервер зупинено.
pause
