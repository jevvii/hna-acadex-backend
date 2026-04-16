from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Activity,
    ActivityReminder,
    Course,
    CourseSection,
    Enrollment,
    Notification,
    Quiz,
    Section,
    User,
)
from core.tasks import process_reminders


class ReminderTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = self._create_user("student@example.com", User.Role.STUDENT)
        self.teacher = self._create_user("teacher@example.com", User.Role.TEACHER)

        section = Section.objects.create(
            name="Section A",
            grade_level=User.GradeLevel.G7,
            school_year="2026-2027",
        )
        course = Course.objects.create(
            code="MATH7",
            title="Mathematics 7",
            school_year="2026-2027",
        )
        self.course_section = CourseSection.objects.create(
            course=course,
            section=section,
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

    def test_create_activity_reminder_within_now_and_deadline(self):
        self.client.force_authenticate(self.student)
        deadline = timezone.now() + timedelta(days=1)
        activity = Activity.objects.create(
            course_section=self.course_section,
            title="Worksheet 1",
            deadline=deadline,
            points=100,
            is_published=True,
        )
        reminder_dt = timezone.now() + timedelta(hours=2)

        response = self.client.post(
            reverse("reminders-list"),
            {
                "reminder_type": "activity",
                "activity_id": str(activity.id),
                "reminder_datetime": reminder_dt.isoformat(),
                "offset_minutes": 120,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(ActivityReminder.objects.filter(user=self.student, activity=activity).count(), 1)
        reminder = ActivityReminder.objects.get(user=self.student, activity=activity)
        self.assertGreaterEqual(reminder.offset_minutes, 0)

    def test_create_reminder_recomputes_offset_minutes_for_accuracy(self):
        self.client.force_authenticate(self.student)
        activity_deadline = timezone.now() + timedelta(hours=2)
        quiz_deadline = timezone.now() + timedelta(hours=3)
        activity = Activity.objects.create(
            course_section=self.course_section,
            title="Offset Activity",
            deadline=activity_deadline,
            points=100,
            is_published=True,
        )
        quiz = Quiz.objects.create(
            course_section=self.course_section,
            title="Offset Quiz",
            close_at=quiz_deadline,
            is_published=True,
        )
        activity_reminder_dt = activity_deadline - timedelta(minutes=15)
        quiz_reminder_dt = quiz_deadline - timedelta(minutes=60)

        activity_response = self.client.post(
            reverse("reminders-list"),
            {
                "reminder_type": "activity",
                "activity_id": str(activity.id),
                "reminder_datetime": activity_reminder_dt.isoformat(),
                "offset_minutes": 9999,  # intentionally wrong; server should recompute
            },
            format="json",
        )
        quiz_response = self.client.post(
            reverse("reminders-list"),
            {
                "reminder_type": "quiz",
                "quiz_id": str(quiz.id),
                "reminder_datetime": quiz_reminder_dt.isoformat(),
                "offset_minutes": 9999,  # intentionally wrong; server should recompute
            },
            format="json",
        )

        self.assertEqual(activity_response.status_code, 201)
        self.assertEqual(quiz_response.status_code, 201)

        activity_reminder = ActivityReminder.objects.get(user=self.student, activity=activity)
        quiz_reminder = ActivityReminder.objects.get(user=self.student, quiz=quiz)

        self.assertEqual(activity_reminder.offset_minutes, 15)
        self.assertEqual(quiz_reminder.offset_minutes, 60)

    def test_create_reminder_after_deadline_is_rejected(self):
        self.client.force_authenticate(self.student)
        deadline = timezone.now() + timedelta(hours=3)
        activity = Activity.objects.create(
            course_section=self.course_section,
            title="Worksheet 2",
            deadline=deadline,
            points=100,
            is_published=True,
        )
        reminder_dt = deadline + timedelta(minutes=1)

        response = self.client.post(
            reverse("reminders-list"),
            {
                "reminder_type": "activity",
                "activity_id": str(activity.id),
                "reminder_datetime": reminder_dt.isoformat(),
                "offset_minutes": 0,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("reminder_datetime", response.json())

    def test_create_reminder_when_deadline_passed_is_rejected(self):
        self.client.force_authenticate(self.student)
        past_deadline = timezone.now() - timedelta(minutes=30)
        quiz = Quiz.objects.create(
            course_section=self.course_section,
            title="Past Quiz",
            close_at=past_deadline,
            is_published=True,
        )

        response = self.client.post(
            reverse("reminders-list"),
            {
                "reminder_type": "quiz",
                "quiz_id": str(quiz.id),
                "reminder_datetime": timezone.now().isoformat(),
                "offset_minutes": 0,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("reminder_datetime", response.json())

    def test_reminder_list_excludes_past_entries(self):
        self.client.force_authenticate(self.student)
        now = timezone.now()
        activity = Activity.objects.create(
            course_section=self.course_section,
            title="List Filter Activity",
            deadline=now + timedelta(days=1),
            points=100,
            is_published=True,
        )
        future_reminder = ActivityReminder.objects.create(
            user=self.student,
            reminder_type=ActivityReminder.ReminderType.ACTIVITY,
            activity=activity,
            reminder_datetime=now + timedelta(minutes=20),
            offset_minutes=20,
            notification_sent=False,
        )
        ActivityReminder.objects.create(
            user=self.student,
            reminder_type=ActivityReminder.ReminderType.ACTIVITY,
            activity=activity,
            reminder_datetime=now - timedelta(minutes=1),
            offset_minutes=1,
            notification_sent=True,
        )

        response = self.client.get(f"{reverse('reminders-list')}?activity_id={activity.id}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        items = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
        returned_ids = {item["id"] for item in items}
        self.assertEqual(returned_ids, {str(future_reminder.id)})

    def test_listing_reminders_processes_due_reminders_and_creates_notification(self):
        self.client.force_authenticate(self.student)
        now = timezone.now()
        activity = Activity.objects.create(
            course_section=self.course_section,
            title="Due Reminder Activity",
            deadline=now + timedelta(hours=2),
            points=100,
            is_published=True,
        )
        due_reminder = ActivityReminder.objects.create(
            user=self.student,
            reminder_type=ActivityReminder.ReminderType.ACTIVITY,
            activity=activity,
            reminder_datetime=now - timedelta(minutes=1),
            offset_minutes=1,
            notification_sent=False,
        )

        response = self.client.get(f"{reverse('reminders-list')}?activity_id={activity.id}")
        self.assertEqual(response.status_code, 200)

        due_reminder.refresh_from_db()
        self.assertTrue(due_reminder.notification_sent)

        notification = Notification.objects.filter(
            recipient=self.student,
            activity=activity,
            type=Notification.NotificationType.NEW_ACTIVITY,
        ).first()
        self.assertIsNotNone(notification)
        self.assertTrue(notification.title.startswith("Assignment Reminder:"))

        payload = response.json()
        items = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
        returned_ids = {item["id"] for item in items}
        self.assertNotIn(str(due_reminder.id), returned_ids)

    def test_process_reminders_creates_in_app_notification_and_marks_sent(self):
        now = timezone.now()
        activity = Activity.objects.create(
            course_section=self.course_section,
            title="Reminder Activity",
            deadline=now + timedelta(days=1),
            points=100,
            is_published=True,
        )
        quiz = Quiz.objects.create(
            course_section=self.course_section,
            title="Reminder Quiz",
            close_at=now + timedelta(days=1),
            is_published=True,
        )
        activity_reminder = ActivityReminder.objects.create(
            user=self.student,
            reminder_type=ActivityReminder.ReminderType.ACTIVITY,
            activity=activity,
            reminder_datetime=now - timedelta(minutes=2),
            offset_minutes=2,
            notification_sent=False,
        )
        quiz_reminder = ActivityReminder.objects.create(
            user=self.student,
            reminder_type=ActivityReminder.ReminderType.QUIZ,
            quiz=quiz,
            reminder_datetime=now - timedelta(minutes=1),
            offset_minutes=1,
            notification_sent=False,
        )

        process_reminders()

        activity_reminder.refresh_from_db()
        quiz_reminder.refresh_from_db()

        self.assertTrue(activity_reminder.notification_sent)
        self.assertTrue(quiz_reminder.notification_sent)

        activity_notification = Notification.objects.filter(
            recipient=self.student,
            activity=activity,
            type=Notification.NotificationType.NEW_ACTIVITY,
        ).first()
        quiz_notification = Notification.objects.filter(
            recipient=self.student,
            quiz=quiz,
            type=Notification.NotificationType.NEW_QUIZ,
        ).first()

        self.assertIsNotNone(activity_notification)
        self.assertIsNotNone(quiz_notification)
        self.assertTrue(activity_notification.title.startswith("Assignment Reminder:"))
        self.assertTrue(quiz_notification.title.startswith("Quiz Reminder:"))
