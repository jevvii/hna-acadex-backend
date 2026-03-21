# SIS Import - Sections Processor
"""
Processor for importing class sections from CSV files.

CSV Headers:
  Required: name, grade_level, school_year
  Optional: strand, is_active
"""

from dataclasses import dataclass
from typing import Any

from django.db import transaction

from .base import BaseCSVProcessor, RowResult
from core.models import Section, User


class SectionCSVProcessor(BaseCSVProcessor):
    """Processor for importing Section records."""

    @property
    def import_type(self) -> str:
        return 'sections'

    @property
    def required_headers(self) -> list[str]:
        return ['name', 'grade_level', 'school_year']

    @property
    def optional_headers(self) -> list[str]:
        return ['strand', 'is_active']

    def validate_row(self, row_number: int, row_data: dict[str, str]) -> RowResult:
        """Validate a single section row."""
        errors = []
        warnings = []

        # Validate required fields
        name = row_data.get('name', '').strip()
        grade_level = row_data.get('grade_level', '').strip()
        school_year = row_data.get('school_year', '').strip()

        if not name:
            errors.append("Section name is required")

        # Validate grade_level
        if not grade_level:
            errors.append("Grade level is required")
        else:
            valid_grades = [choice[0] for choice in User.GradeLevel.choices]
            if grade_level not in valid_grades:
                errors.append(f"Invalid grade_level '{grade_level}'. Valid options: {', '.join(valid_grades)}")

        # Validate school year
        is_valid_sy, sy_error = self.validate_school_year(school_year)
        if not school_year:
            errors.append("School year is required")
        elif not is_valid_sy:
            errors.append(sy_error)

        # Validate strand
        strand = row_data.get('strand', '').strip()
        if strand:
            valid_strands = [choice[0] for choice in User.Strand.choices]
            if strand not in valid_strands:
                errors.append(f"Invalid strand '{strand}'. Valid options: {', '.join(valid_strands)}")

        # Validate is_active
        is_active_str = row_data.get('is_active', '').strip()
        if is_active_str:
            is_valid, _, error = self.validate_boolean(is_active_str)
            if not is_valid:
                errors.append(error)

        # Check for existing section (upsert logic)
        if name and grade_level and school_year and is_valid_sy:
            existing = Section.objects.filter(
                name=name,
                grade_level=grade_level,
                school_year=school_year
            ).first()
            if existing:
                warnings.append(f"Section '{name}' ({grade_level}, {school_year}) already exists and will be updated")

        action = 'error' if errors else 'valid'

        return RowResult(
            row_number=row_number,
            data=row_data,
            action=action,
            message='; '.join(errors) if errors else 'Valid',
            warnings=warnings
        )

    def process_row(self, row_number: int, row_data: dict[str, str], options: dict[str, Any] = None) -> RowResult:
        """Create or update a section from row data."""
        options = options or {}

        # Extract and clean values
        name = row_data.get('name', '').strip()
        grade_level = row_data.get('grade_level', '').strip()
        school_year = row_data.get('school_year', '').strip()
        strand = row_data.get('strand', '').strip() or None

        # Parse is_active
        is_active_str = row_data.get('is_active', '').strip()
        _, is_active, _ = self.validate_boolean(is_active_str)

        # Upsert: find by name + grade_level + school_year
        section, created = Section.objects.update_or_create(
            name=name,
            grade_level=grade_level,
            school_year=school_year,
            defaults={
                'strand': strand or User.Strand.NONE,
                'is_active': is_active,
            }
        )

        action = 'created' if created else 'updated'
        message = f"Section '{name}' ({grade_level}) {'created' if created else 'updated'} for {school_year}"

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
            'ICT-A',             # name
            'Grade 11',          # grade_level
            '2024-2025',         # school_year
            'STEM',              # strand
            'true',              # is_active
        ]