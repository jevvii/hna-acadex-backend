# hna-acadex-backend/core/grade_computation.py
"""Grade computation helpers for the DepEd grading system."""

from core.models import GradeWeightConfig
from core.grade_constants import DEPED_DEFAULT_WEIGHTS, DEFAULT_WEIGHTS


def get_or_create_weight_config(course_section):
    """Get or create GradeWeightConfig for a course section.

    If no config exists, create one with DepEd defaults based on the
    course's subject category. Falls back to 25/50/25 if category is null.
    """
    try:
        return course_section.grade_weight_config
    except GradeWeightConfig.DoesNotExist:
        category = course_section.course.category if course_section.course else None
        defaults = DEPED_DEFAULT_WEIGHTS.get(category, DEFAULT_WEIGHTS)
        config = GradeWeightConfig.objects.create(
            course_section=course_section,
            written_works=defaults["written_works"],
            performance_tasks=defaults["performance_tasks"],
            quarterly_assessment=defaults["quarterly_assessment"],
            is_customized=False,
        )
        return config