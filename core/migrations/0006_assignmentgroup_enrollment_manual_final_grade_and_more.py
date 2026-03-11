from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_meetingsession_attendancerecord"),
    ]

    operations = [
        migrations.AddField(
            model_name="enrollment",
            name="manual_final_grade",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.CreateModel(
            name="AssignmentGroup",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=100)),
                ("weight_percent", models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("course_section", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assignment_groups", to="core.coursesection")),
            ],
            options={
                "ordering": ["name"],
                "unique_together": {("course_section", "name")},
            },
        ),
        migrations.AddField(
            model_name="activity",
            name="assignment_group",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="activities", to="core.assignmentgroup"),
        ),
    ]
