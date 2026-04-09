"""
Django management command to create grading periods for a school year.

Usage:
    python manage.py create_grading_periods 2024-2025
    python manage.py create_grading_periods 2024-2025 --for-grade-level=7-10  # Q1-Q4 (no semester grouping)
    python manage.py create_grading_periods 2024-2025 --for-grade-level=11-12 # Q1-Q4 grouped into semesters
    python manage.py create_grading_periods 2024-2025 --start-month=6  # June start

This will create:
- For Grades 7-10: Q1, Q2, Q3, Q4 (semester_group is null)
- For Grades 11-12: Q1, Q2 (semester_group=1), Q3, Q4 (semester_group=2)
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import GradingPeriod
from datetime import date, timedelta


class Command(BaseCommand):
    help = 'Create grading periods (Quarters) for a school year'

    def add_arguments(self, parser):
        parser.add_argument(
            'school_year',
            type=str,
            help='School year in format YYYY-YYYY (e.g., 2024-2025)',
        )
        parser.add_argument(
            '--for-grade-level',
            type=str,
            choices=['7-10', '11-12'],
            default='7-10',
            help='Grade level group: 7-10 (quarters only) or 11-12 (quarters grouped into semesters)',
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
            '--set-current',
            type=int,
            default=1,
            help='Quarter number to set as current (default: 1)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating',
        )

    def handle(self, *args, **options):
        school_year = options['school_year']
        grade_level_group = options['for_grade_level']
        start_month = options['start_month']
        start_day = options['start_day']
        quarter_weeks = options['quarter_weeks']
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

        # Generate quarter periods based on grade level group
        periods_to_create = self._generate_quarters(
            school_year, start_date, quarter_weeks, set_current, grade_level_group
        )

        # Display what will be created
        self.stdout.write(f"\nGrading Periods for School Year {school_year}:")
        self.stdout.write(f"Grade Level Group: {grade_level_group}")
        self.stdout.write("=" * 70)

        for period_data in periods_to_create:
            current_str = " [CURRENT]" if period_data['is_current'] else ""
            semester_str = f" (Semester {period_data['semester_group']})" if period_data['semester_group'] else ""
            self.stdout.write(
                f"  {period_data['label']:5} {semester_str:15} "
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
                    semester_group=period_data['semester_group'],
                    period_number=period_data['period_number'],
                    defaults={
                        'start_date': period_data['start_date'],
                        'end_date': period_data['end_date'],
                        'is_current': period_data['is_current'],
                        'period_type': 'quarter',  # Always quarter now
                    }
                )
                if created:
                    created_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"\nSuccessfully created {created_count} grading period(s).")
        )

    def _generate_quarters(self, school_year, start_date, weeks_per_quarter, set_current, grade_level_group):
        """
        Generate 4 quarter periods.

        For Grades 7-10: Q1-Q4 with semester_group=null
        For Grades 11-12: Q1-Q2 with semester_group=1, Q3-Q4 with semester_group=2
        """
        periods = []
        current_date = start_date

        # Determine semester group mapping
        # For 11-12: Q1, Q2 -> semester_group=1 (1st Sem); Q3, Q4 -> semester_group=2 (2nd Sem)
        # For 7-10: All quarters have semester_group=null
        for quarter_num in range(1, 5):
            # Calculate end date (weeks_per_quarter weeks later)
            end_date = current_date + timedelta(weeks=weeks_per_quarter)

            # Adjust end date to be the day before the next quarter starts
            if quarter_num < 4:
                end_date = end_date - timedelta(days=1)

            # Determine semester_group
            if grade_level_group == '11-12':
                if quarter_num <= 2:
                    semester_group = 1  # 1st Semester
                else:
                    semester_group = 2  # 2nd Semester
            else:
                semester_group = None  # No semester grouping for Grades 7-10

            periods.append({
                'school_year': school_year,
                'period_type': 'quarter',
                'period_number': quarter_num,
                'semester_group': semester_group,
                'label': f'Q{quarter_num}',
                'start_date': current_date,
                'end_date': end_date,
                'is_current': quarter_num == set_current,
            })

            # Next quarter starts right after this one ends
            if quarter_num < 4:
                current_date = end_date + timedelta(days=1)

        return periods