from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
import os


class Command(BaseCommand):
    help = 'Create superuser from environment variables'

    def handle(self, *args, **options):
        User = get_user_model()

        email = os.environ.get('DJANGO_SU_EMAIL', 'admin@example.com')
        password = os.environ.get('DJANGO_SU_PASSWORD')

        if not password:
            self.stdout.write(
                self.style.WARNING('DJANGO_SU_PASSWORD not set. Skipping superuser creation.')
            )
            return

        if User.objects.filter(email=email).exists():
            self.stdout.write(
                self.style.SUCCESS(f'Superuser with email "{email}" already exists.')
            )
            return

        User.objects.create_superuser(
            email=email,
            password=password
        )
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created superuser with email "{email}"')
        )