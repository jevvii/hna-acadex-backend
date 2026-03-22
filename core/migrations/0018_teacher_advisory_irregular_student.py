# Generated migration for TeacherAdvisory model
"""
Migration: 0018_teacher_advisory_irregular_student
Adds:
  - TeacherAdvisory model for section advisory assignments
"""

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_add_separate_name_fields'),
    ]

    operations = [
        # Create TeacherAdvisory model
        migrations.CreateModel(
            name='TeacherAdvisory',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)),
                ('teacher', models.ForeignKey(
                    on_delete=models.CASCADE,
                    related_name='advisory_assignments',
                    to='core.user',
                    limit_choices_to={'role': 'teacher'},
                    verbose_name='Teacher'
                )),
                ('section', models.ForeignKey(
                    on_delete=models.CASCADE,
                    related_name='advisory_assignments',
                    to='core.section',
                    verbose_name='Section'
                )),
                ('school_year', models.CharField(
                    max_length=20,
                    help_text='Academic year e.g. 2024-2025',
                    verbose_name='School Year'
                )),
                ('is_active', models.BooleanField(default=True, verbose_name='Active')),
                ('assigned_at', models.DateTimeField(auto_now_add=True, verbose_name='Assigned At')),
                ('assigned_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=models.SET_NULL,
                    related_name='advisory_assignments_made',
                    to='core.user',
                    limit_choices_to={'role': 'admin'},
                    verbose_name='Assigned By'
                )),
            ],
            options={
                'verbose_name': 'Teacher Advisory',
                'verbose_name_plural': 'Teacher Advisories',
                'ordering': ['-school_year', 'section__name'],
            },
        ),

        # Add unique_together constraints
        migrations.AlterUniqueTogether(
            name='teacheradvisory',
            unique_together={
                ('teacher', 'school_year'),
                ('section', 'school_year'),
            },
        ),
    ]