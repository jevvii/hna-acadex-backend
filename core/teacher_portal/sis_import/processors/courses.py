# Teacher Portal - Courses CSV Processor
"""
Scoped processor for importing courses via CSV in the teacher portal.

Teachers can import courses for their advisory curriculum.
Courses are school-wide but this provides scoped access for teachers.
"""

from typing import Any

from core.sis_import.processors.courses import CourseCSVProcessor
from core.sis_import.processors.base import RowResult
from core.models import Course


class TeacherScopedCourseCSVProcessor(CourseCSVProcessor):
    """
    Processor for importing courses in teacher portal.

    Extends the base CourseCSVProcessor with advisory context.
    Courses are not scoped to sections at the model level,
    but teachers import with their advisory's context for convenience.
    """

    def __init__(self, advisory_section=None):
        self.advisory_section = advisory_section

    @property
    def import_type(self) -> str:
        return 'courses'

    def validate_row(self, row_number: int, row_data: dict[str, str]) -> RowResult:
        """
        Validate a single course row.

        Same validation as parent but with advisory context for information.
        """
        # Use parent validation
        result = super().validate_row(row_number, row_data)

        # Add advisory context warning if grade_level/strand might differ
        if self.advisory_section:
            grade_level = row_data.get('grade_level', '').strip()
            strand = row_data.get('strand', '').strip()

            if grade_level and grade_level != self.advisory_section.grade_level:
                result.warnings.append(
                    f"Course grade_level '{grade_level}' differs from your advisory "
                    f"section grade '{self.advisory_section.grade_level}'."
                )

            if strand and strand != self.advisory_section.strand:
                result.warnings.append(
                    f"Course strand '{strand}' differs from your advisory "
                    f"section strand '{self.advisory_section.strand}'."
                )

        return result

    def process_row(self, row_number: int, row_data: dict[str, str], options: dict[str, Any] = None) -> RowResult:
        """
        Process a course row.

        Uses parent implementation. Courses are school-wide resources.
        """
        return super().process_row(row_number, row_data, options)

    def _get_example_row(self) -> list[str]:
        """Get an example row for the template CSV."""
        return [
            'MATH101',           # code
            'Algebra I',         # title
            '2024-2025',         # school_year
            'Introduction to Algebra',  # description
            'Grade 11',          # grade_level
            'STEM',              # strand
            '1st Semester',      # semester
            '18',                # num_weeks
            'true',              # is_active
            'shs_specialized',   # category
            'https://example.com/cover.jpg',  # cover_image_url
        ]