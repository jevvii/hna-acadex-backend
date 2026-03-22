# Teacher Portal Package
"""
Teacher Advisory Portal for HNA Acadex.

This package provides a separate admin site for teachers to manage their
advisory sections, including student enrollment and SIS import functionality.
"""

from .site import teacher_portal_site

__all__ = ['teacher_portal_site']