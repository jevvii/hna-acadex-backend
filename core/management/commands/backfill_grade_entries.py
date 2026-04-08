"""
Django management command to backfill GradeEntry records from existing activity/quiz scores.

This command:
1. Finds all active enrollments
2. For each enrollment and grading period, computes scores from:
   - Activities with deadlines within the period
   - Quizzes with close_at within the period
3. Creates GradeEntry records with computed scores

Usage:
    python manage.py backfill_grade_entries --dry-run
    python manage.py backfill_grade_entries
    python manage.py backfill_grade_entries --school-year=2024-2025
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from decimal import Decimal
from datetime import datetime
from core.models import (
    GradingPeriod,
    Enrollment,
    CourseSection,
    Activity,
    Quiz,
    QuizAttempt,
    Submission,
    GradeEntry,
)


class Command(BaseCommand):
    help = 'Backfill GradeEntry records from existing activity/quiz scores'

    def add_arguments(self, parser):
        parser.add_argument(
            '--school-year',
            type=str,
            default=None,
            help='Only process grading periods for this school year (e.g., 2024-2025)',
        )
        parser.add_argument(
            '--course-section',
            type=str,
            default=None,
            help='Only process this specific course section ID (UUID)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Overwrite existing computed_score values',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed progress',
        )

    def handle(self, *args, **options):
        school_year = options['school_year']
        course_section_id = options['course_section']
        dry_run = options['dry_run']
        force = options['force']
        verbose = options['verbose']

        # Get grading periods
        periods_qs = GradingPeriod.objects.all()
        if school_year:
            periods_qs = periods_qs.filter(school_year=school_year)

        periods = list(periods_qs.order_by('school_year', 'period_number'))
        if not periods:
            self.stdout.write(
                self.style.ERROR("No grading periods found. Run create_grading_periods first.")
            )
            return

        # Get active enrollments
        enrollments_qs = Enrollment.objects.filter(
            is_active=True
        ).select_related('student', 'course_section__course')

        if course_section_id:
            enrollments_qs = enrollments_qs.filter(course_section_id=course_section_id)

        enrollments = list(enrollments_qs)
        if not enrollments:
            self.stdout.write(self.style.WARNING("No active enrollments found."))
            return

        self.stdout.write(f"Found {len(periods)} grading periods")
        self.stdout.write(f"Found {len(enrollments)} active enrollments")

        stats = {
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'no_score': 0,
        }

        if dry_run:
            self.stdout.write(self.style.WARNING("\n[DRY RUN] No changes will be made.\n"))

        # Process each enrollment
        for enrollment in enrollments:
            course_section = enrollment.course_section

            # Determine period type based on grade level
            grade_level = course_section.course.grade_level
            if grade_level in ['Grade 11', 'Grade 12']:
                period_type = 'semester'
            else:
                period_type = 'quarter'

            # Filter periods by type
            relevant_periods = [p for p in periods if p.period_type == period_type and p.school_year == course_section.school_year]

            for period in relevant_periods:
                # Check if entry already exists
                existing_entry = GradeEntry.objects.filter(
                    enrollment=enrollment,
                    grading_period=period
                ).first()

                # Compute score for this period
                computed_score = self._compute_period_score(
                    enrollment.student,
                    course_section,
                    period.start_date,
                    period.end_date,
                    verbose
                )

                if computed_score is None:
                    stats['no_score'] += 1
                    if verbose:
                        self.stdout.write(
                            f"  No score for {enrollment.student.full_name} in {period.label}"
                        )
                    continue

                if dry_run:
                    if existing_entry:
                        stats['updated'] += 1
                        if verbose:
                            self.stdout.write(
                                f"  Would update: {enrollment.student.full_name} - {period.label}: {computed_score:.2f}"
                            )
                    else:
                        stats['created'] += 1
                        if verbose:
                            self.stdout.write(
                                f"  Would create: {enrollment.student.full_name} - {period.label}: {computed_score:.2f}"
                            )
                else:
                    if existing_entry:
                        if force or existing_entry.computed_score != computed_score:
                            existing_entry.computed_score = computed_score
                            existing_entry.save(update_fields=['computed_score', 'computed_at'])
                            stats['updated'] += 1
                        else:
                            stats['skipped'] += 1
                    else:
                        GradeEntry.objects.create(
                            enrollment=enrollment,
                            grading_period=period,
                            computed_score=computed_score,
                            is_published=False,
                        )
                        stats['created'] += 1

        # Print summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("Summary:")
        self.stdout.write(f"  Created: {stats['created']}")
        self.stdout.write(f"  Updated: {stats['updated']}")
        self.stdout.write(f"  Skipped (unchanged): {stats['skipped']}")
        self.stdout.write(f"  No score available: {stats['no_score']}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\n[DRY RUN] Run without --dry-run to apply changes."))

    def _compute_period_score(self, student, course_section, start_date, end_date, verbose=False):
        """
        Compute a student's score for a grading period based on activities and quizzes.

        Returns a Decimal score (0-100) or None if no graded items found.
        """
        # Get activities in this period
        activities = Activity.objects.filter(
            course_section=course_section,
            is_published=True,
            deadline__date__gte=start_date,
            deadline__date__lte=end_date,
        )

        # Get quizzes in this period
        quizzes = Quiz.objects.filter(
            course_section=course_section,
            is_published=True,
            close_at__date__gte=start_date,
            close_at__date__lte=end_date,
        )

        activity_scores = []
        quiz_scores = []

        # Get activity submissions
        for activity in activities:
            submission = Submission.objects.filter(
                activity=activity,
                student=student
            ).order_by('-attempt_number').first()

            if submission and submission.score is not None:
                # Normalize to 0-100 scale
                normalized = (submission.score / Decimal(str(activity.points))) * Decimal('100')
                activity_scores.append(normalized)

        # Get quiz attempts
        for quiz in quizzes:
            attempt = QuizAttempt.objects.filter(
                quiz=quiz,
                student=student,
                is_submitted=True
            ).order_by('-submitted_at').first()

            if attempt and attempt.score is not None and attempt.max_score:
                # Normalize to 0-100 scale
                normalized = (attempt.score / attempt.max_score) * Decimal('100')
                quiz_scores.append(normalized)

        # Combine scores
        all_scores = activity_scores + quiz_scores

        if not all_scores:
            return None

        # Calculate average
        total = sum(all_scores)
        count = len(all_scores)
        average = total / Decimal(str(count))

        # Round to 2 decimal places
        return round(average, 2)