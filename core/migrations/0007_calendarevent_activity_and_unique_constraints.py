from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_assignmentgroup_enrollment_manual_final_grade_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="calendarevent",
            name="activity",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="calendar_events", to="core.activity"),
        ),
        migrations.AlterUniqueTogether(
            name="calendarevent",
            unique_together={("creator", "activity")},
        ),
        migrations.AlterUniqueTogether(
            name="todoitem",
            unique_together={("user", "activity")},
        ),
    ]
