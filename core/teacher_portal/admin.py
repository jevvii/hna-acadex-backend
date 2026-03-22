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

from core.models import Enrollment, CourseSectionGroup, User, CourseSection, Course
from core.utils import generate_student_id, generate_school_email_from_parts
from core.email_utils import generate_random_password, send_credentials_email

from .site import teacher_portal_site
from .views import get_teacher_advisory


# =============================================================================
# Student Creation Form and Admin
# =============================================================================

class TeacherStudentCreationForm(forms.ModelForm):
    """Form for teachers to create student accounts for their advisory."""

    first_name = forms.CharField(max_length=100, label="First Name")
    last_name = forms.CharField(max_length=100, label="Last Name")
    middle_name = forms.CharField(max_length=100, required=False, label="Middle Name")
    personal_email = forms.EmailField(
        required=False,
        label="Personal Email",
        help_text="Email address for sending login credentials"
    )
    send_credentials = forms.BooleanField(
        required=False,
        initial=True,
        label="Send login credentials via email",
        help_text="Sends school email and password to personal email"
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'middle_name', 'personal_email', 'send_credentials']

    def clean_personal_email(self):
        """Check uniqueness of personal email."""
        personal_email = self.cleaned_data.get('personal_email', '')
        if personal_email:
            if User.objects.filter(personal_email=personal_email).exists():
                raise forms.ValidationError("This personal email is already in use.")
        return personal_email


class TeacherStudentChangeForm(forms.ModelForm):
    """Form for teachers to edit existing student accounts."""

    middle_name = forms.CharField(
        max_length=100,
        required=False,
        label="Middle Name"
    )
    personal_email = forms.EmailField(
        required=False,
        label="Personal Email",
        help_text="Student's personal email for contact"
    )
    is_irregular = forms.BooleanField(
        required=False,
        label="Is Irregular",
        help_text="Mark as irregular student (can enroll in courses outside advisory section)"
    )

    class Meta:
        model = User
        fields = ['middle_name', 'personal_email', 'is_irregular']

    def clean_personal_email(self):
        """Check uniqueness of personal email, excluding current instance."""
        personal_email = self.cleaned_data.get('personal_email', '')
        if personal_email:
            # Exclude current instance when checking uniqueness
            qs = User.objects.filter(personal_email=personal_email)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("This personal email is already in use.")
        return personal_email


class TeacherUserAdmin(admin.ModelAdmin):
    """Admin for teachers to view and create students in their advisory."""

    form = TeacherStudentCreationForm
    list_display = ['student_id_display', 'full_name_display', 'email', 'personal_email', 'is_irregular', 'status', 'created_at']
    list_filter = ['status', 'is_irregular']
    search_fields = ['first_name', 'last_name', 'email', 'student_id', 'personal_email']
    ordering = ['-created_at']

    # Fields shown when viewing/editing existing student (derived from advisory section)
    readonly_fields = ['student_id', 'email', 'username', 'role', 'section', 'grade_level', 'strand', 'status', 'created_at']

    # Fieldsets for creating new student
    add_fieldsets = (
        ('Student Information', {
            'fields': ('first_name', 'last_name', 'middle_name'),
            'description': 'Enter the student\'s name. Student ID and school email will be auto-generated.'
        }),
        ('Contact & Settings', {
            'fields': ('personal_email', 'send_credentials'),
            'description': 'Optional: Personal email for sending login credentials.'
        }),
    )

    # Fieldsets for editing existing student
    change_fieldsets = (
        ('Student Identity', {
            'fields': ('student_id', 'email'),
            'description': 'Auto-generated fields (read-only).'
        }),
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'middle_name'),
        }),
        ('Contact', {
            'fields': ('personal_email',),
        }),
        ('Academic Details', {
            'fields': ('grade_level', 'strand'),
            'description': 'Grade level and strand from advisory section (read-only).'
        }),
        ('Account Status', {
            'fields': ('status', 'is_irregular', 'section'),
            'description': 'Account status and section assignment (read-only).'
        }),
    )

    def get_fieldsets(self, request, obj=None):
        """Use different fieldsets for add vs change."""
        if obj is None:
            return self.add_fieldsets
        return self.change_fieldsets

    def get_readonly_fields(self, request, obj=None):
        """Show readonly fields only when editing existing student."""
        if obj is None:
            # Creating new - first_name and last_name are editable
            return []
        # Editing existing - show readonly fields plus first_name and last_name
        return self.readonly_fields + ['first_name', 'last_name']

    def get_form(self, request, obj=None, **kwargs):
        """Use different form for add vs change."""
        if obj is None:
            return TeacherStudentCreationForm
        return TeacherStudentChangeForm

    def student_id_display(self, obj):
        return obj.student_id or '—'
    student_id_display.short_description = 'Student ID'
    student_id_display.admin_order_field = 'student_id'

    def full_name_display(self, obj):
        return obj.get_full_name()
    full_name_display.short_description = 'Full Name'
    full_name_display.admin_order_field = 'last_name'

    def has_delete_permission(self, request, obj=None):
        """Teachers cannot delete students."""
        return False

    def has_view_permission(self, request, obj=None):
        """Teachers with active advisory can view students."""
        return get_teacher_advisory(request.user) is not None

    def has_change_permission(self, request, obj=None):
        """Teachers with active advisory can edit students."""
        return get_teacher_advisory(request.user) is not None

    def has_add_permission(self, request):
        """Teachers can add students."""
        return True

    def get_queryset(self, request):
        """Filter to students in teacher's advisory section."""
        advisory = get_teacher_advisory(request.user)
        if not advisory:
            return User.objects.none()

        return User.objects.filter(
            role=User.Role.STUDENT,
            section=advisory.section.name,
            status=User.Status.ACTIVE
        ).order_by('-created_at')

    def save_model(self, request, obj, form, change):
        """Handle both student creation and editing."""
        advisory = get_teacher_advisory(request.user)
        if not advisory:
            raise ValueError("No active advisory assignment.")

        if change:
            # Editing existing student - just save changes
            # Only personal_email and is_irregular can be changed
            super().save_model(request, obj, form, change)
            messages.success(request, f"Student {obj.get_full_name()} updated successfully.")
        else:
            # Creating new student - generate credentials
            first_name = form.cleaned_data['first_name']
            last_name = form.cleaned_data['last_name']
            middle_name = form.cleaned_data.get('middle_name', '') or ''
            personal_email = form.cleaned_data.get('personal_email', '')
            send_credentials = form.cleaned_data.get('send_credentials', False)

            # Generate student ID and email
            student_id = generate_student_id()
            email = generate_school_email_from_parts(
                first_name=first_name,
                last_name=last_name,
                middle_name=middle_name if middle_name else None,
                role='student',
                id_number=student_id
            )

            # Generate random password
            plain_password = generate_random_password()

            # Set user attributes
            obj.student_id = student_id
            obj.email = email
            obj.username = email  # Use email as username
            obj.role = User.Role.STUDENT
            obj.section = advisory.section.name
            obj.grade_level = advisory.section.grade_level  # From advisory section
            obj.strand = advisory.section.strand  # From advisory section
            obj.status = User.Status.ACTIVE
            obj.is_active = True
            obj.requires_setup = True
            obj.first_name = first_name
            obj.last_name = last_name
            obj.middle_name = middle_name if middle_name else None
            obj.personal_email = personal_email if personal_email else None

            # Set password
            obj.set_password(plain_password)

            # Save the user
            super().save_model(request, obj, form, change)

            # Send credentials email if requested and personal email provided
            if send_credentials and personal_email:
                success, message = send_credentials_email(obj, plain_password)
                if success:
                    messages.success(request, f"Student created successfully. Credentials sent to {personal_email}")
                else:
                    messages.warning(request, f"Student created but email failed: {message}")
                    messages.info(request, f"Student ID: {student_id}, Email: {email}, Password: {plain_password}")
            else:
                messages.success(request, f"Student created successfully.")
                messages.info(request, f"Student ID: {student_id}, Email: {email}, Password: {plain_password}")


# =============================================================================
# Course Admin for Teachers
# =============================================================================

class TeacherCourseAdmin(admin.ModelAdmin):
    """Admin for teachers to create courses for their curriculum."""

    list_display = ['code', 'title', 'school_year', 'semester', 'grade_level', 'strand', 'is_active']
    list_filter = ['school_year', 'semester', 'is_active']
    search_fields = ['code', 'title']
    ordering = ['school_year', 'code']

    fieldsets = (
        ('Course Details', {
            'fields': ('code', 'title', 'description'),
            'description': 'Enter the course code and title.'
        }),
        ('Academic Period', {
            'fields': ('school_year', 'semester', 'num_weeks'),
        }),
        ('Classification', {
            'fields': ('grade_level', 'strand'),
        }),
        ('Status', {
            'fields': ('is_active',),
        }),
    )

    def has_delete_permission(self, request, obj=None):
        """Teachers cannot delete courses."""
        return False

    def has_add_permission(self, request):
        """Teachers with active advisory can add courses."""
        return get_teacher_advisory(request.user) is not None

    def has_view_permission(self, request, obj=None):
        """Teachers with active advisory can view courses."""
        return get_teacher_advisory(request.user) is not None

    def has_change_permission(self, request, obj=None):
        """Teachers with active advisory can change courses."""
        return get_teacher_advisory(request.user) is not None

    def get_queryset(self, request):
        """Filter courses by advisory's grade level and strand."""
        advisory = get_teacher_advisory(request.user)
        if not advisory:
            return Course.objects.none()

        qs = Course.objects.filter(grade_level=advisory.section.grade_level)
        if advisory.section.strand and advisory.section.strand != 'NONE':
            qs = qs.filter(strand=advisory.section.strand)
        return qs

    def get_changeform_initial_data(self, request):
        """Pre-fill form with advisory defaults."""
        advisory = get_teacher_advisory(request.user)
        if not advisory:
            return {}

        initial = {
            'grade_level': advisory.section.grade_level,
            'school_year': advisory.school_year,
            'num_weeks': 18,
            'is_active': True,
        }
        if advisory.section.strand and advisory.section.strand != 'NONE':
            initial['strand'] = advisory.section.strand
        return initial


# =============================================================================
# Enrollment Admin for Teachers
# =============================================================================

class EnrollmentAdminTeacher(admin.ModelAdmin):
    """Enrollment admin scoped to teacher's advisory."""

    list_display = ('student_name', 'course_section_display', 'is_irregular_flag', 'is_active', 'enrolled_at')
    list_filter = ('is_active', 'course_section__course__code')
    search_fields = ('student__first_name', 'student__last_name', 'student__email', 'student__student_id')
    autocomplete_fields = ('student',)

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

    def has_add_permission(self, request):
        """Teachers with active advisory can add enrollments."""
        return get_teacher_advisory(request.user) is not None

    def has_view_permission(self, request, obj=None):
        """Teachers with active advisory can view enrollments."""
        return get_teacher_advisory(request.user) is not None

    def has_change_permission(self, request, obj=None):
        """Teachers with active advisory can change enrollments."""
        return get_teacher_advisory(request.user) is not None

    def has_delete_permission(self, request, obj=None):
        """Teachers cannot delete enrollments."""
        return False

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
# Order matters: User must be registered before Enrollment (for autocomplete)
teacher_portal_site.register(User, TeacherUserAdmin)
teacher_portal_site.register(Course, TeacherCourseAdmin)
teacher_portal_site.register(Enrollment, EnrollmentAdminTeacher)
teacher_portal_site.register(CourseSectionGroup, CourseSectionGroupAdminTeacher)