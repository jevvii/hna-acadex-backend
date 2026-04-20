# SIS Import - Courses Processor
"""
Processor for importing courses from CSV files.

CSV Headers:
  Required: code, title, school_year
  Optional: description, grade_level, strand, semester, num_weeks, is_active, category, cover_image_url
"""

from dataclasses import dataclass
from typing import Any

from django.db import transaction

from .base import BaseCSVProcessor, RowResult
from core.models import Course, User


class CourseCSVProcessor(BaseCSVProcessor):
    """Processor for importing Course records."""

    @property
    def import_type(self) -> str:
        return 'courses'

    @property
    def required_headers(self) -> list[str]:
        return ['code', 'title', 'school_year']

    @property
    def optional_headers(self) -> list[str]:
        return ['description', 'grade_level', 'strand', 'semester', 'num_weeks', 'is_active', 'category', 'cover_image_url']

    def validate_row(self, row_number: int, row_data: dict[str, str]) -> RowResult:
        """Validate a single course row."""
        errors = []
        warnings = []

        # Validate required fields
        code = row_data.get('code', '').strip()
        title = row_data.get('title', '').strip()
        school_year = row_data.get('school_year', '').strip()

        if not code:
            errors.append("Course code is required")
        if not title:
            errors.append("Course title is required")

        # Validate school year format
        is_valid_sy, sy_error = self.validate_school_year(school_year)
        if not is_valid_sy:
            errors.append(sy_error)

        # Validate grade level
        grade_level = row_data.get('grade_level', '').strip()
        if grade_level:
            valid_grades = [choice[0] for choice in User.GradeLevel.choices]
            if grade_level not in valid_grades:
                errors.append(f"Invalid grade_level '{grade_level}'. Valid options: {', '.join(valid_grades)}")

        # Validate strand
        strand = row_data.get('strand', '').strip()
        if strand:
            valid_strands = [choice[0] for choice in User.Strand.choices]
            if strand not in valid_strands:
                errors.append(f"Invalid strand '{strand}'. Valid options: {', '.join(valid_strands)}")

        # Validate category
        category = row_data.get('category', '').strip()
        if category:
            valid_categories = [choice[0] for choice in Course.SubjectCategory.choices]
            if category not in valid_categories:
                errors.append(f"Invalid category '{category}'. Valid options: {', '.join(valid_categories)}")

        # Validate num_weeks
        num_weeks_str = row_data.get('num_weeks', '').strip()
        if num_weeks_str:
            is_valid, num_weeks, error = self.validate_integer(num_weeks_str, min_val=1, max_val=52, default=18)
            if not is_valid:
                errors.append(error)

        # Validate is_active
        is_active_str = row_data.get('is_active', '').strip()
        if is_active_str:
            is_valid, _, error = self.validate_boolean(is_active_str)
            if not is_valid:
                errors.append(error)

        # Check for existing course (upsert logic)
        if code and school_year and is_valid_sy:
            existing = Course.objects.filter(
                code=code,
                school_year=school_year
            ).first()
            if existing:
                warnings.append(f"Course '{code}' for {school_year} already exists and will be updated")

        action = 'error' if errors else ('skipped' if warnings and not code else 'valid')

        return RowResult(
            row_number=row_number,
            data=row_data,
            action=action,
            message='; '.join(errors) if errors else 'Valid',
            warnings=warnings
        )

    def process_row(self, row_number: int, row_data: dict[str, str], options: dict[str, Any] = None) -> RowResult:
        """Create or update a course from row data."""
        options = options or {}

        # Extract and clean values
        code = row_data.get('code', '').strip()
        title = row_data.get('title', '').strip()
        school_year = row_data.get('school_year', '').strip()
        description = row_data.get('description', '').strip() or None
        grade_level = row_data.get('grade_level', '').strip() or None
        strand = row_data.get('strand', '').strip() or None
        semester = row_data.get('semester', '').strip() or None
        category = row_data.get('category', '').strip() or None
        cover_image_url = row_data.get('cover_image_url', '').strip() or None

        # Parse num_weeks
        num_weeks_str = row_data.get('num_weeks', '').strip()
        _, num_weeks, _ = self.validate_integer(num_weeks_str, min_val=1, max_val=52, default=18)

        # Parse is_active
        is_active_str = row_data.get('is_active', '').strip()
        _, is_active, _ = self.validate_boolean(is_active_str)

        # Upsert: find by code + school_year
        course, created = Course.objects.update_or_create(
            code=code,
            school_year=school_year,
            defaults={
                'title': title,
                'description': description,
                'grade_level': grade_level,
                'strand': strand,
                'semester': semester,
                'num_weeks': num_weeks,
                'is_active': is_active,
                'category': category,
                'cover_image_url': cover_image_url,
            }
        )

        action = 'created' if created else 'updated'
        message = f"Course '{code}' {'created' if created else 'updated'} for {school_year}"

        return RowResult(
            row_number=row_number,
            data=row_data,
            action=action,
            message=message
        )

    def _get_example_row(self) -> list[str]:
        """Get an example row for the template CSV."""
        return [
            'MATH101',           # code
            'Algebra I',         # title
            '2024-2025',         # school_year
            'Introduction to Algebra',  # description
            'Grade 7',           # grade_level
            'STEM',              # strand
            '1st Semester',      # semester
            '18',                # num_weeks
            'true',              # is_active
            'science_math',      # category
            'https://example.com/cover.jpg',  # cover_image_url
        ]

    def execute_import(self, file_obj, **options) -> 'ImportResult':
        """Execute import with transaction safety."""
        from .base import ImportResult

        validation_result = self.validate_all(file_obj)

        if not validation_result.is_valid:
            return ImportResult(
                success=False,
                failed=[
                    RowResult(row_number=0, data={}, action='error', message=msg)
                    for msg in validation_result.missing_headers
                ],
                message="Validation failed"
            )

        created = []
        updated = []
        skipped = []
        failed = []

        # Re-parse to get rows
        rows, _ = self.parse_csv(file_obj)

        with transaction.atomic():
            for row_num, row_dict in enumerate(rows, start=2):
                try:
                    result = self.process_row(row_num, row_dict, options)

                    if result.action == 'created':
                        created.append(result)
                    elif result.action == 'updated':
                        updated.append(result)
                    elif result.action == 'skipped':
                        skipped.append(result)
                    else:
                        failed.append(result)

                except Exception as e:
                    failed.append(RowResult(
                        row_number=row_num,
                        data=row_dict,
                        action='error',
                        message=str(e)
                    ))

        success = len(failed) == 0
        message = f"Import complete: {len(created)} created, {len(updated)} updated, {len(skipped)} skipped, {len(failed)} failed"

        return ImportResult(
            success=success,
            created=created,
            updated=updated,
            skipped=skipped,
            failed=failed,
            message=message
        )