# SIS Import - Enrollments Processor
"""
Processor for importing enrollments from CSV files.

CSV Headers:
  Required: student_email, class_section
  Optional: none

Notes:
  - Student is identified by school email (personal_email is also accepted)
  - Class section is identified by section name
  - Student is enrolled to all active class offerings for that section
"""

from typing import Any

from django.db import transaction
from django.db.models import Q

from .base import BaseCSVProcessor, RowResult
from core.models import User, CourseSection, Section, Enrollment


class EnrollmentCSVProcessor(BaseCSVProcessor):
    """Processor for importing Enrollment records."""

    @property
    def import_type(self) -> str:
        return 'enrollments'

    @property
    def required_headers(self) -> list[str]:
        return ['student_email', 'class_section']

    @property
    def optional_headers(self) -> list[str]:
        return []

    def _find_student(self, student_email: str) -> User | None:
        """Find student by school email (or personal email fallback)."""
        return User.objects.filter(
            Q(email__iexact=student_email) | Q(personal_email__iexact=student_email),
            role=User.Role.STUDENT
        ).first()

    def _find_section(self, class_section_name: str) -> Section | None:
        """
        Find class section by name.

        If multiple sections share the same name across years, use the latest active one.
        """
        section_qs = Section.objects.filter(name__iexact=class_section_name).order_by('-is_active', '-school_year')
        return section_qs.first()

    def validate_row(self, row_number: int, row_data: dict[str, str]) -> RowResult:
        """Validate a single enrollment row."""
        errors = []
        warnings = []

        # Get identifiers
        student_email = row_data.get('student_email', '').strip()
        class_section = row_data.get('class_section', '').strip()

        # Validate student_email
        is_valid_email, email_error = self.validate_email(student_email)
        if not student_email:
            errors.append("Student email is required")
        elif not is_valid_email:
            errors.append(email_error)
        else:
            student = self._find_student(student_email)
            if not student:
                warnings.append(f"Student '{student_email}' not found - row will be skipped")

        if not class_section:
            errors.append("Class section is required")
        else:
            section_matches = Section.objects.filter(name__iexact=class_section)
            match_count = section_matches.count()

            if match_count == 0:
                warnings.append(f"Class section '{class_section}' not found - row will be skipped")
            elif match_count > 1:
                warnings.append(
                    f"Multiple class sections named '{class_section}' found across school years - latest active section will be used"
                )
            else:
                section = section_matches.first()
                class_offerings_count = CourseSection.objects.filter(section=section, is_active=True).count()
                if class_offerings_count == 0:
                    warnings.append(
                        f"Class section '{class_section}' has no active class offerings - row will be skipped"
                    )

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

        student_email = row_data.get('student_email', '').strip()
        class_section_name = row_data.get('class_section', '').strip()

        student = self._find_student(student_email)

        if not student:
            return RowResult(
                row_number=row_number,
                data=row_data,
                action='error',
                message=f"Student '{student_email}' not found"
            )

        section = self._find_section(class_section_name)
        if not section:
            return RowResult(
                row_number=row_number,
                data=row_data,
                action='error',
                message=f"Class section '{class_section_name}' not found"
            )

        course_sections = CourseSection.objects.filter(section=section, is_active=True).select_related('course', 'section')
        if not course_sections.exists():
            return RowResult(
                row_number=row_number,
                data=row_data,
                action='error',
                message=f"No active class offerings found for class section '{section.name}'"
            )

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for course_section in course_sections:
            enrollment, created = Enrollment.objects.get_or_create(
                student=student,
                course_section=course_section,
                defaults={'is_active': True}
            )

            if created:
                created_count += 1
            else:
                if not enrollment.is_active:
                    enrollment.is_active = True
                    enrollment.save(update_fields=['is_active'])
                    updated_count += 1
                else:
                    skipped_count += 1

        if created_count > 0:
            action = 'created'
        elif updated_count > 0:
            action = 'updated'
        else:
            action = 'skipped'

        message = (
            f"Processed section '{section.name}' for {student.email}: "
            f"{created_count} enrolled, {updated_count} re-activated, {skipped_count} already enrolled"
        )

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
            'student@example.edu.ph',  # student_email
            'ICT-A',                   # class_section
        ]
