# Teacher Portal - CourseSections CSV Processor
"""
Scoped processor for importing CourseSections via CSV in the teacher portal.

Teachers can import CourseSections (class offerings) for their advisory.
This creates the junction between Course + Section + Teacher.

Key behaviors:
- section defaults to teacher's advisory section
- school_year defaults to advisory school year
- teacher defaults to importing teacher (can override via CSV)
- validates course grade_level/strand matches advisory
"""

from typing import Any

from core.sis_import.processors.course_sections import CourseSectionCSVProcessor
from core.sis_import.processors.base import RowResult
from core.models import Course, User


class TeacherScopedCourseSectionCSVProcessor(CourseSectionCSVProcessor):
    """
    Processor for importing CourseSections in teacher portal.

    Extends the base CourseSectionCSVProcessor with advisory context.
    """

    def __init__(self, advisory_section=None, advisory_school_year: str = None, teacher_user=None):
        """
        Initialize processor with advisory context.

        Args:
            advisory_section: Section instance (teacher's advisory)
            advisory_school_year: School year string (e.g., '2024-2025')
            teacher_user: User instance (the importing teacher)
        """
        self.advisory_section = advisory_section
        self.advisory_school_year = advisory_school_year
        self.teacher_user = teacher_user

    @property
    def import_type(self) -> str:
        return 'course_sections'

    @property
    def required_headers(self) -> list[str]:
        # school_year is auto-filled from advisory, so only course_code is required
        return ['course_code']

    @property
    def optional_headers(self) -> list[str]:
        # section_name not needed (auto-set to advisory section)
        return ['semester', 'teacher_email', 'is_active']

    def validate_row(self, row_number: int, row_data: dict[str, str]) -> RowResult:
        """
        Validate a single CourseSection row with advisory context.

        Auto-fills:
        - school_year from advisory
        - section from advisory
        - teacher from importing user (unless override provided)
        """
        # Auto-fill school_year from advisory if not provided
        if not row_data.get('school_year') and self.advisory_school_year:
            row_data = dict(row_data)  # Make a copy
            row_data['school_year'] = self.advisory_school_year

        # Use parent validation
        result = super().validate_row(row_number, row_data)

        # Add advisory context warnings
        if self.advisory_section:
            course_code = row_data.get('course_code', '').strip()
            school_year = row_data.get('school_year', '').strip() or self.advisory_school_year

            if course_code and school_year:
                course = Course.objects.filter(
                    code=course_code,
                    school_year=school_year
                ).first()

                if course:
                    # Check grade_level match
                    if course.grade_level and self.advisory_section.grade_level:
                        if course.grade_level != self.advisory_section.grade_level:
                            result.warnings.append(
                                f"Course grade_level '{course.grade_level}' differs from your advisory "
                                f"section grade '{self.advisory_section.grade_level}'."
                            )

                    # Check strand match (only if both have strand)
                    if course.strand and self.advisory_section.strand:
                        if course.strand != self.advisory_section.strand:
                            result.warnings.append(
                                f"Course strand '{course.strand}' differs from your advisory "
                                f"section strand '{self.advisory_section.strand}'."
                            )

        # Check if teacher_email is for a valid teacher
        teacher_email = row_data.get('teacher_email', '').strip()
        if teacher_email:
            teacher = User.objects.filter(email=teacher_email, role=User.Role.TEACHER).first()
            if teacher and not teacher.is_active:
                result.warnings.append(f"Teacher '{teacher_email}' is not active.")

        return result

    def process_row(self, row_number: int, row_data: dict[str, str], options: dict[str, Any] = None) -> RowResult:
        """
        Process a CourseSection row with advisory context.

        Auto-fills defaults from advisory context.
        """
        options = options or {}

        # Add default section and teacher from advisory
        if self.advisory_section:
            options.setdefault('section', self.advisory_section)
        if self.teacher_user:
            options.setdefault('teacher', self.teacher_user)

        # Auto-fill school_year
        if not row_data.get('school_year') and self.advisory_school_year:
            row_data = dict(row_data)  # Make a copy
            row_data['school_year'] = self.advisory_school_year

        return super().process_row(row_number, row_data, options)

    def _get_example_row(self) -> list[str]:
        """Get an example row for the template CSV."""
        # Only include required + optional headers for teacher portal
        return [
            'MATH101',           # course_code (required)
            '1st Semester',      # semester (optional)
            '',                  # teacher_email (optional - defaults to you)
            'true',              # is_active (optional)
        ]

    def get_template_csv(self) -> str:
        """
        Generate a template CSV file with advisory context.

        Includes course codes from courses matching the advisory grade/strand.
        """
        import io
        import csv

        output = io.StringIO()
        writer = csv.writer(output)

        # Write header row
        writer.writerow(self.headers)

        # Get example row with advisory context
        example_row = self._get_example_row()
        writer.writerow(example_row)

        # If we have advisory context, add more example rows with actual course codes
        if self.advisory_school_year:
            courses = Course.objects.filter(
                school_year=self.advisory_school_year,
                is_active=True
            )

            # Filter by grade/strand if available
            if self.advisory_section:
                if self.advisory_section.grade_level:
                    courses = courses.filter(grade_level=self.advisory_section.grade_level)
                if self.advisory_section.strand:
                    courses = courses.filter(strand=self.advisory_section.strand)

            # Add up to 3 more example rows with actual course codes
            for course in courses[:3]:
                writer.writerow([
                    course.code,           # course_code
                    course.semester or '', # semester
                    '',                    # teacher_email (defaults to importing teacher)
                    'true',                # is_active
                ])

        return output.getvalue()