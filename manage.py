#!/usr/bin/env python
# hna-acadex-backend/manage.py
import os
import sys
from pathlib import Path


def main() -> None:
    # Load .env file if it exists
    env_file = Path(__file__).resolve().parent / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
