# Teacher Portal Admin Registrations
"""
ModelAdmin registrations for the Teacher Portal.

These are scoped versions of the main admin's ModelAdmins, filtered
to only show data related to the teacher's advisory section.
"""

from django.contrib import admin, messages
from django.db import transaction
from django.shortcuts import render, redirect
from django.urls import reverse
from django import forms
from django.db.models import Q

from core.models import Enrollment, CourseSectionGroup, User, CourseSection

from .site import teacher_portal_site
from .views import get_teacher_advisory


class EnrollmentAdminTeacher(admin.ModelAdmin):
    """Enrollment admin scoped to teacher's advisory."""

    list_display = ('student_name', 'course_section_display', 'is_irregular_flag', 'is_active', 'enrolled_at')
    list_filter = ('is_active', 'course_section__course__code')
    search_fields = ('student__first_name', 'student__last_name', 'student__email', 'student__student_id')
    autocomplete_fields = ('student', 'course_section')
    raw_id_fields = ('student',)

    fieldsets = (
        ('Enrollment Details', {
            'fields': ('student', 'course_section', 'is_active'),
            'description': 'Enroll a student in a class offering.'
        }),
        ('Grade Information', {
            'fields': ('final_grade', 'manual_final_grade'),
            'classes': ('collapse',)
        }),
    )

    actions = ['activate_enrollments', 'deactivate_enrollments']

    def student_name(self, obj):
        return obj.student.get_full_name()
    student_name.short_description = 'Student'
    student_name.admin_order_field = 'student__last_name'

    def course_section_display(self, obj):
        return str(obj.course_section)
    course_section_display.short_description = 'Class'
    course_section_display.admin_order_field = 'course_section'

    def is_irregular_flag(self, obj):
        return obj.student.is_irregular
    is_irregular_flag.short_description = 'Irregular'
    is_irregular_flag.boolean = True

    def get_queryset(self, request):
        """Filter to teacher's advisory students."""
        advisory = get_teacher_advisory(request.user)
        if not advisory:
            return Enrollment.objects.none()

        # Regular students in advisory section + irregular students enrolled elsewhere
        return Enrollment.objects.filter(
            Q(course_section__section=advisory.section) |
            Q(student__is_irregular=True, student__section=advisory.section.name)
        ).select_related('student', 'course_section__course', 'course_section__section')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Limit student and course_section choices to advisory scope."""
        advisory = get_teacher_advisory(request.user)
        if not advisory:
            return super().formfield_for_foreignkey(db_field, request, **kwargs)

        if db_field.name == 'student':
            kwargs['queryset'] = User.objects.filter(
                role=User.Role.STUDENT,
                section=advisory.section.name,
                status=User.Status.ACTIVE
            )
        elif db_field.name == 'course_section':
            # Show all active CourseSections; validation on save handles irregular students
            kwargs['queryset'] = CourseSection.objects.filter(is_active=True).select_related('course', 'section')

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        """Validate enrollment before saving."""
        advisory = get_teacher_advisory(request.user)
        if not advisory:
            raise ValueError("No active advisory assignment.")

        # Check business rules
        student = obj.student
        course_section = obj.course_section

        if not student.is_irregular:
            # Regular students can only be enrolled in their advisory section
            if course_section.section != advisory.section:
                raise ValueError(
                    f"Regular students can only be enrolled in courses belonging to their "
                    f"advisory section. {student.get_full_name()} is a regular student in "
                    f"{advisory.section.name}."
                )

        super().save_model(request, obj, form, change)

    def activate_enrollments(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"Activated {count} enrollment(s).", level=messages.SUCCESS)
    activate_enrollments.short_description = "Activate selected enrollments"

    def deactivate_enrollments(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {count} enrollment(s).", level=messages.SUCCESS)
    deactivate_enrollments.short_description = "Deactivate selected enrollments"


class CourseSectionGroupAdminTeacher(admin.ModelAdmin):
    """CourseSectionGroup admin (read-only for teachers, with enroll action)."""

    list_display = ('name', 'school_year', 'course_count', 'student_count', 'is_active')
    readonly_fields = ('name', 'description', 'school_year', 'semester', 'course_sections', 'is_active', 'created_at', 'updated_at')

    def course_count(self, obj):
        return obj.course_sections.count()
    course_count.short_description = 'Classes'

    def student_count(self, obj):
        return Enrollment.objects.filter(
            course_section__in=obj.course_sections.all(),
            is_active=True
        ).values('student').distinct().count()
    student_count.short_description = 'Enrolled'

    def has_add_permission(self, request):
        """Teachers cannot create enrollment groups."""
        return False

    def has_change_permission(self, request, obj=None):
        """Teachers cannot edit enrollment group definitions."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Teachers cannot delete enrollment groups."""
        return False

    def get_queryset(self, request):
        """Filter to groups matching advisory section name and school year."""
        advisory = get_teacher_advisory(request.user)
        if not advisory:
            return CourseSectionGroup.objects.none()

        return CourseSectionGroup.objects.filter(
            name=advisory.section.name,
            school_year=advisory.school_year
        ).prefetch_related('course_sections')

    def get_urls(self):
        """Add URL for bulk enrollment action."""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/enroll-students/',
                self.admin_site.admin_view(self.enroll_students_view),
                name='teacher_portal_core_coursesectiongroup_enroll_students'
            ),
        ]
        return custom_urls + urls

    def enroll_students_view(self, request, object_id):
        """View to enroll multiple students to all courses in the group."""
        from django.shortcuts import get_object_or_404
        from django.http import HttpResponseRedirect

        advisory = get_teacher_advisory(request.user)
        if not advisory:
            self.message_user(request, "No active advisory assignment.", level=messages.ERROR)
            return HttpResponseRedirect(reverse('teacher_portal:index'))

        course_group = get_object_or_404(CourseSectionGroup, pk=object_id)

        # Verify group belongs to teacher's advisory
        if course_group.name != advisory.section.name or course_group.school_year != advisory.school_year:
            self.message_user(request, "This enrollment group does not belong to your advisory.", level=messages.ERROR)
            return HttpResponseRedirect(reverse('teacher_portal:index'))

        if request.method == 'POST':
            student_ids = request.POST.getlist('students')
            course_sections = course_group.course_sections.filter(is_active=True)

            if not course_sections.exists():
                self.message_user(request, "No active course sections in this group.", level=messages.ERROR)
                return HttpResponseRedirect(request.path)

            created_count = 0
            skipped_count = 0

            with transaction.atomic():
                for student_id in student_ids:
                    student = User.objects.filter(pk=student_id, role=User.Role.STUDENT).first()
                    if not student:
                        continue

                    # Verify student is in advisory (regular or irregular)
                    if student.section != advisory.section.name and not student.is_irregular:
                        continue

                    for course_section in course_sections:
                        _, created = Enrollment.objects.get_or_create(
                            student=student,
                            course_section=course_section,
                            defaults={'is_active': True}
                        )
                        if created:
                            created_count += 1
                        else:
                            skipped_count += 1

            self.message_user(
                request,
                f"Enrolled {len(student_ids)} student(s) to {course_sections.count()} course(s). "
                f"Created {created_count} new enrollments, {skipped_count} already existed.",
                level=messages.SUCCESS
            )
            return HttpResponseRedirect(reverse('teacher_portal:teacher_portal_core_coursesectiongroup_changelist'))

        # GET - show form
        # Students in advisory section (regular) + irregular students from advisory
        students = User.objects.filter(
            Q(section=advisory.section.name, role=User.Role.STUDENT) |
            Q(is_irregular=True, section=advisory.section.name, role=User.Role.STUDENT),
            status=User.Status.ACTIVE
        ).order_by('last_name', 'first_name')

        context = {
            'course_group': course_group,
            'students': students,
            'opts': self.model._meta,
            'has_view_permission': True,
            'title': f'Enroll Students to {course_group.name}',
        }
        return render(request, 'admin/course_section_group_enroll.html', context)


# Register models to teacher portal site
teacher_portal_site.register(Enrollment, EnrollmentAdminTeacher)
teacher_portal_site.register(CourseSectionGroup, CourseSectionGroupAdminTeacher)