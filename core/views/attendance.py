"""
Attendance-related views.
"""
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import (
    AttendanceRecord,
    CourseSection,
    Enrollment,
    MeetingSession,
    User,
)
from core.serializers import (
    AttendanceRecordSerializer,
    MeetingSessionSerializer,
)
from core.views.common import _recompute_course_section_grades


class AttendanceOverviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _resolve_course_section(self, request, pk):
        course_section = CourseSection.objects.filter(id=pk).first()
        if not course_section:
            return None, Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role == User.Role.STUDENT:
            allowed = Enrollment.objects.filter(course_section=course_section, student=request.user, is_active=True).exists()
            if not allowed:
                return None, Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        elif request.user.role == User.Role.TEACHER:
            if course_section.teacher_id != request.user.id:
                return None, Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        elif request.user.role != User.Role.ADMIN:
            return None, Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        return course_section, None

    def _attendance_percentage(self, present_count, absent_count, late_count, excused_count):
        total = present_count + absent_count + late_count + excused_count
        if total <= 0:
            return 0
        score = present_count + excused_count + (late_count * 0.5)
        return int(round((score / total) * 100))

    def get(self, request, pk):
        course_section, denied = self._resolve_course_section(request, pk)
        if denied:
            return denied

        sessions = list(MeetingSession.objects.filter(course_section=course_section).order_by("-date", "-created_at"))
        session_ids = [s.id for s in sessions]
        records_qs = AttendanceRecord.objects.filter(meeting_id__in=session_ids).select_related("student", "meeting")
        records = list(records_qs)

        enrollments = Enrollment.objects.filter(course_section=course_section, is_active=True).select_related("student")
        students = [e.student for e in enrollments if e.student and e.student.role == User.Role.STUDENT]

        if request.user.role == User.Role.STUDENT:
            my_records = [r for r in records if r.student_id == request.user.id]
            present_count = sum(1 for r in my_records if r.status == AttendanceRecord.AttendanceStatus.PRESENT)
            absent_count = sum(1 for r in my_records if r.status == AttendanceRecord.AttendanceStatus.ABSENT)
            late_count = sum(1 for r in my_records if r.status == AttendanceRecord.AttendanceStatus.LATE)
            excused_count = sum(1 for r in my_records if r.status == AttendanceRecord.AttendanceStatus.EXCUSED)
            total_sessions = len(sessions)
            summary = {
                "total_sessions": total_sessions,
                "present_count": present_count,
                "absent_count": absent_count,
                "late_count": late_count,
                "excused_count": excused_count,
                "attendance_percentage": self._attendance_percentage(
                    present_count, absent_count, late_count, excused_count
                ),
            }
            history = []
            by_meeting = {r.meeting_id: r for r in my_records}
            for s in sessions:
                rec = by_meeting.get(s.id)
                history.append(
                    {
                        "meeting_id": str(s.id),
                        "date": s.date,
                        "title": s.title,
                        "status": rec.status if rec else None,  # None means unmarked/not recorded
                        "remarks": rec.remarks if rec else None,
                    }
                )
            return Response(
                {
                    "course_section_id": str(course_section.id),
                    "sessions": MeetingSessionSerializer(sessions, many=True).data,
                    "summary": summary,
                    "history": history,
                    "updated_at": AttendanceOverviewView._get_current_time(),
                }
            )

        student_rows = []
        for student in students:
            s_records = [r for r in records if r.student_id == student.id]
            present_count = sum(1 for r in s_records if r.status == AttendanceRecord.AttendanceStatus.PRESENT)
            absent_count = sum(1 for r in s_records if r.status == AttendanceRecord.AttendanceStatus.ABSENT)
            late_count = sum(1 for r in s_records if r.status == AttendanceRecord.AttendanceStatus.LATE)
            excused_count = sum(1 for r in s_records if r.status == AttendanceRecord.AttendanceStatus.EXCUSED)

            # Get avatar URL (handles both avatar_url field and avatar FileField)
            avatar_url = None
            if student.avatar_url:
                avatar_url = student.avatar_url
            elif student.avatar:
                avatar_url = request.build_absolute_uri(student.avatar.url)

            student_rows.append(
                {
                    "student_id": str(student.id),
                    "student_name": student.full_name,
                    "student_email": student.email,
                    "avatar_url": avatar_url,
                    "total_sessions": len(sessions),
                    "present_count": present_count,
                    "absent_count": absent_count,
                    "late_count": late_count,
                    "excused_count": excused_count,
                    "attendance_percentage": self._attendance_percentage(
                        present_count, absent_count, late_count, excused_count
                    ),
                }
            )

        return Response(
            {
                "course_section_id": str(course_section.id),
                "sessions": MeetingSessionSerializer(sessions, many=True).data,
                "students": student_rows,
                "records": AttendanceRecordSerializer(records, many=True).data,
                "updated_at": AttendanceOverviewView._get_current_time(),
            }
        )

    @staticmethod
    def _get_current_time():
        from django.utils import timezone
        return timezone.now()


class AttendanceSessionCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        course_section = CourseSection.objects.filter(id=pk).first()
        if not course_section:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role == User.Role.TEACHER and course_section.teacher_id != request.user.id:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role not in [User.Role.TEACHER, User.Role.ADMIN]:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        date = request.data.get("date")
        title = request.data.get("title")
        if not date or not title:
            return Response({"detail": "date and title are required."}, status=status.HTTP_400_BAD_REQUEST)

        session = MeetingSession.objects.create(
            course_section=course_section,
            date=date,
            title=title,
            created_by=request.user,
        )
        # Do NOT create attendance records automatically - let them be created
        # when the teacher marks each student. Unmarked students will show as "None".
        _recompute_course_section_grades(course_section)
        return Response(MeetingSessionSerializer(session).data, status=status.HTTP_201_CREATED)


class AttendanceSessionDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        session = MeetingSession.objects.select_related("course_section").filter(id=pk).first()
        if not session:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role == User.Role.TEACHER and session.course_section.teacher_id != request.user.id:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role not in [User.Role.TEACHER, User.Role.ADMIN]:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        course_section = session.course_section
        session.delete()
        _recompute_course_section_grades(course_section)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AttendanceRecordBulkUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        session = MeetingSession.objects.select_related("course_section").filter(id=pk).first()
        if not session:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role == User.Role.TEACHER and session.course_section.teacher_id != request.user.id:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role not in [User.Role.TEACHER, User.Role.ADMIN]:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        bulk_action = request.data.get("bulk_action")
        if bulk_action == "mark_all_present":
            AttendanceRecord.objects.filter(meeting=session).update(
                status=AttendanceRecord.AttendanceStatus.PRESENT,
                marked_by=request.user,
                updated_at=AttendanceRecordBulkUpdateView._get_current_time(),
            )
            _recompute_course_section_grades(session.course_section)
            return Response({"ok": True})
        if bulk_action == "clear_all":
            AttendanceRecord.objects.filter(meeting=session).update(
                status=AttendanceRecord.AttendanceStatus.ABSENT,
                remarks=None,
                marked_by=request.user,
                updated_at=AttendanceRecordBulkUpdateView._get_current_time(),
            )
            _recompute_course_section_grades(session.course_section)
            return Response({"ok": True})

        records = request.data.get("records") or []
        if not isinstance(records, list):
            return Response({"detail": "records must be a list."}, status=status.HTTP_400_BAD_REQUEST)

        valid_statuses = set(AttendanceRecord.AttendanceStatus.values)
        for row in records:
            student_id = row.get("student_id")
            status_value = row.get("status")
            if not student_id or status_value not in valid_statuses:
                continue
            AttendanceRecord.objects.update_or_create(
                meeting=session,
                student_id=student_id,
                defaults={
                    "status": status_value,
                    "remarks": row.get("remarks"),
                    "marked_by": request.user,
                },
            )
        _recompute_course_section_grades(session.course_section)
        return Response({"ok": True})

    @staticmethod
    def _get_current_time():
        from django.utils import timezone
        return timezone.now()


__all__ = [
    'AttendanceOverviewView',
    'AttendanceSessionCreateView',
    'AttendanceSessionDeleteView',
    'AttendanceRecordBulkUpdateView',
]