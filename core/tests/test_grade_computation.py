"""Tests for compute_period_grade DepEd-weighted grade computation."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone

from core.models import (
    User,
    Course,
    Section,
    CourseSection,
    GradingPeriod,
    GradeWeightConfig,
    Activity,
    Quiz,
    QuizQuestion,
    QuizAttempt,
    Submission,
)
from core.grade_computation import compute_period_grade


def _make_datetime(d):
    """Convert a date to a timezone-aware datetime at noon."""
    return timezone.make_aware(datetime.combine(d, datetime.min.time().replace(hour=12)))


class ComputePeriodGradeTestBase(TestCase):
    """Base test class that sets up common test fixtures."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def _create_student(self, email="student@test.com"):
        return User.objects.create_user(
            email=email,
            password="testpass123",
            role=User.Role.STUDENT,
            first_name="Test",
            last_name="Student",
        )

    def _create_teacher(self, email="teacher@test.com"):
        return User.objects.create_user(
            email=email,
            password="testpass123",
            role=User.Role.TEACHER,
            first_name="Test",
            last_name="Teacher",
        )

    def _create_course_section(self):
        course = Course.objects.create(
            code="MATH101",
            title="Mathematics",
            grade_level="Grade 7",
            school_year="2024-2025",
        )
        section = Section.objects.create(
            name="Section A",
            grade_level="Grade 7",
        )
        cs = CourseSection.objects.create(
            course=course,
            section=section,
            school_year="2024-2025",
        )
        return cs

    def _create_grading_period(self, start_date=None, end_date=None):
        if start_date is None:
            start_date = date(2024, 10, 1)
        if end_date is None:
            end_date = date(2024, 12, 31)
        return GradingPeriod.objects.create(
            school_year="2024-2025",
            period_type="quarter",
            period_number=1,
            start_date=start_date,
            end_date=end_date,
        )

    def _create_activity(
        self,
        course_section,
        points=100,
        deadline=None,
        component_type=None,
        is_exam=False,
        exam_type=None,
        score_selection_policy=Activity.ScorePolicy.HIGHEST,
    ):
        if deadline is None:
            deadline = _make_datetime(date(2024, 11, 15))
        return Activity.objects.create(
            course_section=course_section,
            title=f"Activity-{Activity.objects.count() + 1}",
            points=points,
            deadline=deadline,
            component_type=component_type,
            is_exam=is_exam,
            exam_type=exam_type,
            score_selection_policy=score_selection_policy,
            is_published=True,
        )

    def _create_quiz(
        self,
        course_section,
        close_at=None,
        score_selection_policy=Quiz.ScorePolicy.HIGHEST,
    ):
        if close_at is None:
            close_at = _make_datetime(date(2024, 11, 15))
        return Quiz.objects.create(
            course_section=course_section,
            title=f"Quiz-{Quiz.objects.count() + 1}",
            close_at=close_at,
            score_selection_policy=score_selection_policy,
            is_published=True,
        )

    def _create_submission(self, activity, student, score, attempt_number=1):
        return Submission.objects.create(
            activity=activity,
            student=student,
            score=Decimal(str(score)),
            attempt_number=attempt_number,
            status=Submission.SubmissionStatus.GRADED,
        )

    def _create_quiz_attempt(self, quiz, student, score, max_score, is_submitted=True):
        return QuizAttempt.objects.create(
            quiz=quiz,
            student=student,
            score=Decimal(str(score)),
            max_score=Decimal(str(max_score)),
            is_submitted=is_submitted,
            submitted_at=timezone.now() if is_submitted else None,
        )

    def _create_quiz_with_questions(self, course_section, total_points, close_at=None):
        """Create a quiz with questions summing to total_points."""
        quiz = self._create_quiz(course_section, close_at=close_at)
        QuizQuestion.objects.create(
            quiz=quiz,
            question_text="Sample question",
            question_type=QuizQuestion.QuestionType.MULTIPLE_CHOICE,
            points=Decimal(str(total_points)),
        )
        return quiz


class AllComponentsWeightedCorrectlyTest(ComputePeriodGradeTestBase):
    """All components have items, weights sum correctly."""

    def test_all_components_weighted_sum(self):
        student = self._create_student()
        cs = self._create_course_section()
        period = self._create_grading_period()

        # Create weight config: WW=25, PT=50, QA=25
        GradeWeightConfig.objects.create(
            course_section=cs,
            written_works=25,
            performance_tasks=50,
            quarterly_assessment=25,
        )

        # Written Works activity: student scores 80/100
        ww_act = self._create_activity(cs, points=100, component_type="written_works")
        self._create_submission(ww_act, student, 80)

        # Performance Task activity: student scores 90/100
        pt_act = self._create_activity(cs, points=100, component_type="performance_task")
        self._create_submission(pt_act, student, 90)

        # Quarterly Assessment activity: student scores 70/100
        qa_act = self._create_activity(cs, points=100, component_type="quarterly_assessment")
        self._create_submission(qa_act, student, 70)

        # Expected:
        # WW pct = 80/100 * 100 = 80, weight 25
        # PT pct = 90/100 * 100 = 90, weight 50
        # QA pct = 70/100 * 100 = 70, weight 25
        # weighted = (80*25 + 90*50 + 70*25) / 100 = (2000 + 4500 + 1750) / 100 = 82.50
        result = compute_period_grade(student, cs, period)
        self.assertEqual(result, Decimal("82.50"))


class ReProportioningTest(ComputePeriodGradeTestBase):
    """One component has no items, re-proportioning works."""

    def test_qa_missing_reproportioned(self):
        student = self._create_student()
        cs = self._create_course_section()
        period = self._create_grading_period()

        # Weights: WW=25, PT=50, QA=25
        GradeWeightConfig.objects.create(
            course_section=cs,
            written_works=25,
            performance_tasks=50,
            quarterly_assessment=25,
        )

        # Only Written Works and Performance Tasks have items
        ww_act = self._create_activity(cs, points=100, component_type="written_works")
        self._create_submission(ww_act, student, 80)

        pt_act = self._create_activity(cs, points=100, component_type="performance_task")
        self._create_submission(pt_act, student, 90)

        # No QA items -> re-proportion: active_weight_total = 25 + 50 = 75
        # WW weighted = (80 * 25) / 75 = 26.6666...
        # PT weighted = (90 * 50) / 75 = 60
        # Total = 86.67 (rounded)
        result = compute_period_grade(student, cs, period)
        self.assertEqual(result, Decimal("86.67"))

    def test_ww_missing_reproportioned(self):
        student = self._create_student()
        cs = self._create_course_section()
        period = self._create_grading_period()

        # Weights: WW=25, PT=50, QA=25
        GradeWeightConfig.objects.create(
            course_section=cs,
            written_works=25,
            performance_tasks=50,
            quarterly_assessment=25,
        )

        # Only PT and QA have items
        pt_act = self._create_activity(cs, points=100, component_type="performance_task")
        self._create_submission(pt_act, student, 60)

        qa_act = self._create_activity(cs, points=100, component_type="quarterly_assessment")
        self._create_submission(qa_act, student, 80)

        # active_weight_total = 50 + 25 = 75
        # PT weighted = (60 * 50) / 75 = 40
        # QA weighted = (80 * 25) / 75 = 26.6666...
        # Total = 66.67
        result = compute_period_grade(student, cs, period)
        self.assertEqual(result, Decimal("66.67"))


class NoSubmissionsHolisticTest(ComputePeriodGradeTestBase):
    """Student has no submissions (all zeros, holistic grading)."""

    def test_no_submissions_all_zeros(self):
        student = self._create_student()
        cs = self._create_course_section()
        period = self._create_grading_period()

        GradeWeightConfig.objects.create(
            course_section=cs,
            written_works=25,
            performance_tasks=50,
            quarterly_assessment=25,
        )

        # Create activities but no submissions
        self._create_activity(cs, points=100, component_type="written_works")
        self._create_activity(cs, points=100, component_type="performance_task")
        self._create_activity(cs, points=100, component_type="quarterly_assessment")

        # All components have 0 earned out of their possible
        # WW = 0/100 * 100 = 0, PT = 0/100 * 100 = 0, QA = 0/100 * 100 = 0
        # Weighted sum = 0
        result = compute_period_grade(student, cs, period)
        self.assertEqual(result, Decimal("0.00"))

    def test_partial_submissions_missing_counts_zero(self):
        student = self._create_student()
        cs = self._create_course_section()
        period = self._create_grading_period()

        GradeWeightConfig.objects.create(
            course_section=cs,
            written_works=25,
            performance_tasks=50,
            quarterly_assessment=25,
        )

        # Two WW activities, student only submits one
        ww1 = self._create_activity(cs, points=50, component_type="written_works")
        self._create_submission(ww1, student, 50)  # Perfect score

        ww2 = self._create_activity(cs, points=50, component_type="written_works")
        # No submission for ww2 -> earned = 0

        # WW pct = (50 + 0) / (50 + 50) * 100 = 50
        # PT and QA have no items -> re-proportion
        # active_weight_total = 25
        # weighted = (50 * 25) / 25 = 50
        result = compute_period_grade(student, cs, period)
        self.assertEqual(result, Decimal("50.00"))


class MonthlyExamAsWrittenWorksTest(ComputePeriodGradeTestBase):
    """Activity with is_exam=True and exam_type='monthly' counts as Written Works."""

    def test_monthly_exam_in_written_works(self):
        student = self._create_student()
        cs = self._create_course_section()
        period = self._create_grading_period()

        GradeWeightConfig.objects.create(
            course_section=cs,
            written_works=25,
            performance_tasks=50,
            quarterly_assessment=25,
        )

        # Monthly exam should go to Written Works
        monthly_exam = self._create_activity(
            cs, points=100, is_exam=True, exam_type="monthly"
        )
        self._create_submission(monthly_exam, student, 80)

        # A regular PT activity
        pt_act = self._create_activity(cs, points=100, component_type="performance_task")
        self._create_submission(pt_act, student, 90)

        # A QA activity
        qa_act = self._create_activity(cs, points=100, component_type="quarterly_assessment")
        self._create_submission(qa_act, student, 70)

        # WW = 80/100 * 100 = 80 (from monthly exam), weight 25
        # PT = 90/100 * 100 = 90, weight 50
        # QA = 70/100 * 100 = 70, weight 25
        # weighted = (80*25 + 90*50 + 70*25) / 100 = 82.50
        result = compute_period_grade(student, cs, period)
        self.assertEqual(result, Decimal("82.50"))


class QuarterlyExamAsQuarterlyAssessmentTest(ComputePeriodGradeTestBase):
    """Activity with is_exam=True and exam_type='quarterly' counts as Quarterly Assessment."""

    def test_quarterly_exam_in_qa(self):
        student = self._create_student()
        cs = self._create_course_section()
        period = self._create_grading_period()

        GradeWeightConfig.objects.create(
            course_section=cs,
            written_works=25,
            performance_tasks=50,
            quarterly_assessment=25,
        )

        # Written Works activity
        ww_act = self._create_activity(cs, points=100, component_type="written_works")
        self._create_submission(ww_act, student, 80)

        # Performance Task
        pt_act = self._create_activity(cs, points=100, component_type="performance_task")
        self._create_submission(pt_act, student, 90)

        # Quarterly exam should go to QA
        q_exam = self._create_activity(
            cs, points=100, is_exam=True, exam_type="quarterly"
        )
        self._create_submission(q_exam, student, 70)

        # Same calculation as the all-components test
        # WW=80, PT=90, QA=70 -> weighted = 82.50
        result = compute_period_grade(student, cs, period)
        self.assertEqual(result, Decimal("82.50"))


class ComponentTypeNoneAsPerformanceTaskTest(ComputePeriodGradeTestBase):
    """Activity with component_type=None counts as Performance Task."""

    def test_none_component_goes_to_pt(self):
        student = self._create_student()
        cs = self._create_course_section()
        period = self._create_grading_period()

        GradeWeightConfig.objects.create(
            course_section=cs,
            written_works=25,
            performance_tasks=50,
            quarterly_assessment=25,
        )

        # Activity with no component_type -> should go to Performance Task
        act_no_component = self._create_activity(cs, points=100, component_type=None)
        self._create_submission(act_no_component, student, 90)

        # WW and QA are missing -> re-proportion
        # PT pct = 90/100 * 100 = 90
        # active_weight_total = 50
        # weighted = (90 * 50) / 50 = 90
        result = compute_period_grade(student, cs, period)
        self.assertEqual(result, Decimal("90.00"))


class QuizAlwaysWrittenWorksTest(ComputePeriodGradeTestBase):
    """Quiz always counts as Written Works, regardless of any field."""

    def test_quiz_in_written_works(self):
        student = self._create_student()
        cs = self._create_course_section()
        period = self._create_grading_period()

        GradeWeightConfig.objects.create(
            course_section=cs,
            written_works=25,
            performance_tasks=50,
            quarterly_assessment=25,
        )

        # Quiz should always go to Written Works
        quiz = self._create_quiz_with_questions(cs, total_points=50)
        self._create_quiz_attempt(quiz, student, score=40, max_score=50)

        # PT activity
        pt_act = self._create_activity(cs, points=100, component_type="performance_task")
        self._create_submission(pt_act, student, 90)

        # QA activity
        qa_act = self._create_activity(cs, points=100, component_type="quarterly_assessment")
        self._create_submission(qa_act, student, 70)

        # WW = 40/50 * 100 = 80, weight 25
        # PT = 90/100 * 100 = 90, weight 50
        # QA = 70/100 * 100 = 70, weight 25
        # weighted = (80*25 + 90*50 + 70*25) / 100 = 82.50
        result = compute_period_grade(student, cs, period)
        self.assertEqual(result, Decimal("82.50"))


class NoItemsReturnsNoneTest(ComputePeriodGradeTestBase):
    """Returns None when no items exist at all."""

    def test_no_activities_no_quizzes(self):
        student = self._create_student()
        cs = self._create_course_section()
        period = self._create_grading_period()

        GradeWeightConfig.objects.create(
            course_section=cs,
            written_works=25,
            performance_tasks=50,
            quarterly_assessment=25,
        )

        # No activities, no quizzes
        result = compute_period_grade(student, cs, period)
        self.assertIsNone(result)

    def test_unpublished_activities_not_counted(self):
        student = self._create_student()
        cs = self._create_course_section()
        period = self._create_grading_period()

        GradeWeightConfig.objects.create(
            course_section=cs,
            written_works=25,
            performance_tasks=50,
            quarterly_assessment=25,
        )

        # Create an unpublished activity (is_published=False)
        act = self._create_activity(cs, points=100, component_type="written_works")
        act.is_published = False
        act.save()
        self._create_submission(act, student, 80)

        # Only unpublished items -> should be None
        result = compute_period_grade(student, cs, period)
        self.assertIsNone(result)

    def test_activities_outside_period_not_counted(self):
        student = self._create_student()
        cs = self._create_course_section()
        period = self._create_grading_period(
            start_date=date(2024, 10, 1),
            end_date=date(2024, 12, 31),
        )

        GradeWeightConfig.objects.create(
            course_section=cs,
            written_works=25,
            performance_tasks=50,
            quarterly_assessment=25,
        )

        # Activity with deadline outside the grading period
        outside_act = self._create_activity(
            cs, points=100,
            component_type="written_works",
            deadline=_make_datetime(date(2025, 2, 1)),
        )
        self._create_submission(outside_act, student, 80)

        result = compute_period_grade(student, cs, period)
        self.assertIsNone(result)


class ScoreSelectionPolicyTest(ComputePeriodGradeTestBase):
    """Test that score_selection_policy (highest/latest) is respected."""

    def test_highest_policy_picks_highest_score(self):
        student = self._create_student()
        cs = self._create_course_section()
        period = self._create_grading_period()

        GradeWeightConfig.objects.create(
            course_section=cs,
            written_works=25,
            performance_tasks=50,
            quarterly_assessment=25,
        )

        # Activity with highest policy (default)
        act = self._create_activity(
            cs, points=100,
            component_type="performance_task",
            score_selection_policy=Activity.ScorePolicy.HIGHEST,
        )
        # Create multiple submissions - highest should be picked
        self._create_submission(act, student, 60, attempt_number=1)
        self._create_submission(act, student, 80, attempt_number=2)
        self._create_submission(act, student, 70, attempt_number=3)

        # Only PT has items -> weight 50, active_weight_total = 50
        # PT pct = 80/100 * 100 = 80
        # weighted = (80 * 50) / 50 = 80
        result = compute_period_grade(student, cs, period)
        self.assertEqual(result, Decimal("80.00"))

    def test_latest_policy_picks_latest_attempt(self):
        student = self._create_student()
        cs = self._create_course_section()
        period = self._create_grading_period()

        GradeWeightConfig.objects.create(
            course_section=cs,
            written_works=25,
            performance_tasks=50,
            quarterly_assessment=25,
        )

        # Activity with latest policy
        act = self._create_activity(
            cs, points=100,
            component_type="performance_task",
            score_selection_policy=Activity.ScorePolicy.LATEST,
        )
        # Latest submission is attempt 3 with score 70
        self._create_submission(act, student, 60, attempt_number=1)
        self._create_submission(act, student, 80, attempt_number=2)
        self._create_submission(act, student, 70, attempt_number=3)

        # PT pct = 70/100 * 100 = 70
        # weighted = (70 * 50) / 50 = 70
        result = compute_period_grade(student, cs, period)
        self.assertEqual(result, Decimal("70.00"))


class QuizScoreSelectionPolicyTest(ComputePeriodGradeTestBase):
    """Test quiz score_selection_policy."""

    def test_quiz_highest_policy(self):
        student = self._create_student()
        cs = self._create_course_section()
        period = self._create_grading_period()

        GradeWeightConfig.objects.create(
            course_section=cs,
            written_works=25,
            performance_tasks=50,
            quarterly_assessment=25,
        )

        quiz = self._create_quiz(
            cs,
            score_selection_policy=Quiz.ScorePolicy.HIGHEST,
        )
        QuizQuestion.objects.create(
            quiz=quiz,
            question_text="Q1",
            question_type=QuizQuestion.QuestionType.MULTIPLE_CHOICE,
            points=Decimal("100"),
        )

        # Multiple attempts
        QuizAttempt.objects.create(
            quiz=quiz, student=student, attempt_number=1,
            score=Decimal("60"), max_score=Decimal("100"),
            is_submitted=True, submitted_at=timezone.now(),
        )
        QuizAttempt.objects.create(
            quiz=quiz, student=student, attempt_number=2,
            score=Decimal("80"), max_score=Decimal("100"),
            is_submitted=True, submitted_at=timezone.now(),
        )
        QuizAttempt.objects.create(
            quiz=quiz, student=student, attempt_number=3,
            score=Decimal("70"), max_score=Decimal("100"),
            is_submitted=True, submitted_at=timezone.now(),
        )

        # WW = 80/100 * 100 = 80 (highest picked)
        # Only WW has items -> active_weight_total = 25
        # weighted = (80 * 25) / 25 = 80
        result = compute_period_grade(student, cs, period)
        self.assertEqual(result, Decimal("80.00"))


class MultipleItemsPerComponentTest(ComputePeriodGradeTestBase):
    """Test multiple items in a single component are summed correctly."""

    def test_multiple_ww_items(self):
        student = self._create_student()
        cs = self._create_course_section()
        period = self._create_grading_period()

        GradeWeightConfig.objects.create(
            course_section=cs,
            written_works=25,
            performance_tasks=50,
            quarterly_assessment=25,
        )

        # Two Written Works activities
        ww1 = self._create_activity(cs, points=50, component_type="written_works")
        self._create_submission(ww1, student, 40)

        ww2 = self._create_activity(cs, points=50, component_type="written_works")
        self._create_submission(ww2, student, 30)

        # One quiz in Written Works too
        quiz = self._create_quiz_with_questions(cs, total_points=20)
        self._create_quiz_attempt(quiz, student, score=15, max_score=20)

        # WW total earned = 40 + 30 + 15 = 85
        # WW total possible = 50 + 50 + 20 = 120
        # WW pct = 85/120 * 100 = 70.8333...
        # Only WW -> weighted = (70.8333... * 25) / 25 = 70.83
        result = compute_period_grade(student, cs, period)
        self.assertEqual(result, Decimal("70.83"))