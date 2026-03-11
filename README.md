# HNA Acadex Django Backend

## Setup

```bash
cd hna-acadex-backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

Django admin is available at `http://127.0.0.1:8000/admin/`.

## API Base URL for React Native

- Android emulator: `http://10.0.2.2:8000/api`
- iOS simulator: `http://127.0.0.1:8000/api`
- Physical device: `http://<your-computer-lan-ip>:8000/api`

## Main Endpoints

- `POST /api/auth/login/`
- `GET /api/auth/me/`
- `POST /api/auth/refresh/`
- `GET/POST/PATCH/DELETE /api/profiles/`
- `POST /api/profiles/{id}/toggle_status/`
- `POST /api/profiles/me/avatar/`
- `GET /api/dashboard/stats/`
- `GET/POST/PATCH/DELETE /api/todos/`
- `GET/POST/PATCH/DELETE /api/calendar-events/`
- `GET /api/notifications/`
- `POST /api/notifications/{id}/mark_read/`
- `POST /api/notifications/mark_all_read/`
- `GET /api/courses/student/`
- `GET /api/courses/teacher/`
- `GET /api/course-sections/{id}/content/`
