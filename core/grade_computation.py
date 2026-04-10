# hna-acadex-backend/core/grade_computation.py
"""Grade computation helpers for the DepEd grading system."""

from decimal import Decimal

from django.db.models import Sum

from core.models import GradeWeightConfig, Activity, Quiz, Submission, QuizAttempt
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


def compute_period_grade(student, course_section, grading_period):
    """Compute a student's period grade using DepEd component weights.

    Groups items by component:
    - Written Works: quizzes + activities with component_type='written_works'
                     + activities with is_exam=True AND exam_type='monthly'
    - Performance Tasks: activities with component_type='performance_task'
                         + activities with component_type=None (fallback default)
    - Quarterly Assessment: activities with component_type='quarterly_assessment'
                            + activities with is_exam=True AND exam_type='quarterly'

    Missing submissions count as 0 earned (holistic grading).
    If a component has no items, its weight is redistributed proportionally.

    Returns Decimal (0-100) or None if no items exist at all.
    """
    weight_config = get_or_create_weight_config(course_section)

    start_date = grading_period.start_date
    end_date = grading_period.end_date

    # Get published activities whose deadline falls within the grading period
    activities = Activity.objects.filter(
        course_section=course_section,
        is_published=True,
        deadline__date__gte=start_date,
        deadline__date__lte=end_date,
    )

    # Get published quizzes whose close_at falls within the grading period
    quizzes = Quiz.objects.filter(
        course_section=course_section,
        is_published=True,
        close_at__date__gte=start_date,
        close_at__date__lte=end_date,
    )

    # Component buckets: each entry is (earned: Decimal, possible: Decimal)
    written_works_items = []  # (earned, possible)
    performance_task_items = []
    quarterly_assessment_items = []

    # --- Classify and score activities ---
    for activity in activities:
        # Determine component
        component = _classify_activity_component(activity)

        # Get student's score for this activity
        earned, possible = _score_activity(activity, student)

        if component == "written_works":
            written_works_items.append((earned, possible))
        elif component == "performance_task":
            performance_task_items.append((earned, possible))
        elif component == "quarterly_assessment":
            quarterly_assessment_items.append((earned, possible))

    # --- Classify and score quizzes (always Written Works) ---
    for quiz in quizzes:
        earned, possible = _score_quiz(quiz, student)
        written_works_items.append((earned, possible))

    # --- Compute percentage per component ---
    ww_pct = _compute_component_percentage(written_works_items)
    pt_pct = _compute_component_percentage(performance_task_items)
    qa_pct = _compute_component_percentage(quarterly_assessment_items)

    # --- Apply weighted sum with re-proportioning ---
    ww_weight = Decimal(str(weight_config.written_works))
    pt_weight = Decimal(str(weight_config.performance_tasks))
    qa_weight = Decimal(str(weight_config.quarterly_assessment))

    components = [
        (ww_pct, ww_weight),
        (pt_pct, pt_weight),
        (qa_pct, qa_weight),
    ]

    # Filter out components that have no items (pct is None)
    active_components = [(pct, weight) for pct, weight in components if pct is not None]

    if not active_components:
        return None

    active_weight_total = sum(w for _, w in active_components)

    weighted_sum = sum(
        (pct * weight) / active_weight_total
        for pct, weight in active_components
    )

    return round(weighted_sum, 2)


def _classify_activity_component(activity):
    """Determine which DepEd component an activity belongs to.

    Rules:
    - is_exam=True with exam_type='monthly' -> 'written_works'
    - is_exam=True with exam_type='quarterly' -> 'quarterly_assessment'
    - component_type='written_works' -> 'written_works'
    - component_type='performance_task' -> 'performance_task'
    - component_type='quarterly_assessment' -> 'quarterly_assessment'
    - component_type=None (fallback) -> 'performance_task'
    """
    if activity.is_exam and activity.exam_type == "monthly":
        return "written_works"
    if activity.is_exam and activity.exam_type == "quarterly":
        return "quarterly_assessment"
    if activity.component_type == "written_works":
        return "written_works"
    if activity.component_type == "performance_task":
        return "performance_task"
    if activity.component_type == "quarterly_assessment":
        return "quarterly_assessment"
    # Fallback: None or unrecognized -> performance_task
    return "performance_task"


def _score_activity(activity, student):
    """Get (earned, possible) for an activity for a given student.

    Uses score_selection_policy (highest/latest) to pick the best submission.
    Missing submissions: earned = 0 (holistic).
    Returns (Decimal earned, Decimal possible).
    """
    possible = Decimal(str(activity.points))

    submissions = Submission.objects.filter(
        activity=activity,
        student=student,
    )

    if activity.score_selection_policy == Activity.ScorePolicy.HIGHEST:
        submission = submissions.order_by("-score").first()
    else:  # LATEST
        submission = submissions.order_by("-attempt_number").first()

    if submission is not None and submission.score is not None:
        earned = submission.score
    else:
        # Holistic: no submission or ungraded = 0
        earned = Decimal("0")

    return (earned, possible)


def _score_quiz(quiz, student):
    """Get (earned, possible) for a quiz for a given student.

    Uses score_selection_policy (highest/latest) to pick the best attempt.
    Missing attempts: earned = 0 (holistic).
    For possible: uses max_score from the attempt if available, otherwise
    sums points from QuizQuestion.
    Returns (Decimal earned, Decimal possible).
    """
    attempts = QuizAttempt.objects.filter(
        quiz=quiz,
        student=student,
        is_submitted=True,
    )

    if quiz.score_selection_policy == Quiz.ScorePolicy.HIGHEST:
        attempt = attempts.order_by("-score").first()
    else:  # LATEST
        attempt = attempts.order_by("-submitted_at").first()

    if attempt is not None and attempt.score is not None:
        earned = attempt.score
        # Use attempt's max_score if available, otherwise fall back to question sum
        if attempt.max_score is not None:
            possible = attempt.max_score
        else:
            possible = _quiz_max_score(quiz)
    else:
        # Holistic: no attempt or no score = 0
        earned = Decimal("0")
        possible = _quiz_max_score(quiz)

    return (earned, possible)


def _quiz_max_score(quiz):
    """Compute the max possible score for a quiz from its questions."""
    total = quiz.questions.aggregate(total=Sum("points"))["total"]
    if total is not None:
        return Decimal(str(total))
    return Decimal("0")


def _compute_component_percentage(items):
    """Compute percentage for a component from a list of (earned, possible) tuples.

    Returns Decimal percentage (0-100), or None if there are no items.
    """
    if not items:
        return None

    total_earned = sum(earned for earned, _ in items)
    total_possible = sum(possible for _, possible in items)

    if total_possible == Decimal("0"):
        return None

    return (total_earned / total_possible) * Decimal("100")