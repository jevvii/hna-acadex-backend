import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

def check_table_schema():
    with connection.cursor() as cursor:
        print("Checking CourseFile table schema...")
        cursor.execute("""
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'core_coursefile'
            AND column_name IN ('file_url', 'preview_file_url');
        """)
        columns = cursor.fetchall()
        for col in columns:
            print(f"Column: {col[0]}, Type: {col[1]}, Max Length: {col[2]}")

def check_migration_status():
    from django.db.migrations.recorder import MigrationRecorder
    print("\nChecking applied migrations for 'core'...")
    applied = MigrationRecorder.Migration.objects.filter(app='core').order_by('-applied')
    for m in applied[:5]:
        print(f"Migration: {m.name}, Applied: {m.applied}")

if __name__ == "__main__":
    try:
        check_table_schema()
        check_migration_status()
    except Exception as e:
        print(f"Error: {e}")
