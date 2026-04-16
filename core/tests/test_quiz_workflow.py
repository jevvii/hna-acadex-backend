from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import (
    Activity,
    Course,
    CourseSection,
    Enrollment,
    Notification,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizChoice,
    QuizQuestion,
    Section,
    User,
)


class QuizWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.teacher = self._create_user("teacher@example.com", User.Role.TEACHER)
        self.student = self._create_user("student@example.com", User.Role.STUDENT)

        self.section = Section.objects.create(
            name="Section A",
            grade_level=User.GradeLevel.G10,
            school_year="2026-2027",
        )
        self.course = Course.objects.create(
            code="MATH10",
            title="Mathematics 10",
            school_year="2026-2027",
        )
        self.course_section = CourseSection.objects.create(
            course=self.course,
            section=self.section,
            teacher=self.teacher,
            school_year="2026-2027",
        )
        Enrollment.objects.create(
            student=self.student,
            course_section=self.course_section,
            is_active=True,
        )

    def _create_user(self, email: str, role: str) -> User:
        return User.objects.create_user(
            email=email,
            password="testpass123",
            first_name="Test",
            last_name=role.title(),
            role=role,
            status=User.Status.ACTIVE,
            requires_setup=False,
        )

    def _response_items(self, response):
        payload = response.json()
        if isinstance(payload, dict) and "results" in payload:
            return payload["results"]
        return payload

    def test_quick_create_defaults_to_unpublished(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.post(
            reverse("quiz-quick-create"),
            {
                "course_section_id": str(self.course_section.id),
                "title": "Draft Quiz",
                "attempt_limit": 1,
                "questions": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        quiz_id = response.json()["quiz"]["id"]
        quiz = Quiz.objects.get(id=quiz_id)
        self.assertFalse(quiz.is_published)

    def test_student_cannot_take_unpublished_quiz(self):
        quiz = Quiz.objects.create(
            course_section=self.course_section,
            title="Hidden Quiz",
            attempt_limit=1,
            is_published=False,
        )
        self.client.force_authenticate(self.student)
        response = self.client.get(reverse("quiz-take", kwargs={"pk": quiz.id}))
        self.assertEqual(response.status_code, 403)

    def test_multi_select_auto_grades_with_partial_credit_and_notifies(self):
        quiz = Quiz.objects.create(
            course_section=self.course_section,
            title="Multi Select Quiz",
            attempt_limit=1,
            is_published=True,
        )
        question = QuizQuestion.objects.create(
            quiz=quiz,
            question_text="Pick all prime numbers",
            question_type=QuizQuestion.QuestionType.MULTI_SELECT,
            points=4,
            sort_order=0,
        )
        c1 = QuizChoice.objects.create(question=question, choice_text="2", is_correct=True, sort_order=0)
        QuizChoice.objects.create(question=question, choice_text="3", is_correct=True, sort_order=1)
        QuizChoice.objects.create(question=question, choice_text="4", is_correct=False, sort_order=2)

        self.client.force_authenticate(self.student)
        response = self.client.post(
            reverse("quiz-submit-attempt", kwargs={"pk": quiz.id}),
            {
                "answers": [
                    {
                        "question_id": str(question.id),
                        "selected_choice_ids": [str(c1.id)],
                    }
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        attempt = QuizAttempt.objects.get(quiz=quiz, student=self.student, is_submitted=True)
        answer = QuizAnswer.objects.get(attempt=attempt, question=question)

        self.assertFalse(attempt.pending_manual_grading)
        self.assertEqual(float(attempt.score), 2.0)
        self.assertFalse(answer.needs_manual_grading)
        self.assertEqual(float(answer.points_awarded), 2.0)

        self.assertTrue(
            Notification.objects.filter(
                recipient=self.teacher,
                quiz=quiz,
                type=Notification.NotificationType.NEW_QUIZ,
                title__startswith="Quiz Submission:",
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.student,
                quiz=quiz,
                type=Notification.NotificationType.GRADE_RELEASED,
                title__startswith="Quiz Graded:",
            ).exists()
        )

    def test_multi_select_with_mixed_correct_and_incorrect_choices_gets_partial_credit(self):
        quiz = Quiz.objects.create(
            course_section=self.course_section,
            title="Mixed Multi Select Quiz",
            attempt_limit=1,
            is_published=True,
        )
        question = QuizQuestion.objects.create(
            quiz=quiz,
            question_text="Select all valid statements",
            question_type=QuizQuestion.QuestionType.MULTI_SELECT,
            points=6,
            sort_order=0,
        )
        correct_a = QuizChoice.objects.create(question=question, choice_text="A", is_correct=True, sort_order=0)
        QuizChoice.objects.create(question=question, choice_text="B", is_correct=True, sort_order=1)
        incorrect_c = QuizChoice.objects.create(question=question, choice_text="C", is_correct=False, sort_order=2)
        QuizChoice.objects.create(question=question, choice_text="D", is_correct=False, sort_order=3)

        self.client.force_authenticate(self.student)
        response = self.client.post(
            reverse("quiz-submit-attempt", kwargs={"pk": quiz.id}),
            {
                "answers": [
                    {
                        "question_id": str(question.id),
                        "selected_choice_ids": [str(correct_a.id), str(incorrect_c.id)],
                    }
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        attempt = QuizAttempt.objects.get(quiz=quiz, student=self.student, is_submitted=True)
        answer = QuizAnswer.objects.get(attempt=attempt, question=question)

        self.assertGreater(float(attempt.score), 0.0)
        self.assertGreater(float(answer.points_awarded), 0.0)
        self.assertLess(float(answer.points_awarded), float(question.points))

    def test_activity_submission_notifies_teacher(self):
        activity = Activity.objects.create(
            course_section=self.course_section,
            title="Worksheet 1",
            points=100,
            is_published=True,
            allowed_file_types=["text"],
            attempt_limit=1,
        )

        self.client.force_authenticate(self.student)
        response = self.client.post(
            reverse("activity-submit", kwargs={"pk": activity.id}),
            {"text_content": "My answer"},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.teacher,
                activity=activity,
                type=Notification.NotificationType.NEW_ACTIVITY,
                title__startswith="Submission Received:",
            ).exists()
        )

    def test_teacher_notification_list_hides_activity_and_quiz_deadline_creation_events(self):
        Notification.objects.create(
            recipient=self.teacher,
            type=Notification.NotificationType.NEW_ACTIVITY,
            title="Today: Weekly Worksheet",
            body="Deadline • 9:00 AM",
            course_section=self.course_section,
        )
        Notification.objects.create(
            recipient=self.teacher,
            type=Notification.NotificationType.NEW_QUIZ,
            title="Quiz deadline today: Unit Test",
            body="Due at 5:00 PM",
            course_section=self.course_section,
        )
        Notification.objects.create(
            recipient=self.teacher,
            type=Notification.NotificationType.NEW_QUIZ,
            title="Quiz Submission: Unit Test",
            body="Student submitted attempt #1.",
            course_section=self.course_section,
        )

        self.client.force_authenticate(self.teacher)
        response = self.client.get(reverse("notifications-list"))
        self.assertEqual(response.status_code, 200)
        titles = {item["title"] for item in self._response_items(response)}
        self.assertNotIn("Today: Weekly Worksheet", titles)
        self.assertNotIn("Quiz deadline today: Unit Test", titles)
        self.assertIn("Quiz Submission: Unit Test", titles)
