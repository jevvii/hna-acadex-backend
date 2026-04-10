"""Data migration: backfill GradeSubmission and SectionReportCard from existing data.

GradeSubmission: one per (course_section, grading_period) pair that has at least one GradeEntry.
  - If all GradeEntries for that pair have is_published=True → status=published
  - If at least one has is_published=True but not all → status=submitted
  - If none have is_published=True → status=draft

SectionReportCard: one per (section, grading_period) pair where ALL enrolled students
  have published grade entries for that period.
"""
from django.db import migrations


def backfill_grade_submissions_and_report_cards(apps, schema_editor):
    GradeEntry = apps.get_model("core", "GradeEntry")
    GradeSubmission = apps.get_model("core", "GradeSubmission")
    SectionReportCard = apps.get_model("core", "SectionReportCard")
    Enrollment = apps.get_model("core", "Enrollment")
    CourseSection = apps.get_model("core", "CourseSection")
    Section = apps.get_model("core", "Section")
    GradingPeriod = apps.get_model("core", "GradingPeriod")

    # --- Backfill GradeSubmission records ---
    # Group existing GradeEntry records by (course_section, grading_period)
    entry_pairs = list(
        GradeEntry.objects
        .select_related("enrollment__course_section", "grading_period")
        .values_list("enrollment__course_section", "grading_period")
        .distinct()
    )

    for course_section_id, grading_period_id in entry_pairs:
        # Get all grade entries for this pair
        entries = GradeEntry.objects.filter(
            enrollment__course_section_id=course_section_id,
            grading_period_id=grading_period_id,
        )

        total_count = entries.count()
        published_count = entries.filter(is_published=True).count()

        if published_count == total_count and total_count > 0:
            status = "published"
        elif published_count > 0:
            status = "submitted"
        else:
            status = "draft"

        GradeSubmission.objects.get_or_create(
            course_section_id=course_section_id,
            grading_period_id=grading_period_id,
            defaults={
                "status": status,
            },
        )

    # --- Backfill SectionReportCard records ---
    # For each (section, grading_period) where ALL enrolled students in ALL
    # course_sections of that section have published grade entries, create
    # a SectionReportCard with is_published=True.
    active_sections = Section.objects.all()
    grading_periods = GradingPeriod.objects.all()

    for section in active_sections:
        # Get all active enrollments for course_sections in this section
        enrollment_ids = list(
            Enrollment.objects.filter(
                course_section__section=section,
                is_active=True,
            ).values_list("id", flat=True)
        )

        if not enrollment_ids:
            continue

        for gp in grading_periods:
            total_entries = GradeEntry.objects.filter(
                enrollment_id__in=enrollment_ids,
                grading_period_id=gp.id,
            ).count()

            if total_entries == 0:
                continue

            published_entries = GradeEntry.objects.filter(
                enrollment_id__in=enrollment_ids,
                grading_period_id=gp.id,
                is_published=True,
            ).count()

            # Only publish if every enrolled student has a published entry
            if published_entries == len(enrollment_ids) and published_entries > 0:
                SectionReportCard.objects.get_or_create(
                    section_id=section.id,
                    grading_period_id=gp.id,
                    defaults={
                        "is_published": True,
                    },
                )


def reverse_backfill(apps, schema_editor):
    GradeSubmission = apps.get_model("core", "GradeSubmission")
    SectionReportCard = apps.get_model("core", "SectionReportCard")
    GradeSubmission.objects.all().delete()
    SectionReportCard.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0030_gradeentry_adviser_overridden_adviseroverridelog_and_more"),
    ]

    operations = [
        migrations.RunPython(
            backfill_grade_submissions_and_report_cards,
            reverse_backfill,
        ),
    ]