# SIS Import - Base Processor
"""
Base classes and data structures for CSV import processors.

Provides:
- Data classes for row results, validation, and import results
- Abstract base class with common CSV handling logic
- Validation utilities
"""

import csv
import io
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from django.core.exceptions import ValidationError
from django.core.validators import validate_email


@dataclass
class RowResult:
    """Result of processing a single row."""
    row_number: int
    data: dict[str, Any]
    action: str  # 'created', 'updated', 'skipped', 'error'
    message: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.action != 'error'


@dataclass
class ValidationResult:
    """Result of validating all rows in a CSV file."""
    rows: list[RowResult]
    error_count: int = 0
    warning_count: int = 0
    valid_headers: bool = True
    missing_headers: list[str] = field(default_factory=list)
    extra_headers: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.error_count == 0 and self.valid_headers


@dataclass
class ImportResult:
    """Result of executing an import operation."""
    success: bool
    created: list[RowResult] = field(default_factory=list)
    updated: list[RowResult] = field(default_factory=list)
    skipped: list[RowResult] = field(default_factory=list)
    failed: list[RowResult] = field(default_factory=list)
    message: str = ""

    @property
    def created_count(self) -> int:
        return len(self.created)

    @property
    def updated_count(self) -> int:
        return len(self.updated)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    @property
    def failed_count(self) -> int:
        return len(self.failed)

    @property
    def total_processed(self) -> int:
        return self.created_count + self.updated_count + self.skipped_count + self.failed_count


class BaseCSVProcessor(ABC):
    """
    Abstract base class for CSV import processors.

    Each subclass handles a specific import type (courses, users, sections, enrollments).
    """

    # Maximum number of rows allowed in a CSV file
    MAX_ROWS = 500

    # Warning threshold for row count
    ROW_WARNING_THRESHOLD = 500

    @property
    @abstractmethod
    def import_type(self) -> str:
        """Return the type of import (e.g., 'courses', 'users')."""
        pass

    @property
    @abstractmethod
    def required_headers(self) -> list[str]:
        """Return list of required CSV headers."""
        pass

    @property
    def optional_headers(self) -> list[str]:
        """Return list of optional CSV headers."""
        return []

    @property
    def headers(self) -> list[str]:
        """Return all valid headers (required + optional)."""
        return self.required_headers + self.optional_headers

    def parse_csv(self, file_obj) -> tuple[list[dict[str, str]], list[str]]:
        """
        Parse a CSV file and return list of row dictionaries.

        Args:
            file_obj: File-like object containing CSV data

        Returns:
            Tuple of (rows list, error messages list)
        """
        errors = []

        # Reset file pointer and decode
        file_obj.seek(0)
        try:
            content = file_obj.read()
            if isinstance(content, bytes):
                content = content.decode('utf-8')
        except UnicodeDecodeError:
            errors.append("File must be UTF-8 encoded")
            return [], errors

        # Parse CSV
        reader = csv.DictReader(io.StringIO(content))

        # Check headers
        if reader.fieldnames is None:
            errors.append("CSV file appears to be empty or malformed")
            return [], errors

        # Normalize header names (strip whitespace, lowercase)
        normalized_fieldnames = [f.strip().lower() for f in reader.fieldnames]
        required_set = set(h.lower() for h in self.required_headers)

        # Check for missing required headers
        missing = required_set - set(normalized_fieldnames)
        if missing:
            errors.append(f"Missing required headers: {', '.join(sorted(missing))}")

        if errors:
            return [], errors

        # Map normalized headers to original headers
        header_map = {f.strip().lower(): f.strip() for f in reader.fieldnames}

        rows = []
        for row_num, row in enumerate(reader, start=2):  # Start at 2 (1 is header)
            if len(rows) >= self.MAX_ROWS:
                errors.append(f"File exceeds maximum of {self.MAX_ROWS} rows")
                break

            # Normalize row keys
            normalized_row = {}
            for key, value in row.items():
                normalized_key = key.strip().lower()
                # Use the original header name from header_map if available
                original_key = header_map.get(normalized_key, key.strip())
                normalized_row[original_key] = value.strip() if isinstance(value, str) else value

            rows.append(normalized_row)

        return rows, errors

    def validate_all(self, file_obj) -> ValidationResult:
        """
        Validate all rows in a CSV file.

        Args:
            file_obj: File-like object containing CSV data

        Returns:
            ValidationResult with row results and error/warning counts
        """
        rows, parse_errors = self.parse_csv(file_obj)

        if parse_errors:
            return ValidationResult(
                rows=[],
                error_count=len(parse_errors),
                valid_headers=False,
                missing_headers=[e for e in parse_errors if 'Missing' in e]
            )

        results = []
        error_count = 0
        warning_count = 0

        for row_num, row_dict in enumerate(rows, start=2):
            try:
                result = self.validate_row(row_num, row_dict)
                results.append(result)
                if result.action == 'error':
                    error_count += 1
                warning_count += len(result.warnings)
            except Exception as e:
                results.append(RowResult(
                    row_number=row_num,
                    data=row_dict,
                    action='error',
                    message=str(e)
                ))
                error_count += 1

        return ValidationResult(
            rows=results,
            error_count=error_count,
            warning_count=warning_count,
            valid_headers=True
        )

    @abstractmethod
    def validate_row(self, row_number: int, row_data: dict[str, str]) -> RowResult:
        """
        Validate a single row of data.

        Args:
            row_number: Row number in the CSV (for error messages)
            row_data: Dictionary of column name to value

        Returns:
            RowResult with validation status
        """
        pass

    @abstractmethod
    def process_row(self, row_number: int, row_data: dict[str, str], options: dict[str, Any] = None) -> RowResult:
        """
        Process a single row of data (create or update records).

        Args:
            row_number: Row number in the CSV
            row_data: Dictionary of column name to value
            options: Additional options (e.g., send_credentials for users)

        Returns:
            RowResult with processing status
        """
        pass

    def execute_import(self, file_obj, **options) -> ImportResult:
        """
        Execute the import after validation.

        Args:
            file_obj: File-like object containing CSV data
            **options: Additional options for processing

        Returns:
            ImportResult with created/updated/skipped/failed lists
        """
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

        # Collect credentials for email sending after transaction
        credentials_to_send = []

        # Re-parse to get rows (since validate_all consumed the file)
        rows, _ = self.parse_csv(file_obj)

        for row_num, row_dict in enumerate(rows, start=2):
            try:
                result = self.process_row(row_num, row_dict, options)

                # Collect credentials for later email sending
                if hasattr(result, 'credentials'):
                    credentials_to_send.append(result.credentials)

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

        # Send emails after successful import (for users import)
        if options.get('send_credentials') and credentials_to_send:
            self._send_credentials_emails(credentials_to_send)

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
        """
        Send credentials emails after successful import.
        Override in subclasses if needed.

        Args:
            credentials_list: List of (user, password) tuples
        """
        from core.email_utils import send_credentials_email

        for user, password in credentials_list:
            try:
                send_credentials_email(user, password)
            except Exception:
                # Log but don't fail the import
                pass

    def get_template_csv(self) -> str:
        """
        Generate a template CSV file for this import type.

        Returns:
            CSV content as string
        """
        import io
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header row
        writer.writerow(self.headers)

        # Write example row
        example_row = self._get_example_row()
        if example_row:
            writer.writerow(example_row)

        return output.getvalue()

    def _get_example_row(self) -> list[str]:
        """
        Get an example row for the template CSV.
        Override in subclasses to provide type-specific examples.

        Returns:
            List of example values for each column
        """
        return [''] * len(self.headers)

    # Validation helper methods

    @staticmethod
    def validate_email(email: str) -> tuple[bool, str]:
        """Validate an email address."""
        if not email:
            return False, "Email is required"
        try:
            validate_email(email)
            return True, ""
        except ValidationError:
            return False, f"Invalid email format: {email}"

    @staticmethod
    def validate_school_year(value: str) -> tuple[bool, str]:
        """Validate school year format (YYYY-YYYY)."""
        if not value:
            return False, "School year is required"
        pattern = r'^\d{4}-\d{4}$'
        if not re.match(pattern, value):
            return False, f"Invalid school year format: {value}. Expected format: YYYY-YYYY"
        return True, ""

    @staticmethod
    def validate_boolean(value: str) -> tuple[bool, bool, str]:
        """
        Validate and parse a boolean value.

        Returns:
            Tuple of (is_valid, parsed_value, error_message)
        """
        if not value:
            return True, True, ""  # Default to True

        value_lower = value.lower().strip()
        if value_lower in ('true', '1', 'yes'):
            return True, True, ""
        elif value_lower in ('false', '0', 'no'):
            return True, False, ""
        else:
            return False, True, f"Invalid boolean value: {value}"

    @staticmethod
    def validate_integer(value: str, min_val: int = None, max_val: int = None, default: int = None) -> tuple[bool, int, str]:
        """
        Validate and parse an integer value.

        Returns:
            Tuple of (is_valid, parsed_value, error_message)
        """
        if not value:
            return True, default if default is not None else 0, ""

        try:
            parsed = int(value)
            if min_val is not None and parsed < min_val:
                return False, default if default is not None else 0, f"Value {parsed} is below minimum {min_val}"
            if max_val is not None and parsed > max_val:
                return False, default if default is not None else 0, f"Value {parsed} is above maximum {max_val}"
            return True, parsed, ""
        except ValueError:
            return False, default if default is not None else 0, f"Invalid integer: {value}"