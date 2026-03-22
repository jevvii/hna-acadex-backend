# Teacher Portal - Users CSV Processor
"""
Scoped processor for importing students via CSV in the teacher portal.

Teachers can only create students for their advisory section.
"""

from typing import Any

from core.sis_import.processors.base import BaseCSVProcessor, RowResult
from core.models import User
from core.utils import generate_student_id, generate_school_email_from_parts
from core.email_utils import generate_random_password


class TeacherScopedUserCSVProcessor(BaseCSVProcessor):
    """
    Processor for importing students scoped to a teacher's advisory.

    Only allows 'student' role.
    Forces section to advisory section name.
    """

    def __init__(self, advisory_section_name: str, advisory_school_year: str, advisory_section=None):
        self.advisory_section_name = advisory_section_name
        self.advisory_school_year = advisory_school_year
        self.advisory_section = advisory_section

    @property
    def import_type(self) -> str:
        return 'users'

    @property
    def required_headers(self) -> list[str]:
        return ['last_name', 'first_name', 'role', 'personal_email']

    @property
    def optional_headers(self) -> list[str]:
        return ['middle_name', 'grade_level', 'strand', 'status', 'is_irregular']

    def validate_row(self, row_number: int, row_data: dict[str, str]) -> RowResult:
        """Validate a single student row."""
        errors = []
        warnings = []

        # Validate role - must be 'student' only
        role = row_data.get('role', '').strip().lower()
        if not role:
            errors.append("Role is required")
        elif role != 'student':
            errors.append("Only 'student' role is allowed in teacher import")
        elif role == 'admin':
            errors.append("Cannot import admin users via teacher portal")

        # Validate required name fields
        first_name = row_data.get('first_name', '').strip()
        last_name = row_data.get('last_name', '').strip()
        middle_name = row_data.get('middle_name', '').strip() or None

        if not first_name:
            errors.append("First name is required")
        if not last_name:
            errors.append("Last name is required")

        # Validate personal_email
        personal_email = row_data.get('personal_email', '').strip()
        is_valid_email, email_error = self.validate_email(personal_email)
        if not personal_email:
            errors.append("Personal email is required")
        elif not is_valid_email:
            errors.append(email_error)

        # Check for duplicate personal_email
        if personal_email and is_valid_email:
            existing = User.objects.filter(personal_email=personal_email).first()
            if existing:
                errors.append(f"Personal email '{personal_email}' is already used by {existing.email}")

        # Validate grade_level - default to advisory section's grade_level
        grade_level = row_data.get('grade_level', '').strip()
        if not grade_level and self.advisory_section:
            grade_level = self.advisory_section.grade_level
        if grade_level:
            valid_grades = [choice[0] for choice in User.GradeLevel.choices]
            if grade_level not in valid_grades:
                errors.append(f"Invalid grade_level '{grade_level}'. Valid options: {', '.join(valid_grades)}")

        # Validate strand - default to advisory section's strand
        strand = row_data.get('strand', '').strip()
        if not strand and self.advisory_section:
            strand = self.advisory_section.strand
        if strand:
            valid_strands = [choice[0] for choice in User.Strand.choices]
            if strand not in valid_strands:
                errors.append(f"Invalid strand '{strand}'. Valid options: {', '.join(valid_strands)}")

        # Validate status
        status = row_data.get('status', '').strip()
        if status:
            valid_statuses = [choice[0] for choice in User.Status.choices]
            if status not in valid_statuses:
                errors.append(f"Invalid status '{status}'. Valid options: {', '.join(valid_statuses)}")

        # Validate is_irregular
        is_irregular_raw = row_data.get('is_irregular', '').strip().lower()
        if is_irregular_raw and is_irregular_raw not in ('true', 'false', '1', '0', 'yes', 'no'):
            warnings.append(f"Invalid is_irregular value '{row_data.get('is_irregular')}'. Using 'false'.")

        action = 'error' if errors else 'valid'

        return RowResult(
            row_number=row_number,
            data=row_data,
            action=action,
            message='; '.join(errors) if errors else 'Valid',
            warnings=warnings
        )

    def process_row(self, row_number: int, row_data: dict[str, str], options: dict[str, Any] = None) -> RowResult:
        """Create a student from row data."""
        options = options or {}

        # Extract values
        first_name = row_data.get('first_name', '').strip()
        last_name = row_data.get('last_name', '').strip()
        middle_name = row_data.get('middle_name', '').strip() or None
        personal_email = row_data.get('personal_email', '').strip()
        status = row_data.get('status', '').strip() or User.Status.ACTIVE

        # Grade and strand - default from advisory
        grade_level = row_data.get('grade_level', '').strip()
        if not grade_level and self.advisory_section:
            grade_level = self.advisory_section.grade_level

        strand = row_data.get('strand', '').strip()
        if not strand and self.advisory_section:
            strand = self.advisory_section.strand

        # Section is forced to advisory section name
        section = self.advisory_section_name

        # Parse is_irregular
        is_irregular_raw = row_data.get('is_irregular', '').strip().lower()
        is_irregular = is_irregular_raw in ('true', '1', 'yes')

        # Generate password
        plain_password = generate_random_password()

        # Generate student ID and email
        student_id = generate_student_id()
        school_email = generate_school_email_from_parts(
            first_name, last_name, middle_name, 'student', student_id
        )

        # Create student user
        user = User.objects.create(
            email=school_email,
            username=school_email,
            first_name=first_name,
            last_name=last_name,
            middle_name=middle_name,
            personal_email=personal_email,
            role=User.Role.STUDENT,
            status=status,
            student_id=student_id,
            grade_level=grade_level,
            strand=strand,
            section=section,
            is_irregular=is_irregular,
            requires_setup=True,
        )
        user.set_password(plain_password)
        user.save()

        message = f"Student '{first_name} {last_name}' created with school email: {school_email}"

        result = RowResult(
            row_number=row_number,
            data=row_data,
            action='created',
            message=message
        )

        return result

    def _get_example_row(self) -> list[str]:
        """Get an example row for the template CSV."""
        return [
            'student',           # role
            'Juan',              # first_name
            'Dela Cruz',         # last_name
            'juan.delacruz@example.com',  # personal_email
            'B.',                # middle_name
            '',                  # grade_level (will default to advisory section)
            '',                  # strand (will default to advisory section)
            'active',            # status
            'false',             # is_irregular
        ]