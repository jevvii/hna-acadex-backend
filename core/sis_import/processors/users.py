# SIS Import - Users Processor
"""
Processor for importing users (students and teachers) from CSV files.

CSV Headers:
  Required: role, first_name, last_name, personal_email
  Optional: middle_name, grade_level, strand, section, status

Notes:
  - 'admin' role is not allowed for import
  - student_id/employee_id is auto-generated
  - school email is auto-generated from name parts
  - Password is auto-generated
  - Optionally sends credentials email
"""

from dataclasses import dataclass
from typing import Any

from django.db import transaction

from .base import BaseCSVProcessor, RowResult
from core.models import User
from core.utils import generate_student_id, generate_teacher_id, generate_school_email_from_parts
from core.email_utils import generate_random_password


class UserCSVProcessor(BaseCSVProcessor):
    """Processor for importing User records (students and teachers)."""

    # Store credentials for email sending after transaction
    _credentials_list = []

    @property
    def import_type(self) -> str:
        return 'users'

    @property
    def required_headers(self) -> list[str]:
        return ['role', 'first_name', 'last_name', 'personal_email']

    @property
    def optional_headers(self) -> list[str]:
        return ['middle_name', 'grade_level', 'strand', 'section', 'status', 'is_irregular']

    def validate_row(self, row_number: int, row_data: dict[str, str]) -> RowResult:
        """Validate a single user row."""
        errors = []
        warnings = []

        # Validate role
        role = row_data.get('role', '').strip().lower()
        valid_roles = ['student', 'teacher']
        if not role:
            errors.append("Role is required")
        elif role == 'admin':
            errors.append("Cannot import admin users via CSV")
        elif role not in valid_roles:
            errors.append(f"Invalid role '{role}'. Valid options: student, teacher")

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

        # Validate grade_level
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

        # Validate status
        status = row_data.get('status', '').strip()
        if status:
            valid_statuses = [choice[0] for choice in User.Status.choices]
            if status not in valid_statuses:
                errors.append(f"Invalid status '{status}'. Valid options: {', '.join(valid_statuses)}")

        action = 'error' if errors else 'valid'

        return RowResult(
            row_number=row_number,
            data=row_data,
            action=action,
            message='; '.join(errors) if errors else 'Valid',
            warnings=warnings
        )

    def process_row(self, row_number: int, row_data: dict[str, str], options: dict[str, Any] = None) -> RowResult:
        """Create a user from row data."""
        options = options or {}
        send_credentials = options.get('send_credentials', False)

        # Extract and clean values
        role = row_data.get('role', '').strip().lower()
        first_name = row_data.get('first_name', '').strip()
        last_name = row_data.get('last_name', '').strip()
        middle_name = row_data.get('middle_name', '').strip() or None
        personal_email = row_data.get('personal_email', '').strip()
        grade_level = row_data.get('grade_level', '').strip() or None
        strand = row_data.get('strand', '').strip() or None
        section = row_data.get('section', '').strip() or None
        status = row_data.get('status', '').strip() or User.Status.ACTIVE
        is_irregular = row_data.get('is_irregular', '').strip().lower() in ('true', '1', 'yes')

        # Generate password
        plain_password = generate_random_password()

        # Generate ID and school email based on role
        if role == 'student':
            generated_id = generate_student_id()
            school_email = generate_school_email_from_parts(
                first_name, last_name, middle_name, 'student', generated_id
            )
            student_id = generated_id
            employee_id = None
        else:  # teacher
            generated_id = generate_teacher_id()
            school_email = generate_school_email_from_parts(
                first_name, last_name, middle_name, 'teacher', generated_id
            )
            student_id = None
            employee_id = generated_id

        # Create user (create-only logic)
        user = User.objects.create(
            email=school_email,
            username=school_email,
            first_name=first_name,
            last_name=last_name,
            middle_name=middle_name,
            personal_email=personal_email,
            role=role,
            status=status,
            student_id=student_id,
            employee_id=employee_id,
            grade_level=grade_level,
            strand=strand,
            section=section,
            is_irregular=is_irregular,
            requires_setup=True,
        )
        user.set_password(plain_password)
        user.save()

        # Store credentials for email sending
        credentials = None
        if send_credentials and personal_email:
            credentials = (user, plain_password)

        message = f"{'Student' if role == 'student' else 'Teacher'} '{first_name} {last_name}' created with school email: {school_email}"

        result = RowResult(
            row_number=row_number,
            data=row_data,
            action='created',
            message=message
        )

        # Attach credentials for email sending
        result.credentials = credentials

        return result

    def execute_import(self, file_obj, **options) -> 'ImportResult':
        """Execute import with transaction safety and email sending."""
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
        credentials_list = []

        # Re-parse to get rows
        rows, _ = self.parse_csv(file_obj)

        with transaction.atomic():
            for row_num, row_dict in enumerate(rows, start=2):
                try:
                    result = self.process_row(row_num, row_dict, options)

                    if result.action == 'created':
                        created.append(result)
                        # Collect credentials
                        if hasattr(result, 'credentials') and result.credentials:
                            credentials_list.append(result.credentials)
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

        # Send emails AFTER transaction commits
        if options.get('send_credentials') and credentials_list:
            self._send_credentials_emails(credentials_list)

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

    def _send_credentials_emails(self, credentials_list: list[tuple]) -> None:
        """Send credentials emails after successful import."""
        from core.email_utils import send_credentials_email

        for user, password in credentials_list:
            try:
                send_credentials_email(user, password)
            except Exception as e:
                # Log but don't fail
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to send credentials email to {user.email}: {e}")

    def _get_example_row(self) -> list[str]:
        """Get an example row for the template CSV."""
        return [
            'student',           # role
            'Juan',              # first_name
            'Dela Cruz',         # last_name
            'juan.delacruz@example.com',  # personal_email
            'B.',                # middle_name
            'Grade 7',           # grade_level
            'STEM',              # strand
            'ICT-A',             # section
            'active',            # status
            'false',             # is_irregular
        ]