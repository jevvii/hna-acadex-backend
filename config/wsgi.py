import os
from pathlib import Path
from django.core.wsgi import get_wsgi_application

# Load .env file if it exists
env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()