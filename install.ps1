# ============================================
# АЛЛІН Тренажер - Скрипт встановлення
# Для Windows 11 + Python 3.14.3
# ============================================

param(
    [switch]$Silent,
    [string]$InstallPath = "$env:USERPROFILE\allin_trainer",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

# Кольори для виводу
function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

function Write-Info($message) {
    Write-ColorOutput Cyan "[INFO] $message"
}

function Write-Success($message) {
    Write-ColorOutput Green "[OK] $message"
}

function Write-Warning($message) {
    Write-ColorOutput Yellow "[WARN] $message"
}

function Write-Error($message) {
    Write-ColorOutput Red "[ERROR] $message"
}

function Pause-IfNotSilent {
    if (-not $Silent) {
        Write-Output ""
        Write-Output "Натисніть Enter для продовження..."
        Read-Host
    }
}

# ============================================
# 1. ПЕРЕВІРКА СИСТЕМИ
# ============================================
Clear-Host
Write-Output "========================================"
Write-Output "  АЛЛІН Тренажер - Встановлення"
Write-Output "========================================"
Write-Output ""

Write-Info "Перевірка системних вимог..."

# Перевірка Windows 11
$osInfo = Get-CimInstance Win32_OperatingSystem
$windowsVersion = [System.Environment]::OSVersion.Version

if ($windowsVersion.Major -lt 10 -or ($windowsVersion.Major -eq 10 -and $windowsVersion.Build -lt 22000)) {
    Write-Warning "Рекомендується Windows 11. Поточна версія: $($osInfo.Caption)"
    Pause-IfNotSilent
}

# Перевірка Python
Write-Info "Перевірка Python..."
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
}

if (-not $pythonCmd) {
    Write-Error "Python не знайдено! Будь ласка, встановіть Python 3.14.3"
    Write-Output ""
    Write-Output "Завантажити Python: https://www.python.org/downloads/"
    Write-Output "ВАЖЛИВО: Під час встановлення поставте галочку 'Add Python to PATH'"
    Pause-IfNotSilent
    exit 1
}

$pythonVersion = & $pythonCmd.Source --version 2>&1
Write-Info "Знайдено: $pythonVersion"

# Перевірка версії Python (мінімум 3.10)
$versionMatch = $pythonVersion -match '(\d+)\.(\d+)'
if ($versionMatch) {
    $major = [int]$matches[1]
    $minor = [int]$matches[2]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
        Write-Warning "Рекомендується Python 3.10+. Поточна версія: $major.$minor"
        Pause-IfNotSilent
    }
}

Write-Success "Перевірка системи завершена"
Pause-IfNotSilent

# ============================================
# 2. СТВОРЕННЯ ПАПОК
# ============================================
Clear-Host
Write-Info "Створення структури папок..."

$folders = @(
    $InstallPath,
    "$InstallPath\app",
    "$InstallPath\app\templates",
    "$InstallPath\app\static\css",
    "$InstallPath\app\static\js",
    "$InstallPath\data",
    "$InstallPath\import",
    "$InstallPath\export",
    "$InstallPath\logs"
)

foreach ($folder in $folders) {
    if (-not (Test-Path $folder)) {
        New-Item -ItemType Directory -Path $folder -Force | Out-Null
        Write-Info "Створено: $folder"
    }
}

Write-Success "Папки створені"
Pause-IfNotSilent

# ============================================
# 3. СТВОРЕННЯ VIRTUAL ENVIRONMENT
# ============================================
Clear-Host
Write-Info "Створення віртуального оточення..."

$venvPath = "$InstallPath\venv"

if (Test-Path $venvPath) {
    Write-Warning "Віртуальне оточення вже існує"
} else {
    & $pythonCmd.Source -m venv $venvPath
    Write-Success "Віртуальне оточення створено"
}

# Активація venv
$venvPython = "$venvPath\Scripts\python.exe"
$venvPip = "$venvPath\Scripts\pip.exe"

Write-Success "Віртуальне оточення готове"
Pause-IfNotSilent

# ============================================
# 4. ВСТАНОВЛЕННЯ ЗАЛЕЖНОСТЕЙ
# ============================================
Clear-Host
Write-Info "Встановлення необхідних пакетів..."

# Створюємо requirements.txt
$requirements = @"
Flask==3.0.3
Flask-SQLAlchemy==3.1.1
Flask-Login==0.6.3
Flask-WTF==1.2.1
Werkzeug==3.0.3
PyJWT==2.8.0
bcrypt==4.1.3
python-dotenv==1.0.1
pandas==2.2.2
waitress==3.0.0
"@

$requirementsPath = "$InstallPath\requirements.txt"
$requirements | Out-File -FilePath $requirementsPath -Encoding UTF8

& $venvPip install --upgrade pip
& $venvPip install -r $requirementsPath

Write-Success "Пакети встановлені"
Pause-IfNotSilent

# ============================================
# 5. КОПІЮВАННЯ ФАЙЛІВ ПРОЄКТУ
# ============================================
Clear-Host
Write-Info "Копіювання файлів проєкту..."

# Перевіряємо чи є файли поруч зі скриптом
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourcePath = if (Test-Path "$scriptPath\app") { $scriptPath } else { $PWD.Path }

Write-Info "Джерело: $sourcePath"
Write-Info "Призначення: $InstallPath"

# Копіюємо файли
$filesToCopy = @(
    "run.py",
    "config.py",
    "requirements.txt"
)

foreach ($file in $filesToCopy) {
    $source = "$sourcePath\$file"
    if (Test-Path $source) {
        Copy-Item $source "$InstallPath\$file" -Force
        Write-Info "Скопійовано: $file"
    }
}

# Копіюємо папку app
if (Test-Path "$sourcePath\app") {
    Copy-Item "$sourcePath\app" $InstallPath -Recurse -Force
    Write-Info "Скопійовано: app/"
}

# Копіюємо файли з питаннями якщо є
$questionFiles = @(
    "питання з фото.json",
    "questions 300 питань.csv",
    "questions_photo.json",
    "questions.csv"
)

foreach ($file in $questionFiles) {
    $source = "$sourcePath\$file"
    if (Test-Path $source) {
        Copy-Item $source "$InstallPath\import\$file" -Force
        Write-Info "Скопійовано файл з питаннями: $file"
    }
}

Write-Success "Файли скопійовані"
Pause-IfNotSilent

# ============================================
# 6. СТВОРЕННЯ СКРИПТІВ ЗАПУСКУ
# ============================================
Clear-Host
Write-Info "Створення скриптів запуску..."

# Скрипт для розробки
$devScript = @"
@echo off
cd /d "$InstallPath"
call venv\Scripts\activate.bat
python run.py
pause
"@
$devScript | Out-File -FilePath "$InstallPath\start-dev.bat" -Encoding UTF8

# Скрипт для production (через waitress)
$prodScript = @"
@echo off
cd /d "$InstallPath"
call venv\Scripts\activate.bat
python -c "from waitress import serve; from app import create_app; app = create_app(); serve(app, host='0.0.0.0', port=$Port, threads=8)"
"@
$prodScript | Out-File -FilePath "$InstallPath\start-prod.bat" -Encoding UTF8

# PowerShell скрипт для production
$prodPsScript = @"
`$ErrorActionPreference = "Stop"
Set-Location "$InstallPath"
& ".\venv\Scripts\Activate.ps1"

`$env:FLASK_ENV = "production"

# Запуск через waitress
python -c "from waitress import serve; from app import create_app; app = create_app('production'); serve(app, host='0.0.0.0', port=$Port, threads=8, connection_limit=100, channel_timeout=30)"
"@
$prodPsScript | Out-File -FilePath "$InstallPath\start-server.ps1" -Encoding UTF8

# Скрипт для створення Windows служби
$serviceScript = @"
# Створення Windows служби для АЛЛІН Тренажера
# Потребує прав адміністратора

`$serviceName = "AllinTrainer"
`$displayName = "АЛЛІН Тренажер"
`$description = "Веб-додаток для тестування судноводіїв"
`$pythonPath = "$InstallPath\venv\Scripts\python.exe"
`$scriptPath = "$InstallPath\run_service.py"

# Створюємо скрипт служби
`$serviceScript = @'
import win32serviceutil
import win32service
import win32event
import servicemanager
import subprocess
import os
import sys

class AllinTrainerService(win32serviceutil.ServiceFramework):
    _svc_name_ = "AllinTrainer"
    _svc_display_name_ = "АЛЛІН Тренажер"
    _svc_description_ = "Веб-додаток для тестування судноводіїв"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.process = None
    
    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        if self.process:
            self.process.terminate()
    
    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                            servicemanager.PYS_SERVICE_STARTED,
                            (self._svc_name_, ''))
        os.chdir(r'$InstallPath')
        self.process = subprocess.Popen([
            r'$InstallPath\venv\Scripts\python.exe',
            '-c',
            'from waitress import serve; from app import create_app; app = create_app(\"production\"); serve(app, host=\"0.0.0.0\", port=$Port)'
        ])
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(AllinTrainerService)
'@

`$serviceScript | Out-File -FilePath `$scriptPath -Encoding UTF8

Write-Output "Для встановлення служби виконайте:"
Write-Output "  python ```$scriptPath install"
Write-Output ""
Write-Output "Для запуску:"
Write-Output "  python ```$scriptPath start"
"@
$serviceScript | Out-File -FilePath "$InstallPath\install-service.ps1" -Encoding UTF8

Write-Success "Скрипти запуску створені"
Pause-IfNotSilent

# ============================================
# 7. ІНІЦІАЛІЗАЦІЯ БАЗИ ДАНИХ
# ============================================
Clear-Host
Write-Info "Ініціалізація бази даних..."

Set-Location $InstallPath
& $venvPython -c "
import sys
sys.path.insert(0, '$InstallPath')
from app import create_app
from app.models import db
app = create_app()
with app.app_context():
    db.create_all()
    print('База даних створена')
"

Write-Success "База даних ініціалізована"
Pause-IfNotSilent

# ============================================
# 8. СТВОРЕННЯ ЯРЛИКІВ
# ============================================
Clear-Host
Write-Info "Створення ярликів..."

$WshShell = New-Object -ComObject WScript.Shell

# Ярлик для запуску
$shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\АЛЛІН Тренажер.lnk")
$shortcut.TargetPath = "$InstallPath\start-dev.bat"
$shortcut.WorkingDirectory = $InstallPath
$shortcut.IconLocation = "%SystemRoot%\System32\shell32.dll,14"
$shortcut.Description = "АЛЛІН Тренажер - Веб-додаток для тестування"
$shortcut.Save()

# Ярлик в меню Пуск
$startMenuPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\АЛЛІН Тренажер"
if (-not (Test-Path $startMenuPath)) {
    New-Item -ItemType Directory -Path $startMenuPath -Force | Out-Null
}

$shortcut2 = $WshShell.CreateShortcut("$startMenuPath\АЛЛІН Тренажер.lnk")
$shortcut2.TargetPath = "$InstallPath\start-dev.bat"
$shortcut2.WorkingDirectory = $InstallPath
$shortcut2.IconLocation = "%SystemRoot%\System32\shell32.dll,14"
$shortcut2.Save()

Write-Success "Ярлики створені"
Pause-IfNotSilent

# ============================================
# 9. НАЛАШТУВАННЯ ФАЄРВОЛА
# ============================================
Clear-Host
Write-Info "Налаштування брандмауера Windows..."

# Додаємо правило для входящих з'єднань
$ruleName = "АЛЛІН Тренажер - Port $Port"
$existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue

if (-not $existingRule) {
    try {
        New-NetFirewallRule -DisplayName $ruleName `
                           -Direction Inbound `
                           -Protocol TCP `
                           -LocalPort $Port `
                           -Action Allow `
                           -Profile Any `
                           -Description "Дозволяє вхідні з'єднання до АЛЛІН Тренажера" | Out-Null
        Write-Success "Правило брандмауера створено"
    } catch {
        Write-Warning "Не вдалося створити правило брандмауера. Запустіть скрипт від імені адміністратора."
    }
} else {
    Write-Info "Правило брандмауера вже існує"
}

Pause-IfNotSilent

# ============================================
# 10. ФІНАЛЬНА ІНФОРМАЦІЯ
# ============================================
Clear-Host
Write-Output "========================================"
Write-Output "  ✅ ВСТАНОВЛЕННЯ ЗАВЕРШЕНО!"
Write-Output "========================================"
Write-Output ""
Write-Success "АЛЛІН Тренажер успішно встановлено!"
Write-Output ""
Write-Output "📁 Шлях встановлення: $InstallPath"
Write-Output "🌐 Адреса доступу: http://localhost:$Port"
Write-Output "🌐 Адреса в мережі: http://$(hostname):$Port"
Write-Output ""
Write-Output "🔑 Тестові облікові записи:"
Write-Output "   admin / admin123       (Адміністратор)"
Write-Output "   teacher / teacher123   (Вчитель)"
Write-Output "   student / student123   (Учень)"
Write-Output ""
Write-Output "🚀 Запуск:"
Write-Output "   - Подвійний клік на ярлик 'АЛЛІН Тренажер' на робочому столі"
Write-Output "   - Або виконайте: $InstallPath\start-dev.bat"
Write-Output ""
Write-Output "📋 Додаткові скрипти:"
Write-Output "   - start-prod.bat       - Production режим"
Write-Output "   - start-server.ps1     - PowerShell сервер"
Write-Output "   - install-service.ps1  - Встановлення як служба Windows"
Write-Output ""
Write-Output "⚠️  Для доступу з інтернету:"
Write-Output "   1. Налаштуйте DDNS (наприклад, No-IP)"
Write-Output "   2. Налаштуйте Port Forwarding на роутері"
Write-Output "   3. Відкрийте порт $Port в брандмауері"
Write-Output ""
Write-Output "📖 Документація: README.md"
Write-Output ""

if (-not $Silent) {
    Write-Output "Натисніть Enter для виходу..."
    Read-Host
}
