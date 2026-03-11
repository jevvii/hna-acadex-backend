from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CourseSection, WeeklyModule


@receiver(post_save, sender=CourseSection)
def create_default_weekly_modules(sender, instance: CourseSection, created: bool, **kwargs):
    if not created:
        return
    total_weeks = max(int(instance.course.num_weeks or 0), 0)
    if total_weeks <= 0:
        return

    WeeklyModule.objects.bulk_create(
        [
            WeeklyModule(
                course_section=instance,
                week_number=week_number,
                title=f"Week {week_number}",
                description="",
                is_exam_week=False,
                is_published=True,
                sort_order=week_number,
            )
            for week_number in range(1, total_weeks + 1)
        ]
    )
