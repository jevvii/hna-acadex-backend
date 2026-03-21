# SIS Import - Enrollments Processor
"""
Processor for importing enrollments from CSV files.

CSV Headers:
  Required: student_id, course_code, school_year
  Optional: section_name, semester

Notes:
  - Student can be identified by student_id or personal_email
  - Course is identified by code + school_year
  - CourseSection is found by course + optional section_name/semester filters
"""

from typing import Any

from django.db import transaction
from django.db.models import Q

from .base import BaseCSVProcessor, RowResult
from core.models import User, Course, CourseSection, Section, Enrollment


class EnrollmentCSVProcessor(BaseCSVProcessor):
    """Processor for importing Enrollment records."""

    @property
    def import_type(self) -> str:
        return 'enrollments'

    @property
    def required_headers(self) -> list[str]:
        return ['student_id', 'course_code', 'school_year']

    @property
    def optional_headers(self) -> list[str]:
        return ['section_name', 'semester']

    def validate_row(self, row_number: int, row_data: dict[str, str]) -> RowResult:
        """Validate a single enrollment row."""
        errors = []
        warnings = []

        # Get identifiers
        student_id = row_data.get('student_id', '').strip()
        course_code = row_data.get('course_code', '').strip()
        school_year = row_data.get('school_year', '').strip()
        section_name = row_data.get('section_name', '').strip() or None
        semester = row_data.get('semester', '').strip() or None

        # Validate student_id (can be student ID or email)
        if not student_id:
            errors.append("Student ID or email is required")
        else:
            # Check if student exists
            if '@' in student_id:
                # It's an email - look for personal_email or school email
                student = User.objects.filter(
                    Q(personal_email=student_id) | Q(email=student_id),
                    role=User.Role.STUDENT
                ).first()
            else:
                # It's a student ID
                student = User.objects.filter(student_id=student_id, role=User.Role.STUDENT).first()

            if not student:
                warnings.append(f"Student '{student_id}' not found - will be skipped during import")

        # Validate course
        if not course_code:
            errors.append("Course code is required")

        # Validate school year
        is_valid_sy, sy_error = self.validate_school_year(school_year)
        if not school_year:
            errors.append("School year is required")
        elif not is_valid_sy:
            errors.append(sy_error)

        # Check if course exists
        if course_code and school_year and is_valid_sy:
            course = Course.objects.filter(code=course_code, school_year=school_year).first()
            if not course:
                warnings.append(f"Course '{course_code}' for {school_year} not found")

        # Check if CourseSection exists (if we can identify it)
        if course_code and school_year:
            course = Course.objects.filter(code=course_code, school_year=school_year).first()
            if course:
                course_sections = CourseSection.objects.filter(
                    course=course,
                    school_year=school_year
                )
                if section_name:
                    # Try to find by section name
                    try:
                        section = Section.objects.filter(name=section_name, school_year=school_year).first()
                        if section:
                            course_sections = course_sections.filter(section=section)
                    except Exception:
                        pass

                if semester:
                    course_sections = course_sections.filter(semester=semester)

                count = course_sections.count()
                if count == 0:
                    warnings.append(f"No matching CourseSection found for {course_code} in {school_year}")
                elif count > 1:
                    warnings.append(f"Multiple CourseSections ({count}) found for {course_code} - will use first match")

        action = 'error' if errors else 'valid'

        return RowResult(
            row_number=row_number,
            data=row_data,
            action=action,
            message='; '.join(errors) if errors else 'Valid',
            warnings=warnings
        )

    def process_row(self, row_number: int, row_data: dict[str, str], options: dict[str, Any] = None) -> RowResult:
        """Create an enrollment from row data."""
        options = options or {}

        # Extract identifiers
        student_identifier = row_data.get('student_id', '').strip()
        course_code = row_data.get('course_code', '').strip()
        school_year = row_data.get('school_year', '').strip()
        section_name = row_data.get('section_name', '').strip() or None
        semester = row_data.get('semester', '').strip() or None

        # Find student
        if '@' in student_identifier:
            student = User.objects.filter(
                Q(personal_email=student_identifier) | Q(email=student_identifier),
                role=User.Role.STUDENT
            ).first()
        else:
            student = User.objects.filter(student_id=student_identifier, role=User.Role.STUDENT).first()

        if not student:
            return RowResult(
                row_number=row_number,
                data=row_data,
                action='error',
                message=f"Student '{student_identifier}' not found"
            )

        # Find course
        course = Course.objects.filter(code=course_code, school_year=school_year).first()
        if not course:
            return RowResult(
                row_number=row_number,
                data=row_data,
                action='error',
                message=f"Course '{course_code}' for {school_year} not found"
            )

        # Find CourseSection
        course_sections = CourseSection.objects.filter(course=course, school_year=school_year)

        if section_name:
            section = Section.objects.filter(name=section_name, school_year=school_year).first()
            if section:
                course_sections = course_sections.filter(section=section)

        if semester:
            course_sections = course_sections.filter(semester=semester)

        course_section = course_sections.first()

        if not course_section:
            return RowResult(
                row_number=row_number,
                data=row_data,
                action='error',
                message=f"No matching CourseSection found for {course_code} in {school_year}"
            )

        # Create enrollment (get_or_create to avoid duplicates)
        enrollment, created = Enrollment.objects.get_or_create(
            student=student,
            course_section=course_section,
            defaults={'is_active': True}
        )

        if created:
            message = f"Enrolled {student.email} in {course_section}"
            action = 'created'
        else:
            # Update to active if it was inactive
            if not enrollment.is_active:
                enrollment.is_active = True
                enrollment.save(update_fields=['is_active'])
                message = f"Re-activated enrollment for {student.email} in {course_section}"
                action = 'updated'
            else:
                message = f"Enrollment already exists for {student.email} in {course_section}"
                action = 'skipped'

        return RowResult(
            row_number=row_number,
            data=row_data,
            action=action,
            message=message
        )

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

    def _get_example_row(self) -> list[str]:
        """Get an example row for the template CSV."""
        return [
            '120240001',         # student_id (or email)
            'MATH101',           # course_code
            '2024-2025',         # school_year
            'ICT-A',             # section_name
            '1st Semester',      # semester
        ]