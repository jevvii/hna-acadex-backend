from datetime import datetime, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import CalendarEvent, Course, CourseSection, Enrollment, Notification, Section, User


class CalendarEventApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = self._create_user("student1@example.com", User.Role.STUDENT)
        self.other_student = self._create_user("student2@example.com", User.Role.STUDENT)
        self.teacher = self._create_user("teacher@example.com", User.Role.TEACHER)

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

    def test_create_event_creates_notification_for_creator(self):
        self.client.force_authenticate(self.student)
        response = self.client.post(
            reverse("calendar-events-list"),
            {
                "title": "Study Group",
                "description": "Review session for oral communication",
                "event_type": CalendarEvent.EventType.PERSONAL,
                "start_at": (timezone.now() + timedelta(days=1)).isoformat(),
                "all_day": False,
                "is_personal": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        notification = Notification.objects.filter(recipient=self.student).first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.type, Notification.NotificationType.SYSTEM)
        self.assertEqual(notification.title, "Calendar: Study Group")

    def test_end_date_filter_includes_events_on_end_day(self):
        self.client.force_authenticate(self.student)
        event_dt = timezone.make_aware(datetime(2026, 3, 31, 15, 0, 0))
        event = CalendarEvent.objects.create(
            creator=self.student,
            title="Quarterly Planning",
            event_type=CalendarEvent.EventType.PERSONAL,
            start_at=event_dt,
            all_day=False,
            is_personal=True,
        )

        response = self.client.get(
            f"{reverse('calendar-events-list')}?start=2026-03-01&end=2026-03-31"
        )
        self.assertEqual(response.status_code, 200)
        item_ids = {item["id"] for item in self._response_items(response)}
        self.assertIn(str(event.id), item_ids)

    def test_student_does_not_see_shared_events_from_unenrolled_sections(self):
        section = Section.objects.create(
            name="STEM-A",
            grade_level=User.GradeLevel.G11,
            strand=User.Strand.STEM,
            school_year="2026-2027",
        )
        course = Course.objects.create(
            code="ORALCOM",
            title="Oral Communication in Context",
            school_year="2026-2027",
            semester="1st",
        )
        course_section = CourseSection.objects.create(
            course=course,
            section=section,
            teacher=self.teacher,
            school_year="2026-2027",
            semester="1st",
        )
        Enrollment.objects.create(student=self.other_student, course_section=course_section)

        hidden_event = CalendarEvent.objects.create(
            creator=self.other_student,
            course_section=course_section,
            title="Private Section Event",
            event_type=CalendarEvent.EventType.SCHOOL_EVENT,
            start_at=timezone.now(),
            all_day=False,
            is_personal=False,
        )
        visible_event = CalendarEvent.objects.create(
            creator=self.student,
            title="My Personal Event",
            event_type=CalendarEvent.EventType.PERSONAL,
            start_at=timezone.now(),
            all_day=False,
            is_personal=True,
        )

        self.client.force_authenticate(self.student)
        response = self.client.get(reverse("calendar-events-list"))
        self.assertEqual(response.status_code, 200)
        item_ids = {item["id"] for item in self._response_items(response)}
        self.assertIn(str(visible_event.id), item_ids)
        self.assertNotIn(str(hidden_event.id), item_ids)
