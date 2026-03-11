# 🌐 Налаштування DDNS для доступу з інтернету

Цей документ описує налаштування доступу до АЛЛІН Тренажера з інтернету через Dynamic DNS (DDNS).

## 📋 Зміст

1. [Що таке DDNS?](#що-таке-ddns)
2. [Варіант 1: No-IP (безкоштовно)](#варіант-1-no-ip-безкоштовно)
3. [Варіант 2: DuckDNS (безкоштовно)](#варіант-2-duckdns-безкоштовно)
4. [Налаштування роутера](#налаштування-роутера)
5. [Налаштування брандмауера](#налаштування-брандмауера)
6. [Перевірка доступу](#перевірка-доступу)
7. [Вирішення проблем](#вирішення-проблем)

---

## Що таке DDNS?

**Dynamic DNS (DDNS)** — це сервіс, який автоматично оновлює DNS-записи при зміні IP-адреси вашого інтернет-з'єднання. Це дозволяє отримати постійну адресу для доступу до сервера навіть при динамічному IP.

---

## Варіант 1: No-IP (безкоштовно)

### Крок 1: Реєстрація

1. Перейдіть на [noip.com](https://www.noip.com/)
2. Натисніть **Sign Up** та створіть обліковий запис
3. Підтвердіть email

### Крок 2: Створення хосту

1. Увійдіть в панель керування
2. Натисніть **Create Hostname**
3. Введіть бажане ім'я (наприклад: `allin-trainer`)
4. Виберіть домен (наприклад: `ddns.net`)
5. Натисніть **Create Hostname**

Ваша адреса буде: `allin-trainer.ddns.net`

### Крок 3: Встановлення DUC клієнта

#### Windows:

1. Завантажте DUC з [noip.com/download](https://www.noip.com/download?page=win
2. Встановіть та запустіть
3. Увійдіть з вашими обліковими даними No-IP
4. Виберіть створений хост
5. Натисніть **Refresh Now** для тестування

#### Альтернатива — PowerShell скрипт:

```powershell
# Створіть файл noip-updater.ps1
$hostname = "your-hostname.ddns.net"
$username = "your-noip-email@example.com"
$password = "your-noip-password"

$auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$username`:$password"))
$headers = @{ Authorization = "Basic $auth" }

$response = Invoke-RestMethod -Uri "https://dynupdate.no-ip.com/nic/update?hostname=$hostname" -Headers $headers
Write-Output "No-IP Update: $response"
```

Додайте в Планувальник завдань для запуску кожні 5 хвилин.

---

## Варіант 2: DuckDNS (безкоштовно)

### Крок 1: Реєстрація

1. Перейдіть на [duckdns.org](https://www.duckdns.org/)
2. Увійдіть через Google, GitHub, Twitter або Reddit
3. Введіть бажаний піддомен (наприклад: `allin-trainer`)
4. Натисніть **add domain**

Ваша адреса буде: `allin-trainer.duckdns.org`

### Крок 2: Отримання токена

1. На головній сторінці знайдіть **token**
2. Скопіюйте його (виглядає як: `a1b2c3d4-e5f6-7890-abcd-ef1234567890`)

### Крок 3: Встановлення клієнта

#### Windows PowerShell:

```powershell
# Створіть файл duckdns-updater.ps1
$domain = "allin-trainer"
$token = "your-token-here"

Invoke-RestMethod -Uri "https://www.duckdns.org/update?domains=$domain&token=$token&ip="
```

Додайте в Планувальник завдань:

```powershell
# Створення завдання
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-File C:\allin_trainer\duckdns-updater.ps1"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName "DuckDNS Updater" -Description "Оновлення DuckDNS IP"
```

---

## Налаштування роутера

### Загальні кроки (для більшості роутерів):

1. **Відкрийте налаштування роутера**:
   - Введіть в браузері: `192.168.1.1` або `192.168.0.1`
   - Увійдіть з логіном/паролем (зазвичай admin/admin або написано на роутері)

2. **Знайдіть IP вашого комп'ютера**:
   - Windows: `ipconfig` → IPv4 Address
   - Зазвичай щось на кшталт `192.168.1.100`

3. **Налаштуйте Port Forwarding**:
   - Знайдіть розділ **Port Forwarding**, **Virtual Servers** або **NAT**
   - Додайте нове правило:
     - **Service Name**: AllinTrainer
     - **External Port**: 5000
     - **Internal Port**: 5000
     - **Internal IP**: IP вашого комп'ютера
     - **Protocol**: TCP

4. **Збережіть налаштування**

### Приклади для популярних роутерів:

#### TP-Link:
```
Forwarding → Virtual Servers → Add New
  - Service Port: 5000
  - IP Address: 192.168.1.100 (ваш IP)
  - Protocol: TCP
  - Status: Enabled
```

#### ASUS:
```
WAN → Virtual Server / Port Forwarding
  - Enable Port Forwarding: Yes
  - Service Name: AllinTrainer
  - Port Range: 5000
  - Local IP: 192.168.1.100
  - Local Port: 5000
  - Protocol: TCP
```

#### Xiaomi:
```
Advanced Settings → Port Forwarding
  - Name: AllinTrainer
  - Protocol: TCP
  - External Port: 5000
  - Internal Port: 5000
  - IP Address: 192.168.31.100
```

---

## Налаштування брандмауера

### Windows Defender Firewall:

```powershell
# Запустіть PowerShell від імені адміністратора

# Додати правило для входящих
New-NetFirewallRule `
  -DisplayName "АЛЛІН Тренажер" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 5000 `
  -Action Allow `
  -Profile Any `
  -Description "Дозволяє вхідні з'єднання до АЛЛІН Тренажера"

# Перевірити правило
Get-NetFirewallRule -DisplayName "АЛЛІН Тренажер"
```

### Графічний інтерфейс:

1. **Панель керування** → **Брандмауер Windows**
2. **Додаткові параметри**
3. **Правила для вхідних підключень** → **Створити правило**
4. **Для порту** → **TCP** → **Певні локальні порти: 5000**
5. **Дозволити підключення**
6. **Для всіх профілів**
7. **Ім'я**: АЛЛІН Тренажер

---

## Перевірка доступу

### 1. Локальний доступ

```
http://localhost:5000
```

### 2. Доступ з локальної мережі

```
http://[IP-вашого-комп'ютера]:5000
# Наприклад: http://192.168.1.100:5000
```

### 3. Доступ з інтернету

```
http://[ваш-ddns-домен]:5000
# Наприклад: http://allin-trainer.duckdns.org:5000
```

### Інструменти для перевірки:

- [canyouseeme.org](https://canyouseeme.org/) — перевірка відкритості порту
- [ping.eu](https://ping.eu/port-chk/) — перевірка порту ззовні

---

## Вирішення проблем

### Проблема: "Порт закритий"

**Причини та рішення:**

1. **Сервер не запущений**
   ```powershell
   # Перевірте чи працює процес
   Get-Process -Name python
   ```

2. **Брандмауер блокує**
   - Перевірте правила брандмауера
   - Тимчасово вимкніть брандмауер для тестування

3. **Роутер не налаштований**
   - Перевірте правильність IP адреси в налаштуваннях роутера
   - Переконайтесь що порт 5000 відкритий

4. **Провайдер блокує порт**
   - Спробуйте інший порт (наприклад, 8080, 8000, 3000)
   - Змініть порт в `run.py` та роутері

### Проблема: "DDNS не оновлюється"

**Рішення:**

1. Перевірте токен/пароль
2. Перевірте правильність доменного імені
3. Переконайтесь що клієнт DDNS запущений
4. Перевірте логи оновлення

### Проблема: "Повільна робота через інтернет"

**Рішення:**

1. Перевірте швидкість інтернету
2. Використовуйте production режим:
   ```powershell
   .\start-prod.bat
   ```
3. Обмежте кількість одночасних користувачів

---

## Безпека

### Рекомендації:

1. **Змініть стандартні паролі**
2. **Використовуйте HTTPS** (через зворотний проксі)
3. **Обмежте доступ за IP** якщо можливо
4. **Регулярно оновлюйте** додаток
5. **Ведіть логи** доступу

### HTTPS через Nginx (додатково):

```nginx
server {
    listen 443 ssl;
    server_name allin-trainer.duckdns.org;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Додаткові ресурси

- [No-IP Documentation](https://www.noip.com/support/)
- [DuckDNS FAQ](https://www.duckdns.org/faqs.jsp)
- [Port Forwarding Guide](https://portforward.com/)

---

## Підтримка

При виникненні проблем з DDNS:
1. Перевірте логи DUC клієнта
2. Перевірте налаштування роутера
3. Зверніться до служби підтримки DDNS провайдера
