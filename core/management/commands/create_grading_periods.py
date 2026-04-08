"""
Django management command to create grading periods for a school year.

Usage:
    python manage.py create_grading_periods 2024-2025
    python manage.py create_grading_periods 2024-2025 --type=quarter
    python manage.py create_grading_periods 2024-2025 --type=semester
    python manage.py create_grading_periods 2024-2025 --start-month=6  # June start

This will create:
- Quarters (Q1-Q4) for Grades 7-10
- Semesters (1st Sem, 2nd Sem) for Grades 11-12
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import GradingPeriod
from datetime import date, timedelta
from calendar import monthrange


class Command(BaseCommand):
    help = 'Create grading periods (Quarters or Semesters) for a school year'

    def add_arguments(self, parser):
        parser.add_argument(
            'school_year',
            type=str,
            help='School year in format YYYY-YYYY (e.g., 2024-2025)',
        )
        parser.add_argument(
            '--type',
            type=str,
            choices=['quarter', 'semester', 'both'],
            default='both',
            help='Type of grading periods to create: quarter, semester, or both (default: both)',
        )
        parser.add_argument(
            '--start-month',
            type=int,
            default=6,
            help='Start month of school year (1-12, default: 6 for June)',
        )
        parser.add_argument(
            '--start-day',
            type=int,
            default=1,
            help='Start day of first period (default: 1)',
        )
        parser.add_argument(
            '--quarter-weeks',
            type=int,
            default=10,
            help='Number of weeks per quarter (default: 10)',
        )
        parser.add_argument(
            '--semester-weeks',
            type=int,
            default=20,
            help='Number of weeks per semester (default: 20)',
        )
        parser.add_argument(
            '--set-current',
            type=int,
            default=1,
            help='Period number to set as current (default: 1)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating',
        )

    def handle(self, *args, **options):
        school_year = options['school_year']
        period_type = options['type']
        start_month = options['start_month']
        start_day = options['start_day']
        quarter_weeks = options['quarter_weeks']
        semester_weeks = options['semester_weeks']
        set_current = options['set_current']
        dry_run = options['dry_run']

        # Validate school year format
        try:
            years = school_year.split('-')
            if len(years) != 2:
                raise ValueError()
            start_year = int(years[0])
            end_year = int(years[1])
            if end_year != start_year + 1:
                raise ValueError()
        except (ValueError, IndexError):
            raise CommandError(
                f"Invalid school year format '{school_year}'. Expected format: YYYY-YYYY (e.g., 2024-2025)"
            )

        # Calculate start date
        try:
            start_date = date(start_year, start_month, start_day)
        except ValueError as e:
            raise CommandError(f"Invalid start date: {e}")

        periods_to_create = []

        # Generate quarter periods
        if period_type in ['quarter', 'both']:
            periods_to_create.extend(
                self._generate_quarters(school_year, start_date, quarter_weeks, set_current)
            )

        # Generate semester periods
        if period_type in ['semester', 'both']:
            periods_to_create.extend(
                self._generate_semesters(school_year, start_date, semester_weeks, set_current)
            )

        # Display what will be created
        self.stdout.write(f"\nGrading Periods for School Year {school_year}:")
        self.stdout.write("=" * 60)

        for period_data in periods_to_create:
            current_str = " [CURRENT]" if period_data['is_current'] else ""
            self.stdout.write(
                f"  {period_data['label']:10} ({period_data['period_type']:8}) "
                f"{period_data['start_date']} - {period_data['end_date']}{current_str}"
            )

        if dry_run:
            self.stdout.write(self.style.WARNING("\n[DRY RUN] No periods created."))
            return

        # Check for existing periods
        existing_count = GradingPeriod.objects.filter(school_year=school_year).count()
        if existing_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\nWarning: {existing_count} grading period(s) already exist for {school_year}."
                )
            )
            response = input("Do you want to continue and create additional periods? (y/N): ")
            if response.lower() != 'y':
                self.stdout.write(self.style.ERROR("Operation cancelled."))
                return

        # Create periods
        created_count = 0
        with transaction.atomic():
            for period_data in periods_to_create:
                _, created = GradingPeriod.objects.get_or_create(
                    school_year=period_data['school_year'],
                    period_type=period_data['period_type'],
                    period_number=period_data['period_number'],
                    defaults={
                        'start_date': period_data['start_date'],
                        'end_date': period_data['end_date'],
                        'is_current': period_data['is_current'],
                    }
                )
                if created:
                    created_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"\nSuccessfully created {created_count} grading period(s).")
        )

    def _generate_quarters(self, school_year, start_date, weeks_per_quarter, set_current):
        """Generate 4 quarter periods."""
        periods = []
        current_date = start_date

        for quarter_num in range(1, 5):
            # Calculate end date (weeks_per_quarter weeks later)
            end_date = current_date + timedelta(weeks=weeks_per_quarter)

            # Adjust end date to be the day before the next quarter starts
            # (to avoid gaps or overlaps)
            if quarter_num < 4:
                end_date = end_date - timedelta(days=1)

            periods.append({
                'school_year': school_year,
                'period_type': 'quarter',
                'period_number': quarter_num,
                'label': f'Q{quarter_num}',
                'start_date': current_date,
                'end_date': end_date,
                'is_current': quarter_num == set_current,
            })

            # Next quarter starts right after this one ends
            if quarter_num < 4:
                current_date = end_date + timedelta(days=1)

        return periods

    def _generate_semesters(self, school_year, start_date, weeks_per_semester, set_current):
        """Generate 2 semester periods."""
        periods = []

        for sem_num in range(1, 3):
            # Calculate start and end dates
            start = start_date + timedelta(weeks=weeks_per_semester * (sem_num - 1))
            end = start + timedelta(weeks=weeks_per_semester) - timedelta(days=1)

            # Label: "1st Sem" or "2nd Sem"
            label = f'{sem_num}st Sem' if sem_num == 1 else f'{sem_num}nd Sem'

            periods.append({
                'school_year': school_year,
                'period_type': 'semester',
                'period_number': sem_num,
                'label': label,
                'start_date': start,
                'end_date': end,
                'is_current': sem_num == set_current,
            })

        return periods