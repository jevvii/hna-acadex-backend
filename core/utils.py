# hna-acadex-backend/core/utils.py
"""
Utility functions for auto-generating school emails and IDs.

ID Format (both Student and Teacher):
    1YYYY####
    - 1: Fixed prefix
    - YYYY: Current year (e.g., 2024)
    - ####: 4-digit sequential number (0001-9999)
    - Overflow: If sequential exceeds 9999, increment prefix (1 → 2)

Email Format:
    {initials}{surname}{last_4_digits_of_id}@{domain}
    - initials: First letter of each word in FIRST name + first letter of MIDDLE (if present)
    - surname: Lowercase LAST name
    - domain: @student.hna.edu.ph (students) or @hna.edu.ph (teachers)

Name Parsing:
    full_name format: "LAST, FIRST, MIDDLE" (MIDDLE is optional)
"""

from django.db import transaction
from django.core.exceptions import ValidationError


def parse_full_name(full_name: str) -> tuple[str, str, str | None]:
    """
    Parse 'LAST, FIRST, MIDDLE' format into (last, first, middle).

    Args:
        full_name: Name in "LAST, FIRST, MIDDLE" format (MIDDLE is optional)

    Returns:
        Tuple of (surname, first_name, middle_name or None)

    Raises:
        ValueError: If the name format is invalid

    Examples:
        >>> parse_full_name("Dela Cruz, Juan")
        ('Dela Cruz', 'Juan', None)
        >>> parse_full_name("Dela Cruz, Juan, B.")
        ('Dela Cruz', 'Juan', 'B.')
        >>> parse_full_name("Santos, Maria Clara")
        ('Santos', 'Maria Clara', None)
        >>> parse_full_name("Santos, Maria Clara, C.")
        ('Santos', 'Maria Clara', 'C.')
    """
    if not full_name or not full_name.strip():
        raise ValueError("Name cannot be empty")

    parts = [p.strip() for p in full_name.split(',')]

    if len(parts) < 2:
        raise ValueError(
            f"Invalid name format: '{full_name}'. "
            "Expected format: 'LAST, FIRST' or 'LAST, FIRST, MIDDLE'"
        )

    surname = parts[0].strip()
    first_name = parts[1].strip()
    middle_name = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None

    if not surname:
        raise ValueError("Surname (LAST name) cannot be empty")
    if not first_name:
        raise ValueError("First name cannot be empty")

    return surname, first_name, middle_name


def generate_initials(first_name: str, middle_name: str | None) -> str:
    """
    Generate initials from first name and optional middle name.

    Takes the first letter of each word in the first name, plus the first
    letter of the middle name (if present).

    Args:
        first_name: First name (may contain multiple words like "Maria Clara")
        middle_name: Middle name or initial (optional)

    Returns:
        Lowercase initials string

    Examples:
        >>> generate_initials("Juan", None)
        'j'
        >>> generate_initials("Juan", "B.")
        'jb'
        >>> generate_initials("Maria Clara", None)
        'mc'
        >>> generate_initials("Maria Clara", "C.")
        'mcc'
    """
    initials = ""

    # Get first letter of each word in first name
    for word in first_name.split():
        if word:
            initials += word[0].lower()

    # Add first letter of middle name if present
    if middle_name and middle_name.strip():
        initials += middle_name.strip()[0].lower()

    return initials


def generate_id_prefix(year: int) -> str:
    """
    Generate the year prefix for IDs (1YYYY).

    Args:
        year: The year (e.g., 2024)

    Returns:
        Year prefix string like '12024'

    Examples:
        >>> generate_id_prefix(2024)
        '12024'
    """
    return f"1{year}"


def generate_student_id() -> str:
    """
    Generate a unique 11-digit student ID.

    Format: 1YYYY####
    - 1: Fixed prefix
    - YYYY: Current year
    - ####: 4-digit sequential number (0001-9999)

    If sequential exceeds 9999, the prefix increments (1 → 2 → 3...).

    Returns:
        Generated student ID string

    Note:
        This function must be called within a transaction to ensure
        uniqueness when creating multiple students concurrently.
    """
    from .models import IDCounter
    from django.utils import timezone

    current_year = timezone.now().year

    # Use select_for_update to prevent race conditions
    with transaction.atomic():
        counter, created = IDCounter.objects.select_for_update().get_or_create(
            year=current_year,
            id_type=IDCounter.Type.STUDENT,
            defaults={'prefix': 1, 'sequential': 0}
        )

        # Increment sequential number
        counter.sequential += 1

        # Handle overflow: if sequential > 9999, increment prefix
        if counter.sequential > 9999:
            counter.prefix += 1
            counter.sequential = 1

        counter.save()

        # Format: {prefix}{year}{sequential:04d}
        student_id = f"{counter.prefix}{current_year}{counter.sequential:04d}"

        return student_id


def generate_teacher_id() -> str:
    """
    Generate a unique 11-digit teacher (employee) ID.

    Format: 1YYYY####
    - 1: Fixed prefix
    - YYYY: Current year
    - ####: 4-digit sequential number (0001-9999)

    If sequential exceeds 9999, the prefix increments (1 → 2 → 3...).

    Returns:
        Generated teacher ID string

    Note:
        This function must be called within a transaction to ensure
        uniqueness when creating multiple teachers concurrently.
    """
    from .models import IDCounter
    from django.utils import timezone

    current_year = timezone.now().year

    # Use select_for_update to prevent race conditions
    with transaction.atomic():
        counter, created = IDCounter.objects.select_for_update().get_or_create(
            year=current_year,
            id_type=IDCounter.Type.TEACHER,
            defaults={'prefix': 1, 'sequential': 0}
        )

        # Increment sequential number
        counter.sequential += 1

        # Handle overflow: if sequential > 9999, increment prefix
        if counter.sequential > 9999:
            counter.prefix += 1
            counter.sequential = 1

        counter.save()

        # Format: {prefix}{year}{sequential:04d}
        teacher_id = f"{counter.prefix}{current_year}{counter.sequential:04d}"

        return teacher_id


def generate_school_email(full_name: str, role: str, id_number: str) -> str:
    """
    Generate school email from name, role, and ID.

    Format: {initials}{surname}{last_4_digits_of_id}@{domain}

    Args:
        full_name: Name in "LAST, FIRST, MIDDLE" format
        role: User role ('student' or 'teacher')
        id_number: Student ID or Employee ID

    Returns:
        Generated school email address

    Raises:
        ValueError: If name format is invalid

    Examples:
        >>> generate_school_email("Dela Cruz, Juan", "student", "120247371")
        'jdelacruz7371@student.hna.edu.ph'
        >>> generate_school_email("Dela Cruz, Juan, B.", "student", "120247371")
        'jbdelacruz7371@student.hna.edu.ph'
        >>> generate_school_email("Santos, Maria Clara", "teacher", "120247890")
        'mcsantos7890@hna.edu.ph'
    """
    # Parse the full name
    surname, first_name, middle_name = parse_full_name(full_name)

    # Generate initials
    initials = generate_initials(first_name, middle_name)

    # Lowercase surname and remove spaces for email compatibility
    surname_lower = surname.lower().replace(' ', '')

    # Get last 4 digits of ID
    last_4_digits = id_number[-4:] if len(id_number) >= 4 else id_number.zfill(4)

    # Determine domain based on role
    if role == 'student':
        domain = '@student.hna.edu.ph'
    else:
        domain = '@hna.edu.ph'

    # Construct email
    email = f"{initials}{surname_lower}{last_4_digits}{domain}"

    return email


def validate_full_name_format(full_name: str) -> tuple[bool, str]:
    """
    Validate that full_name follows the 'LAST, FIRST, MIDDLE' format.

    Args:
        full_name: Name string to validate

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_full_name_format("Dela Cruz, Juan")
        (True, '')
        >>> validate_full_name_format("Dela Cruz, Juan, B.")
        (True, '')
        >>> validate_full_name_format("Juan Dela Cruz")
        (False, "Invalid name format: 'Juan Dela Cruz'. Expected format: 'LAST, FIRST' or 'LAST, FIRST, MIDDLE'")
    """
    try:
        parse_full_name(full_name)
        return True, ''
    except ValueError as e:
        return False, str(e)