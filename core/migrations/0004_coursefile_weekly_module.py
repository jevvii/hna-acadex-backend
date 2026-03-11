from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_quizattempt_quizquestion_quizchoice_quizanswer_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="coursefile",
            name="weekly_module",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="learning_materials",
                to="core.weeklymodule",
            ),
        ),
    ]
