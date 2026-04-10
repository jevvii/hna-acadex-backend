# hna-acadex-backend/core/grade_constants.py
"""DepEd default weight mappings for grade computation by subject category."""

DEPED_DEFAULT_WEIGHTS = {
    "languages_ap_esp": {"written_works": 30, "performance_tasks": 50, "quarterly_assessment": 20},
    "science_math": {"written_works": 40, "performance_tasks": 40, "quarterly_assessment": 20},
    "mapeh_epp_tle": {"written_works": 20, "performance_tasks": 60, "quarterly_assessment": 20},
    "shs_core": {"written_works": 25, "performance_tasks": 50, "quarterly_assessment": 25},
    "shs_applied": {"written_works": 25, "performance_tasks": 50, "quarterly_assessment": 25},
    "shs_specialized": {"written_works": 25, "performance_tasks": 50, "quarterly_assessment": 25},
    "shs_tvl": {"written_works": 20, "performance_tasks": 60, "quarterly_assessment": 20},
}

# Null category fallback (same as SHS_CORE)
DEFAULT_WEIGHTS = {"written_works": 25, "performance_tasks": 50, "quarterly_assessment": 25}