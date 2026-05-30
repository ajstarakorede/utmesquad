# UTME SQUAD — Secure Educational Platform

A Django + WebSocket platform for UTME candidate management with real-time messaging, group chat, voice messages, and admin dashboard.

---

## 🚀 Quick Start (Development)

```bash
# 1. Extract and enter the project
cd fixed_project

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — set SECRET_KEY, keep DEBUG=True for dev

# 5. Run migrations
python manage.py migrate

# 6. Run dev server
python manage.py runserver
```

Visit **http://127.0.0.1:8000/admin/** and log in with your `DEFAULT_ADMIN_PASSWORD`.

---

## 🌐 Production Deployment

### Step 1 — Server Setup

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y python3-pip python3-venv mysql-server redis-server nginx certbot python3-certbot-nginx
```

### Step 2 — Project Setup

```bash
cd /var/www/
git clone <your-repo> utme_squad   # or upload the zip
cd utme_squad
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 3 — Environment Variables

```bash
cp .env.example .env
nano .env
```

Fill in **every value** — especially:

| Variable | What to set |
|---|---|
| `SECRET_KEY` | Run: `python -c "import secrets; print(secrets.token_hex(50))"` |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | Your domain, e.g. `utmesquad.com,www.utmesquad.com` |
| `DB_ENGINE` | `mysql` |
| `DB_PASSWORD` | Strong MySQL password |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` |
| `CORS_ORIGINS` | `https://yourdomain.com` |
| `DEFAULT_ADMIN_PASSWORD` | Strong password — **change immediately after first login** |

### Step 4 — Database

```sql
-- Run as MySQL root
CREATE DATABASE utme_squad_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'utme_user'@'localhost' IDENTIFIED BY 'your_strong_password';
GRANT ALL PRIVILEGES ON utme_squad_db.* TO 'utme_user'@'localhost';
FLUSH PRIVILEGES;
```

### Step 5 — Deploy

```bash
bash deploy.sh
```

This runs migrations, collects static files, and seeds the admin password.

### Step 6 — Nginx + SSL

```bash
# Copy and edit nginx config
sudo cp nginx.conf.example /etc/nginx/sites-available/utmesquad
sudo nano /etc/nginx/sites-available/utmesquad   # replace yourdomain.com and paths
sudo ln -s /etc/nginx/sites-available/utmesquad /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Get free SSL certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

### Step 7 — Systemd Service

```bash
sudo nano /etc/systemd/system/utmesquad.service
```

```ini
[Unit]
Description=UTME SQUAD Daphne Server
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/utme_squad
EnvironmentFile=/var/www/utme_squad/.env
ExecStart=/var/www/utme_squad/venv/bin/daphne -b 127.0.0.1 -p 8000 utme_squad.asgi:application
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable utmesquad
sudo systemctl start utmesquad
sudo systemctl status utmesquad
```

### Step 8 — After First Login

1. Log into `/admin/` with your `DEFAULT_ADMIN_PASSWORD`
2. Go to **Settings** and change the admin password immediately
3. Change the messaging unlock password from the default

---

## 🔒 Security Summary

| Feature | Status |
|---|---|
| Passwords hashed with PBKDF2-SHA256 | ✅ |
| Timing-safe password comparison | ✅ |
| CSRF protection on all POST endpoints | ✅ |
| Server-side login rate limiting (10 attempts / 5 min) | ✅ |
| Client-side login lockout (5 attempts / 30 sec) | ✅ |
| Session auth on all protected pages | ✅ |
| WebSocket connection auth | ✅ |
| File upload type + size validation | ✅ |
| XSS protection headers | ✅ |
| Clickjacking protection (X-Frame-Options: DENY) | ✅ |
| HSTS (auto-enabled when DEBUG=False) | ✅ |
| HTTPS redirect (auto-enabled when DEBUG=False) | ✅ |
| No default credentials in source code | ✅ |
| No plaintext passwords in database | ✅ |

---

## 📁 Project Structure

```
utme_squad/
├── manage.py
├── requirements.txt
├── .env.example          ← copy to .env and fill in
├── deploy.sh             ← run once on each deployment
├── Procfile              ← for Heroku/Render/Railway
├── nginx.conf.example    ← copy to /etc/nginx/sites-available/
│
├── utme_squad/           ← Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── asgi.py
│
├── api/                  ← main app (views, models, URLs)
├── chat/                 ← WebSocket consumers
├── templates/
│   ├── admin/
│   └── candidate/
├── static/
└── media/                ← uploaded files (back this up!)
```

---

## ⚙️ Tech Stack

- **Backend**: Python 3.8+, Django 4.2, Django REST Framework
- **Real-time**: Django Channels 4 + Daphne + Redis
- **Database**: MySQL (SQLite for dev)
- **Frontend**: HTML5, Tailwind CSS, Vanilla JS
- **PDF**: ReportLab
- **Voice**: Web Audio API + MediaRecorder
- **Static files**: WhiteNoise
- **Reverse proxy**: Nginx + Let's Encrypt (SSL)
