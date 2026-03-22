# SIS Import - CourseSection Processor
"""
Processor for importing CourseSection records from CSV files.

CourseSection represents a class offering (junction between Course + Section + Teacher).

CSV Headers:
  Required: course_code, school_year
  Optional: section_name, semester, teacher_email, is_active
"""

from dataclasses import dataclass
from typing import Any

from django.db import transaction

from .base import BaseCSVProcessor, RowResult
from core.models import Course, Section, User, CourseSection


class CourseSectionCSVProcessor(BaseCSVProcessor):
    """Processor for importing CourseSection (class offering) records."""

    @property
    def import_type(self) -> str:
        return 'course_sections'

    @property
    def required_headers(self) -> list[str]:
        return ['course_code', 'school_year']

    @property
    def optional_headers(self) -> list[str]:
        return ['section_name', 'semester', 'teacher_email', 'is_active']

    def validate_row(self, row_number: int, row_data: dict[str, str]) -> RowResult:
        """Validate a single CourseSection row."""
        errors = []
        warnings = []

        # Extract required fields
        course_code = row_data.get('course_code', '').strip()
        school_year = row_data.get('school_year', '').strip()

        # Validate required fields
        if not course_code:
            errors.append("Course code is required")

        # Validate school year format
        is_valid_sy, sy_error = self.validate_school_year(school_year)
        if not is_valid_sy:
            errors.append(sy_error)

        # Extract optional fields
        section_name = row_data.get('section_name', '').strip()
        semester = row_data.get('semester', '').strip()
        teacher_email = row_data.get('teacher_email', '').strip()
        is_active_str = row_data.get('is_active', '').strip()

        # Validate section_name if provided
        section = None
        if section_name and school_year and is_valid_sy:
            section = Section.objects.filter(
                name=section_name,
                school_year=school_year
            ).first()
            if not section:
                errors.append(f"Section '{section_name}' not found for school year {school_year}")

        # Validate course exists
        course = None
        if course_code and school_year and is_valid_sy:
            course = Course.objects.filter(
                code=course_code,
                school_year=school_year
            ).first()
            if not course:
                errors.append(f"Course '{course_code}' not found for school year {school_year}")

        # Validate teacher_email if provided
        teacher = None
        if teacher_email:
            is_valid_email, email_error = self.validate_email(teacher_email)
            if not is_valid_email:
                errors.append(email_error)
            else:
                teacher = User.objects.filter(email=teacher_email, role=User.Role.TEACHER).first()
                if not teacher:
                    errors.append(f"Teacher with email '{teacher_email}' not found")

        # Validate is_active
        if is_active_str:
            is_valid, _, error = self.validate_boolean(is_active_str)
            if not is_valid:
                errors.append(error)

        # Check for duplicates (course + section + school_year + semester)
        if course and section and school_year and is_valid_sy:
            existing = CourseSection.objects.filter(
                course=course,
                section=section,
                school_year=school_year,
                semester=semester or course.semester or ''
            ).first()
            if existing:
                warnings.append(
                    f"CourseSection '{course_code}' for section '{section_name}' "
                    f"already exists for {school_year} and will be updated"
                )

        action = 'error' if errors else ('skipped' if warnings and not course_code else 'valid')

        return RowResult(
            row_number=row_number,
            data=row_data,
            action=action,
            message='; '.join(errors) if errors else 'Valid',
            warnings=warnings
        )

    def process_row(self, row_number: int, row_data: dict[str, str], options: dict[str, Any] = None) -> RowResult:
        """Create or update a CourseSection from row data."""
        options = options or {}

        # Extract and clean values
        course_code = row_data.get('course_code', '').strip()
        school_year = row_data.get('school_year', '').strip()
        section_name = row_data.get('section_name', '').strip()
        semester = row_data.get('semester', '').strip()
        teacher_email = row_data.get('teacher_email', '').strip()
        is_active_str = row_data.get('is_active', '').strip()

        # Get options for default values
        default_section = options.get('section')
        default_teacher = options.get('teacher')

        # Find Course
        course = Course.objects.filter(
            code=course_code,
            school_year=school_year
        ).first()

        if not course:
            return RowResult(
                row_number=row_number,
                data=row_data,
                action='error',
                message=f"Course '{course_code}' not found for {school_year}"
            )

        # Find Section
        if section_name:
            section = Section.objects.filter(
                name=section_name,
                school_year=school_year
            ).first()
        else:
            section = default_section

        if not section:
            return RowResult(
                row_number=row_number,
                data=row_data,
                action='error',
                message=f"Section '{section_name or '(default)'}' not found for {school_year}"
            )

        # Find Teacher (optional)
        teacher = None
        if teacher_email:
            teacher = User.objects.filter(email=teacher_email, role=User.Role.TEACHER).first()
        elif default_teacher:
            teacher = default_teacher

        # Determine semester (use course's semester if not specified)
        final_semester = semester if semester else (course.semester if course.semester else '')

        # Parse is_active
        _, is_active, _ = self.validate_boolean(is_active_str)

        # Upsert: find by course + section + school_year + semester
        defaults = {
            'teacher': teacher,
            'is_active': is_active,
        }

        course_section, created = CourseSection.objects.update_or_create(
            course=course,
            section=section,
            school_year=school_year,
            semester=final_semester,
            defaults=defaults
        )

        action = 'created' if created else 'updated'
        teacher_info = f" (teacher: {teacher.email})" if teacher else ""
        message = f"CourseSection '{course_code}@{section.name}' {'created' if created else 'updated'} for {school_year}{teacher_info}"

        return RowResult(
            row_number=row_number,
            data=row_data,
            action=action,
            message=message
        )

    def _get_example_row(self) -> list[str]:
        """Get an example row for the template CSV."""
        return [
            'MATH101',           # course_code
            '2024-2025',         # school_year
            'Section A',         # section_name
            '1st Semester',      # semester
            'teacher@school.edu', # teacher_email
            'true',              # is_active
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