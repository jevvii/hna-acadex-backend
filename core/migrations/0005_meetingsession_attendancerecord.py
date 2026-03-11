from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_coursefile_weekly_module"),
    ]

    operations = [
        migrations.CreateModel(
            name="MeetingSession",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("date", models.DateField()),
                ("title", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("course_section", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="meeting_sessions", to="core.coursesection")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.user")),
            ],
            options={
                "ordering": ["-date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AttendanceRecord",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("Present", "Present"), ("Absent", "Absent"), ("Late", "Late"), ("Excused", "Excused")], default="Absent", max_length=10)),
                ("remarks", models.TextField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("marked_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="marked_attendance_records", to="core.user")),
                ("meeting", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attendance_records", to="core.meetingsession")),
                ("student", models.ForeignKey(limit_choices_to={"role": "student"}, on_delete=django.db.models.deletion.CASCADE, related_name="attendance_records", to="core.user")),
            ],
            options={
                "ordering": ["meeting__date", "student__full_name"],
                "unique_together": {("meeting", "student")},
            },
        ),
    ]
