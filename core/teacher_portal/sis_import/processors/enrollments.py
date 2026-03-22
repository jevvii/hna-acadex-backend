# Teacher Portal - Enrollments CSV Processor
"""
Scoped processor for importing enrollments via CSV in the teacher portal.

Teachers can only enroll students from their advisory section.
Irregular students can be enrolled in any course section.
"""

from typing import Any

from django.db.models import Q

from core.sis_import.processors.base import BaseCSVProcessor, RowResult
from core.models import User, Course, CourseSection, Section, Enrollment


class TeacherScopedEnrollmentCSVProcessor(BaseCSVProcessor):
    """
    Processor for importing enrollments scoped to a teacher's advisory.

    Students must be in the advisory section or be marked as irregular.
    Course sections must belong to the advisory section for regular students.
    """

    def __init__(self, advisory_section, advisory_school_year: str):
        self.advisory_section = advisory_section
        self.advisory_school_year = advisory_school_year

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

        # Validate student_id
        if not student_id:
            errors.append("Student ID is required")
        else:
            # Look up student
            if '@' in student_id:
                student = User.objects.filter(
                    Q(personal_email=student_id) | Q(email=student_id),
                    role=User.Role.STUDENT
                ).first()
            else:
                student = User.objects.filter(student_id=student_id, role=User.Role.STUDENT).first()

            if not student:
                errors.append(f"Student '{student_id}' not found")
            else:
                # Check if student is in advisory section or is irregular
                if student.section != self.advisory_section.name and not student.is_irregular:
                    errors.append(
                        f"Student '{student_id}' is not in your advisory section "
                        f"({self.advisory_section.name}) and is not marked as irregular."
                    )
                elif student.section == self.advisory_section.name:
                    # Student is in advisory - verify section matches
                    if section_name and section_name != self.advisory_section.name:
                        warnings.append(
                            f"Section name '{section_name}' differs from your advisory section. "
                            f"Using {self.advisory_section.name}."
                        )

        # Validate course
        if not course_code:
            errors.append("Course code is required")

        # Validate school year
        is_valid_sy, sy_error = self.validate_school_year(school_year)
        if not school_year:
            errors.append("School year is required")
        elif not is_valid_sy:
            errors.append(sy_error)

        # Check course exists
        if course_code and school_year and is_valid_sy:
            course = Course.objects.filter(code=course_code, school_year=school_year).first()
            if not course:
                errors.append(f"Course '{course_code}' for {school_year} not found")

        # Check CourseSection exists and belongs to advisory for regular students
        if course_code and school_year and is_valid_sy:
            course = Course.objects.filter(code=course_code, school_year=school_year).first()
            if course:
                course_sections = CourseSection.objects.filter(
                    course=course,
                    school_year=school_year
                )

                if section_name:
                    section = Section.objects.filter(name=section_name, school_year=school_year).first()
                    if section:
                        course_sections = course_sections.filter(section=section)
                else:
                    # Default to advisory section
                    course_sections = course_sections.filter(section=self.advisory_section)

                if semester:
                    course_sections = course_sections.filter(semester=semester)

                count = course_sections.count()
                if count == 0:
                    # For regular students, course must be in advisory section
                    if student and not student.is_irregular:
                        errors.append(
                            f"No matching CourseSection found for '{course_code}' in your "
                            f"advisory section '{self.advisory_section.name}' for {school_year}."
                        )
                    else:
                        warnings.append(
                            f"No matching CourseSection found for '{course_code}'. "
                            "Irregular students may be enrolled in any course."
                        )
                elif count > 1:
                    warnings.append(
                        f"Multiple CourseSections ({count}) found for '{course_code}'. "
                        "First match will be used."
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
        else:
            # Default to advisory section for lookup
            course_sections = course_sections.filter(section=self.advisory_section)

        if semester:
            course_sections = course_sections.filter(semester=semester)

        course_section = course_sections.first()

        if not course_section:
            # For irregular students, try to find any matching section
            if student.is_irregular:
                course_sections = CourseSection.objects.filter(
                    course=course,
                    school_year=school_year,
                    is_active=True
                )
                if semester:
                    course_sections = course_sections.filter(semester=semester)
                course_section = course_sections.first()

            if not course_section:
                return RowResult(
                    row_number=row_number,
                    data=row_data,
                    action='error',
                    message=f"No matching CourseSection found for '{course_code}' in {school_year}"
                )

        # Validate enrollment rules
        if not student.is_irregular and course_section.section != self.advisory_section:
            return RowResult(
                row_number=row_number,
                data=row_data,
                action='error',
                message=f"Regular students can only be enrolled in courses from their advisory section. "
                        f"Student '{student_identifier}' is regular but course is in section '{course_section.section.name}'."
            )

        # Create enrollment
        enrollment, created = Enrollment.objects.get_or_create(
            student=student,
            course_section=course_section,
            defaults={'is_active': True}
        )

        if created:
            message = f"Enrolled {student.email} in {course_section}"
            action = 'created'
        else:
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

    def _get_example_row(self) -> list[str]:
        """Get an example row for the template CSV."""
        return [
            '120240001',         # student_id
            'MATH101',           # course_code
            '2024-2025',         # school_year
            '',                  # section_name (optional, defaults to advisory section)
            '1st Semester',      # semester (optional)
        ]