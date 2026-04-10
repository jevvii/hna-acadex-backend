# hna-acadex-backend/core/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin, GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.models import Group
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django import forms
from django.contrib import messages
from django.utils.html import format_html
from django.db import models
from .models import (
    Activity,
    ActivityComment,
    ActivityReminder,
    AdviserOverrideLog,
    Announcement,
    AssignmentGroup,
    AssignmentWeight,
    AttendanceRecord,
    CalendarEvent,
    Course,
    CourseFile,
    CourseSection,
    CourseSectionGroup,
    Enrollment,
    GradeEntry,
    GradeSubmission,
    GradeWeightConfig,
    GradingPeriod,
    IDCounter,
    Notification,
    MeetingSession,
    PasswordResetRequest,
    PushToken,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizChoice,
    QuizQuestion,
    Section,
    SectionReportCard,
    Submission,
    TeacherAdvisory,
    TodoItem,
    User,
    WeeklyModule,
)
from .email_utils import generate_random_password, send_credentials_email
from .admin_site import admin_site
from .utils import (
    generate_student_id,
    generate_teacher_id,
    generate_school_email,
    generate_school_email_from_parts,
)

# Register auth models to custom admin site
admin_site.register(Group, DjangoGroupAdmin)


class CustomUserCreationForm(UserCreationForm):
    """Custom form for creating users with auto-generated password and IDs."""

    personal_email = forms.EmailField(
        required=False,
        label="Personal Email",
        help_text="Personal email for sending login credentials (required for teachers/students)"
    )
    first_name = forms.CharField(
        max_length=100,
        label="First Name",
        help_text="First name (e.g., 'Juan' or 'Maria Clara')"
    )
    last_name = forms.CharField(
        max_length=100,
        label="Last Name",
        help_text="Last name / Surname (e.g., 'Dela Cruz' or 'Santos')"
    )
    middle_name = forms.CharField(
        max_length=100,
        required=False,
        label="Middle Name",
        help_text="Middle name or initial (optional)"
    )
    auto_generate_password = forms.BooleanField(
        required=False,
        initial=True,
        label="Auto-generate password",
        help_text="If checked, a random password will be generated. Uncheck to set password manually."
    )
    password1 = forms.CharField(
        label="Password",
        required=False,
        widget=forms.PasswordInput,
        help_text="Required if auto-generate password is unchecked."
    )
    password2 = forms.CharField(
        label="Password confirmation",
        required=False,
        widget=forms.PasswordInput,
        help_text="Enter the same password as above, for verification."
    )
    send_credentials_email = forms.BooleanField(
        required=False,
        initial=True,
        label="Send credentials via email",
        help_text="If checked, login credentials will be sent to the personal email address."
    )

    class Meta:
        model = User
        fields = ('personal_email', 'first_name', 'last_name', 'middle_name', 'role', 'status', 'is_irregular', 'is_active', 'is_staff')
        # Note: email, student_id, employee_id are auto-generated for students/teachers

    def clean_personal_email(self):
        """Validate that personal_email is not already in use."""
        personal_email = self.cleaned_data.get('personal_email', '')
        if personal_email:
            existing_user = User.objects.filter(personal_email=personal_email).first()
            if existing_user:
                raise forms.ValidationError(
                    f"This personal email is already used by user: {existing_user.get_full_name()} ({existing_user.email})"
                )
        return personal_email

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        personal_email = cleaned_data.get('personal_email')
        auto_generate = cleaned_data.get('auto_generate_password', True)
        send_email = cleaned_data.get('send_credentials_email', True)
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        # Require personal email for teachers and students if sending email
        if role in [User.Role.TEACHER, User.Role.STUDENT] and send_email and not personal_email:
            self.add_error('personal_email', 'Personal email is required to send credentials for teachers/students.')

        # If not auto-generating, require password fields
        if not auto_generate:
            if not password1:
                self.add_error('password1', 'Password is required when auto-generate is unchecked.')
            if not password2:
                self.add_error('password2', 'Password confirmation is required when auto-generate is unchecked.')
            if password1 and password2 and password1 != password2:
                self.add_error('password2', 'The two password fields didn\'t match.')

        return cleaned_data


class CustomUserChangeForm(UserChangeForm):
    """Custom form for changing user details."""

    personal_email = forms.EmailField(
        required=False,
        label="Personal Email",
        help_text="Personal email for sending login credentials"
    )

    class Meta:
        model = User
        fields = '__all__'

    def clean_personal_email(self):
        """Validate that personal_email is not already in use by another user."""
        personal_email = self.cleaned_data.get('personal_email', '')
        if personal_email:
            # Check if any OTHER user has this personal_email
            # Exclude the current user being edited (self.instance)
            existing_user = User.objects.filter(personal_email=personal_email).exclude(pk=self.instance.pk).first()
            if existing_user:
                raise forms.ValidationError(
                    f"This personal email is already used by user: {existing_user.get_full_name()} ({existing_user.email})"
                )
        return personal_email


class UserAdmin(DjangoUserAdmin):
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
    model = User
    list_display = (
        "email",
        "get_full_name",
        "role",
        "status",
        "personal_email",
        "is_staff",
        "is_active",
        "created_at",
    )
    list_filter = ("role", "status", "is_staff", "is_superuser", "is_active")
    ordering = ("-created_at",)
    search_fields = ("email", "first_name", "last_name", "middle_name", "employee_id", "student_id", "personal_email")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal info",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "middle_name",
                    "personal_email",
                    "avatar",
                    "avatar_url",
                    "role",
                    "status",
                    "grade_level",
                    "strand",
                    "section",
                    "is_irregular",
                    "employee_id",
                    "student_id",
                    "theme",
                )
            },
        ),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login", "date_joined", "created_at", "updated_at")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "personal_email",
                    "first_name",
                    "last_name",
                    "middle_name",
                    "role",
                    "status",
                    "is_irregular",
                    "auto_generate_password",
                    "password1",
                    "password2",
                    "send_credentials_email",
                    "is_active",
                    "is_staff",
                ),
            },
        ),
    )

    readonly_fields = ("created_at", "updated_at", "date_joined", "last_login", "current_advisory_display")

    actions = ["send_credentials_action", "assign_advisory_action"]

    def send_credentials_action(self, request, queryset):
        """Admin action to send login credentials to selected users."""
        success_count = 0
        error_count = 0

        for user in queryset:
            if user.role not in [User.Role.TEACHER, User.Role.STUDENT]:
                self.message_user(
                    request,
                    f"Skipping {user.email} - can only send credentials to teachers and students.",
                    level=messages.WARNING
                )
                continue

            if not user.personal_email:
                self.message_user(
                    request,
                    f"Skipping {user.email} - no personal email configured.",
                    level=messages.WARNING
                )
                continue

            # Generate a new password
            new_password = generate_random_password()
            user.set_password(new_password)
            user.save()

            # Send the email
            success, message = send_credentials_email(user, new_password)
            if success:
                success_count += 1
            else:
                error_count += 1
                self.message_user(request, f"Failed to send to {user.email}: {message}", level=messages.ERROR)

        if success_count > 0:
            self.message_user(
                request,
                f"Successfully sent credentials to {success_count} user(s).",
                level=messages.SUCCESS
            )
        if error_count > 0:
            self.message_user(
                request,
                f"Failed to send credentials to {error_count} user(s).",
                level=messages.ERROR
            )

    send_credentials_action.short_description = "Send login credentials via email"

    def current_advisory_display(self, obj):
        """Display the current advisory assignment for teachers."""
        if obj.role != User.Role.TEACHER:
            return "—"
        advisory = TeacherAdvisory.objects.filter(
            teacher=obj, is_active=True
        ).select_related('section').first()
        if advisory:
            return f"{advisory.section.name} ({advisory.school_year})"
        return "—"
    current_advisory_display.short_description = "Current Advisory"

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/assign-advisory/',
                self.admin_site.admin_view(self.assign_advisory_view),
                name='core_user_assign_advisory'
            ),
        ]
        return custom_urls + urls

    def assign_advisory_action(self, request, queryset):
        """Admin action to assign advisory section to selected teacher."""
        from django.shortcuts import redirect
        from django.urls import reverse
        from django.contrib import messages as admin_messages

        # Check that only one teacher is selected
        if queryset.count() != 1:
            admin_messages.error(request, "Please select exactly one teacher to assign advisory.")
            return

        user = queryset.first()

        # Check that the selected user is a teacher
        if user.role != User.Role.TEACHER:
            admin_messages.error(request, "Only teachers can be assigned advisory sections.")
            return

        # Redirect to the intermediate view
        return redirect(reverse('hna_acadex_admin:core_user_assign_advisory', args=[user.pk]))

    assign_advisory_action.short_description = "Assign advisory section"

    def assign_advisory_view(self, request, object_id):
        """Intermediate view for assigning advisory section to a teacher."""
        from django.shortcuts import get_object_or_404, render
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        from django import forms
        from django.db import IntegrityError

        user = get_object_or_404(User, pk=object_id)

        # Only teachers can have advisory assignments
        if user.role != User.Role.TEACHER:
            self.message_user(request, "Only teachers can be assigned advisory sections.", level=messages.ERROR)
            return HttpResponseRedirect(reverse('hna_acadex_admin:core_user_changelist'))

        class AssignAdvisoryForm(forms.Form):
            section = forms.ModelChoiceField(
                queryset=Section.objects.filter(is_active=True).order_by('name'),
                label="Advisory Section",
                help_text="Select the section this teacher will advise."
            )
            school_year = forms.CharField(
                max_length=20,
                label="School Year",
                help_text="Academic year (e.g., 2024-2025)"
            )

        # Get current advisory if exists
        current_advisory = TeacherAdvisory.objects.filter(
            teacher=user, is_active=True
        ).select_related('section').first()

        if request.method == 'POST':
            form = AssignAdvisoryForm(request.POST)
            if form.is_valid():
                section = form.cleaned_data['section']
                school_year = form.cleaned_data['school_year']

                # Check for existing advisory for this section/year
                existing = TeacherAdvisory.objects.filter(
                    section=section,
                    school_year=school_year,
                    is_active=True
                ).exclude(teacher=user).first()

                if existing:
                    self.message_user(
                        request,
                        f"Section '{section.name}' already has an adviser ({existing.teacher.get_full_name()}) for {school_year}.",
                        level=messages.ERROR
                    )
                else:
                    try:
                        # Deactivate existing advisory if any
                        TeacherAdvisory.objects.filter(
                            teacher=user, school_year=school_year, is_active=True
                        ).update(is_active=False)

                        # Create new advisory
                        TeacherAdvisory.objects.create(
                            teacher=user,
                            section=section,
                            school_year=school_year,
                            assigned_by=request.user
                        )

                        self.message_user(
                            request,
                            f"Successfully assigned {user.get_full_name()} as adviser for {section.name} ({school_year}).",
                            level=messages.SUCCESS
                        )
                        return HttpResponseRedirect(reverse('hna_acadex_admin:core_user_changelist'))

                    except IntegrityError:
                        self.message_user(
                            request,
                            f"Teacher {user.get_full_name()} already has an advisory assignment for {school_year}.",
                            level=messages.ERROR
                        )
        else:
            # Pre-fill form with current advisory if exists
            initial = {}
            if current_advisory:
                initial['section'] = current_advisory.section
                initial['school_year'] = current_advisory.school_year
            form = AssignAdvisoryForm(initial=initial)

        context = {
            'user_obj': user,
            'form': form,
            'current_advisory': current_advisory,
            'opts': self.model._meta,
            'has_view_permission': True,
            'title': f'Assign Advisory Section for {user.get_full_name()}',
        }
        return render(request, 'admin/assign_advisory.html', context)

    actions = ["send_credentials_action", "assign_advisory_action"]

    def save_model(self, request, obj, form, change):
        """Override save_model to handle auto-generated passwords, IDs, and emails."""
        if not change:
            # Creating a new user
            auto_generate = form.cleaned_data.get('auto_generate_password', True)
            send_email = form.cleaned_data.get('send_credentials_email', True)
            role = form.cleaned_data.get('role')
            first_name = form.cleaned_data.get('first_name', '')
            last_name = form.cleaned_data.get('last_name', '')
            middle_name = form.cleaned_data.get('middle_name', '')

            if auto_generate:
                # Generate a random password
                plain_password = generate_random_password()
            else:
                # Use the manually entered password
                plain_password = form.cleaned_data.get('password1')

            # Set the password on the user object BEFORE saving
            # This is critical - without this, the user is created with no usable password
            obj.set_password(plain_password)

            # Auto-generate ID and email for students and teachers
            if role == User.Role.STUDENT:
                student_id = generate_student_id()
                obj.student_id = student_id
                # Generate school email from name parts
                obj.email = generate_school_email_from_parts(
                    first_name, last_name, middle_name, 'student', student_id
                )
                obj.username = obj.email  # username mirrors email
            elif role == User.Role.TEACHER:
                employee_id = generate_teacher_id()
                obj.employee_id = employee_id
                # Generate school email from name parts
                obj.email = generate_school_email_from_parts(
                    first_name, last_name, middle_name, 'teacher', employee_id
                )
                obj.username = obj.email  # username mirrors email
            # For admin users, email must be provided manually (handled by parent class)

            # Save the user first
            super().save_model(request, obj, form, change)

            # Send credentials email if requested
            if send_email and obj.personal_email:
                if role in [User.Role.TEACHER, User.Role.STUDENT]:
                    success, message = send_credentials_email(obj, plain_password)
                    if success:
                        self.message_user(
                            request,
                            f"User created successfully. School email: {obj.email}. "
                            f"Credentials sent to {obj.personal_email}",
                            level=messages.SUCCESS
                        )
                    else:
                        self.message_user(
                            request,
                            f"User created with school email: {obj.email}. Email failed: {message}",
                            level=messages.WARNING
                        )
                else:
                    self.message_user(
                        request,
                        f"User created. Email not sent (only teachers/students receive credentials).",
                        level=messages.INFO
                    )
            else:
                if send_email and not obj.personal_email:
                    if role in [User.Role.TEACHER, User.Role.STUDENT]:
                        self.message_user(
                            request,
                            f"User created with school email: {obj.email}. "
                            f"Credentials not sent - no personal email provided.",
                            level=messages.INFO
                        )
                    else:
                        self.message_user(
                            request,
                            f"User created with {'auto-generated' if auto_generate else 'manual'} password.",
                            level=messages.SUCCESS
                        )
        else:
            # Updating existing user
            super().save_model(request, obj, form, change)

    def current_advisory_display(self, obj):
        """Display the current advisory assignment for teachers."""
        if obj.role != User.Role.TEACHER:
            return "-"
        advisory = TeacherAdvisory.objects.filter(
            teacher=obj, is_active=True
        ).select_related('section').first()
        if advisory:
            return f"{advisory.section.name} ({advisory.school_year})"
        return "No advisory assigned"
    current_advisory_display.short_description = "Current Advisory"

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/assign-advisory/',
                self.admin_site.admin_view(self.assign_advisory_view),
                name='core_user_assign_advisory',
            ),
        ]
        return custom_urls + urls

    def assign_advisory_view(self, request, object_id):
        """Intermediate view for assigning advisory section to a teacher."""
        from django.shortcuts import get_object_or_404, render, redirect
        from django.urls import reverse
        from django.db import IntegrityError
        from django import forms

        user = get_object_or_404(User, pk=object_id)

        # Only teachers can have advisory assignments
        if user.role != User.Role.TEACHER:
            self.message_user(request, "Only teachers can be assigned advisory sections.", level=messages.ERROR)
            return redirect('hna_acadex_admin:core_user_change', object_id)

        class AssignAdvisoryForm(forms.Form):
            section = forms.ModelChoiceField(
                queryset=Section.objects.filter(is_active=True).order_by('name'),
                required=True,
                label='Advisory Section',
                help_text='Select the section this teacher will advise.'
            )
            school_year = forms.CharField(
                max_length=20,
                required=True,
                label='School Year',
                help_text='Academic year (e.g., 2024-2025)'
            )
            is_active = forms.BooleanField(
                required=False,
                initial=True,
                label='Active',
                help_text='Mark this advisory assignment as active.'
            )

        # Get current advisory if any
        current_advisory = TeacherAdvisory.objects.filter(
            teacher=user, is_active=True
        ).select_related('section').first()

        if request.method == 'POST':
            form = AssignAdvisoryForm(request.POST)
            if form.is_valid():
                section = form.cleaned_data['section']
                school_year = form.cleaned_data['school_year']
                is_active = form.cleaned_data['is_active']

                try:
                    # Deactivate any existing active advisory for this teacher
                    TeacherAdvisory.objects.filter(teacher=user, is_active=True).update(is_active=False)

                    # Create new advisory
                    TeacherAdvisory.objects.create(
                        teacher=user,
                        section=section,
                        school_year=school_year,
                        is_active=is_active,
                        assigned_by=request.user
                    )
                    self.message_user(
                        request,
                        f"Successfully assigned {user.get_full_name()} as adviser for {section.name} ({school_year}).",
                        level=messages.SUCCESS
                    )
                    return redirect('hna_acadex_admin:core_user_change', object_id)
                except IntegrityError as e:
                    if 'unique constraint' in str(e).lower() or 'duplicate' in str(e).lower():
                        self.message_user(
                            request,
                            f"Section {section.name} already has an adviser for {school_year}, or {user.get_full_name()} already has an advisory for {school_year}.",
                            level=messages.ERROR
                        )
                    else:
                        raise
        else:
            # Pre-populate form with current advisory if exists
            initial = {}
            if current_advisory:
                initial = {
                    'section': current_advisory.section,
                    'school_year': current_advisory.school_year,
                    'is_active': current_advisory.is_active,
                }
            form = AssignAdvisoryForm(initial=initial)

        context = {
            'user': user,
            'form': form,
            'current_advisory': current_advisory,
            'opts': self.model._meta,
            'title': f'Assign Advisory for {user.get_full_name()}',
            'has_view_permission': True,
        }
        return render(request, 'admin/assign_advisory.html', context)

    def assign_advisory_action(self, request, queryset):
        """Admin action to assign advisory section to selected teacher."""
        teachers = queryset.filter(role=User.Role.TEACHER)

        if teachers.count() != 1:
            self.message_user(
                request,
                "Please select exactly one teacher to assign an advisory section.",
                level=messages.WARNING
            )
            return

        teacher = teachers.first()
        from django.urls import reverse
        return redirect(reverse('hna_acadex_admin:core_user_assign_advisory', args=[teacher.pk]))

    assign_advisory_action.short_description = "Assign advisory section to selected teacher"


class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "display_grade_strand", "school_year", "is_active", "course_count")
    list_filter = ("grade_level", "strand", "school_year", "is_active")
    search_fields = ("name",)

    def display_grade_strand(self, obj):
        if obj.strand and obj.strand != 'NONE':
            return f"{obj.get_grade_level_display()} - {obj.get_strand_display()}"
        return obj.get_grade_level_display()
    display_grade_strand.short_description = "Grade & Strand"

    def course_count(self, obj):
        return obj.course_sections.filter(is_active=True).count()
    course_count.short_description = "Active Classes"

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('course_sections')


class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "category", "school_year", "semester", "is_active")
    list_filter = ("category", "school_year", "semester", "is_active")
    search_fields = ("code", "title")
    fieldsets = (
        ("Course Details", {
            "fields": ("code", "title", "description")
        }),
        ("Academic Period", {
            "fields": ("school_year", "semester", "num_weeks")
        }),
        ("Classification", {
            "fields": ("grade_level", "strand", "category")
        }),
        ("Display Settings", {
            "fields": ("cover_image_url", "color_overlay"),
            "classes": ("collapse",)
        }),
        ("Status", {
            "fields": ("is_active",)
        }),
    )


class CourseSectionAdmin(admin.ModelAdmin):
    list_display = ("course", "section", "teacher", "school_year", "semester", "enrollment_count", "is_active")
    list_filter = ("school_year", "semester", "is_active", "course__code")
    search_fields = ("course__code", "course__title", "section__name", "teacher__first_name", "teacher__last_name")
    autocomplete_fields = ("course", "section", "teacher")
    raw_id_fields = ("teacher",)

    fieldsets = (
        ("Class Offering", {
            "fields": ("course", "section", "teacher"),
            "description": "A class offering combines a subject (course) with a specific class section and teacher."
        }),
        ("Academic Period", {
            "fields": ("school_year", "semester", "is_active")
        }),
    )

    def get_queryset(self, request):
        from django.db.models import Count, Q
        qs = super().get_queryset(request)
        return qs.select_related("course", "section", "teacher").annotate(
            _enrollment_count=Count("enrollments", filter=Q(enrollments__is_active=True))
        )

    def enrollment_count(self, obj):
        return obj._enrollment_count
    enrollment_count.short_description = "Students"
    enrollment_count.admin_order_field = "_enrollment_count"


class CourseSectionGroupForm(forms.ModelForm):
    """Custom form for CourseSectionGroup with validation."""

    class Meta:
        model = CourseSectionGroup
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        course_sections = cleaned_data.get('course_sections')

        if course_sections and course_sections.count() > 10:
            raise forms.ValidationError(
                "A course group can contain at most 10 courses. "
                f"You have selected {course_sections.count()} courses."
            )

        return cleaned_data


class CourseSectionGroupInlineEnrollmentForm(forms.Form):
    """Form for enrolling students to a course group with autocomplete search."""
    students = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(role=User.Role.STUDENT, status=User.Status.ACTIVE),
        required=True,
        help_text="Search and select students to enroll in all courses in this group"
    )


class CourseSectionGroupAdmin(admin.ModelAdmin):
    form = CourseSectionGroupForm
    list_display = ("name", "school_year", "semester", "course_count", "student_count", "is_active", "created_at")
    list_filter = ("school_year", "semester", "is_active")
    search_fields = ("name", "description")
    filter_horizontal = ("course_sections",)
    readonly_fields = ("created_at", "updated_at", "course_count", "student_count", "enroll_students_link")

    fieldsets = (
        (None, {
            "fields": ("name", "description", "is_active"),
            "description": "An Enrollment Group allows you to enroll students to multiple classes at once."
        }),
        ("Academic Period", {
            "fields": ("school_year", "semester")
        }),
        ("Class Offerings", {
            "fields": ("course_sections",),
            "description": "Select up to 10 class offerings to include in this group."
        }),
        ("Info", {
            "fields": ("created_at", "updated_at", "course_count", "student_count"),
            "classes": ("collapse",)
        }),
    )

    def course_count(self, obj):
        return obj.course_sections.count()
    course_count.short_description = "Classes"

    def student_count(self, obj):
        # Count unique students enrolled in any course in the group
        return Enrollment.objects.filter(
            course_section__in=obj.course_sections.all(),
            is_active=True
        ).values("student").distinct().count()
    student_count.short_description = "Enrolled Students"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("course_sections")

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/enroll-students/',
                self.admin_site.admin_view(self.enroll_students_view),
                name='core_coursesectiongroup_enroll_students'
            ),
            path(
                'autocomplete/students/',
                self.admin_site.admin_view(self.student_autocomplete_view),
                name='core_user_autocomplete_students'
            ),
        ]
        return custom_urls + urls

    def student_autocomplete_view(self, request):
        """AJAX endpoint for student search autocomplete."""
        from django.http import JsonResponse
        term = request.GET.get('term', '').strip()
        page = int(request.GET.get('page', 1))
        page_size = 20
        offset = (page - 1) * page_size

        queryset = User.objects.filter(
            role=User.Role.STUDENT,
            status=User.Status.ACTIVE
        )

        if term:
            queryset = queryset.filter(
                models.Q(first_name__icontains=term) |
                models.Q(email__icontains=term) |
                models.Q(student_id__icontains=term)
            )

        # Get total count for pagination info
        total_count = queryset.count()

        # Apply pagination
        results = queryset[offset:offset + page_size]

        # Format results for Select2
        data = {
            'results': [
                {
                    'id': str(student.id),
                    'text': f"{student.full_name} ({student.email})" + (f" - {student.student_id}" if student.student_id else "")
                }
                for student in results
            ],
            'pagination': {
                'more': offset + page_size < total_count
            },
            'total_count': total_count,
        }
        return JsonResponse(data)

    def enroll_students_link(self, obj):
        """Display a link to enroll students (shown after saving)."""
        from django.urls import reverse
        from django.utils.html import format_html
        if obj.pk:
            url = reverse('hna_acadex_admin:core_coursesectiongroup_enroll_students', args=[obj.pk])
            return format_html('<a class="button" href="{}">Enroll Students to All Courses in Group</a>', url)
        return "-"
    enroll_students_link.short_description = "Student Enrollment"
    enroll_students_link.allow_tags = True

    def get_readonly_fields(self, request, obj=None):
        """Only show enroll_students_link for existing objects."""
        if obj:
            return self.readonly_fields
        return tuple(f for f in self.readonly_fields if f != 'enroll_students_link')

    def get_fieldsets(self, request, obj=None):
        """Add enrollment section for existing objects."""
        fieldsets = super().get_fieldsets(request, obj)
        if obj and obj.pk:
            # Add enrollment section at the end
            fieldsets = list(fieldsets) + [
                ("Student Enrollment", {
                    "fields": ("enroll_students_link",),
                    "description": "Click the button above to enroll students to all courses in this group."
                }),
            ]
        return fieldsets

    def enroll_students_view(self, request, object_id):
        """View to enroll multiple students to all courses in the group."""
        from django.shortcuts import get_object_or_404, render
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        from django.contrib import messages as admin_messages
        from django.db import transaction

        course_group = get_object_or_404(CourseSectionGroup, pk=object_id)

        if request.method == 'POST':
            form = CourseSectionGroupInlineEnrollmentForm(request.POST)
            if form.is_valid():
                students = form.cleaned_data['students']
                course_sections = course_group.course_sections.filter(is_active=True)

                if not course_sections.exists():
                    admin_messages.error(request, "No active course sections in this group.")
                    return HttpResponseRedirect(request.path)

                created_count = 0
                skipped_count = 0

                with transaction.atomic():
                    for student in students:
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

                admin_messages.success(
                    request,
                    f"Successfully enrolled {students.count()} student(s) to {course_sections.count()} course(s). "
                    f"Created {created_count} new enrollments, {skipped_count} already existed."
                )
                return HttpResponseRedirect(reverse('hna_acadex_admin:core_coursesectiongroup_changelist'))
        else:
            form = CourseSectionGroupInlineEnrollmentForm()

        context = {
            'course_group': course_group,
            'form': form,
            'opts': self.model._meta,
            'has_view_permission': True,
            'title': f'Enroll Students to {course_group.name}',
        }
        return render(request, 'admin/course_section_group_enroll.html', context)


class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "course_section", "display_grade", "is_active", "enrolled_at")
    list_filter = ("is_active", "course_section__school_year", "course_section__semester")
    search_fields = ("student__last_name", "student__first_name", "student__email", "student__student_id")
    autocomplete_fields = ("student", "course_section")
    raw_id_fields = ("student",)
    date_hierarchy = "enrolled_at"

    actions = ["activate_enrollments", "deactivate_enrollments", "bulk_enroll_to_classes"]

    fieldsets = (
        ("Enrollment Details", {
            "fields": ("student", "course_section"),
            "description": "Enroll a student in a class offering."
        }),
        ("Grade Information", {
            "fields": ("final_grade", "manual_final_grade"),
            "classes": ("collapse",)
        }),
        ("Status", {
            "fields": ("is_active",)
        }),
    )

    def display_grade(self, obj):
        if obj.manual_final_grade:
            return f"{obj.manual_final_grade}% (Manual)"
        return f"{obj.final_grade}%" if obj.final_grade else "-"
    display_grade.short_description = "Final Grade"

    def activate_enrollments(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"Activated {count} enrollment(s).", level=messages.SUCCESS)
    activate_enrollments.short_description = "Activate selected enrollments"

    def deactivate_enrollments(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {count} enrollment(s).", level=messages.SUCCESS)
    deactivate_enrollments.short_description = "Deactivate selected enrollments"

    def bulk_enroll_to_classes(self, request, queryset):
        """
        Bulk enroll selected students to multiple class offerings.
        Redirects to an intermediate page for class selection.
        """
        from django.http import HttpResponseRedirect
        from django.urls import reverse

        # Get unique students from selected enrollments
        students = queryset.values_list('student', flat=True).distinct()

        # Store student IDs in session for the intermediate page
        request.session['bulk_enroll_students'] = list(students)

        # Redirect to intermediate page for class selection
        return HttpResponseRedirect(reverse('hna_acadex_admin:core_enrollment_bulk_enroll'))
    bulk_enroll_to_classes.short_description = "Bulk enroll selected students to more classes"

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                'bulk-enroll/',
                self.admin_site.admin_view(self.bulk_enroll_view),
                name='core_enrollment_bulk_enroll'
            ),
        ]
        return custom_urls + urls

    def bulk_enroll_view(self, request):
        """Intermediate page for bulk enrollment."""
        from django.shortcuts import render
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        from django.db import transaction

        if request.method == 'POST':
            student_ids = request.session.get('bulk_enroll_students', [])
            course_section_ids = request.POST.getlist('course_sections')

            if not student_ids:
                messages.error(request, "No students selected.")
                return HttpResponseRedirect(reverse('hna_acadex_admin:core_enrollment_changelist'))

            if not course_section_ids:
                messages.error(request, "No classes selected.")
                return HttpResponseRedirect(request.path)

            created_count = 0
            with transaction.atomic():
                for student_id in student_ids:
                    for cs_id in course_section_ids:
                        _, created = Enrollment.objects.get_or_create(
                            student_id=student_id,
                            course_section_id=cs_id,
                            defaults={'is_active': True}
                        )
                        if created:
                            created_count += 1

            messages.success(request, f"Created {created_count} new enrollment(s).")
            if 'bulk_enroll_students' in request.session:
                del request.session['bulk_enroll_students']
            return HttpResponseRedirect(reverse('hna_acadex_admin:core_enrollment_changelist'))

        # GET - show form
        course_sections = CourseSection.objects.filter(is_active=True).select_related('course', 'section', 'teacher')
        student_ids = request.session.get('bulk_enroll_students', [])
        students = User.objects.filter(id__in=student_ids)

        context = {
            'students': students,
            'course_sections': course_sections,
            'opts': self.model._meta,
            'title': 'Bulk Enroll Students',
            'has_view_permission': True,
        }
        return render(request, 'admin/enrollment_bulk_enroll.html', context)


class WeeklyModuleAdmin(admin.ModelAdmin):
    list_display = ("course_section", "week_number", "title", "is_exam_week", "is_published")
    list_filter = ("is_exam_week", "is_published")


class AssignmentGroupAdmin(admin.ModelAdmin):
    list_display = ("course_section", "name", "weight_percent", "is_active", "created_at")
    list_filter = ("is_active", "course_section")
    search_fields = ("name", "course_section__course__title", "course_section__section__name")


class MeetingSessionAdmin(admin.ModelAdmin):
    list_display = ("course_section", "date", "title", "created_by", "created_at")
    list_filter = ("date", "course_section")
    search_fields = ("title", "course_section__course__title", "course_section__section__name")


class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("meeting", "student", "status", "marked_by", "updated_at")
    list_filter = ("status", "meeting__course_section")
    search_fields = ("student__first_name", "student__last_name", "student__email", "meeting__title")


class ActivityAdmin(admin.ModelAdmin):
    list_display = ("title", "course_section", "points", "deadline", "is_published")
    list_filter = ("is_published",)


class CourseFileAdmin(admin.ModelAdmin):
    list_display = ("file_name", "course_section", "category", "is_visible", "created_at")
    list_filter = ("category", "is_visible")


class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "course_section", "attempt_limit", "is_published", "created_at")
    list_filter = ("is_published",)


class QuizQuestionAdmin(admin.ModelAdmin):
    list_display = ("quiz", "question_type", "question_text", "points", "sort_order")
    list_filter = ("question_type",)
    search_fields = ("question_text", "quiz__title")


class QuizChoiceAdmin(admin.ModelAdmin):
    list_display = ("question", "choice_text", "is_correct", "sort_order")
    list_filter = ("is_correct",)


class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("quiz", "student", "attempt_number", "score", "max_score", "is_submitted", "pending_manual_grading", "submitted_at")
    list_filter = ("is_submitted", "pending_manual_grading")
    search_fields = ("quiz__title", "student__first_name", "student__last_name", "student__email")


class QuizAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "is_correct", "points_awarded", "needs_manual_grading", "graded_at")
    list_filter = ("needs_manual_grading", "is_correct")


class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("activity", "student", "status", "score", "submitted_at", "graded_at")
    list_filter = ("status",)
    search_fields = ("activity__title", "student__first_name", "student__last_name", "student__email")


class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "course_section", "school_wide", "audience", "is_published", "created_at")
    list_filter = ("school_wide", "audience", "is_published")


class CalendarEventAdmin(admin.ModelAdmin):
    list_display = ("title", "creator", "event_type", "start_at", "all_day", "is_personal")
    list_filter = ("event_type", "all_day", "is_personal")


class TodoItemAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "due_at", "is_done", "created_at")
    list_filter = ("is_done",)


class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "type", "title", "is_read", "created_at")
    list_filter = ("type", "is_read")


class PasswordResetRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "personal_email", "status", "created_at", "resolved_at", "resolved_by")
    list_filter = ("status", "created_at")
    search_fields = ("user__email", "user__first_name", "user__last_name", "personal_email")
    readonly_fields = ("created_at", "resolved_at", "resolved_by")
    ordering = ("-created_at",)

    actions = ["approve_requests", "decline_requests"]

    def approve_requests(self, request, queryset):
        """Admin action to approve multiple password reset requests."""
        from .email_utils import generate_random_password, send_password_reset_email
        from django.utils import timezone

        success_count = 0
        error_count = 0

        for reset_request in queryset.filter(status=PasswordResetRequest.Status.PENDING):
            user = reset_request.user

            # Generate new password
            new_password = generate_random_password()
            user.set_password(new_password)
            user.requires_setup = True
            user.save(update_fields=["password", "requires_setup", "updated_at"])

            # Send email
            success, message = send_password_reset_email(user, new_password)

            if success:
                reset_request.status = PasswordResetRequest.Status.APPROVED
                reset_request.resolved_at = timezone.now()
                reset_request.resolved_by = request.user
                reset_request.save()
                success_count += 1
            else:
                error_count += 1
                self.message_user(request, f"Failed to send email for {user.email}: {message}", level=messages.ERROR)

        if success_count > 0:
            self.message_user(request, f"Successfully approved {success_count} password reset request(s).", level=messages.SUCCESS)
        if error_count > 0:
            self.message_user(request, f"Failed to process {error_count} request(s).", level=messages.ERROR)

    approve_requests.short_description = "Approve selected password reset requests"

    def decline_requests(self, request, queryset):
        """Admin action to decline multiple password reset requests."""
        from django.utils import timezone

        count = 0
        for reset_request in queryset.filter(status=PasswordResetRequest.Status.PENDING):
            reset_request.status = PasswordResetRequest.Status.DECLINED
            reset_request.resolved_at = timezone.now()
            reset_request.resolved_by = request.user
            reset_request.save()
            count += 1

        if count > 0:
            self.message_user(request, f"Successfully declined {count} password reset request(s).", level=messages.SUCCESS)

    decline_requests.short_description = "Decline selected password reset requests"


class PushTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "token", "device_type", "device_name", "is_active", "created_at")
    list_filter = ("device_type", "is_active")
    search_fields = ("user__email", "user__first_name", "user__last_name", "token")
    readonly_fields = ("created_at", "updated_at")


class ActivityReminderAdmin(admin.ModelAdmin):
    list_display = ("user", "reminder_type", "activity", "quiz", "reminder_datetime", "notification_sent", "created_at")
    list_filter = ("reminder_type", "notification_sent")
    search_fields = ("user__email", "user__first_name", "user__last_name", "activity__title", "quiz__title")
    readonly_fields = ("created_at", "updated_at")


class IDCounterAdmin(admin.ModelAdmin):
    """Admin view for ID counters (read-only for audit purposes)."""
    list_display = ("year", "id_type", "prefix", "sequential", "last_id_display")
    list_filter = ("year", "id_type")
    readonly_fields = ("year", "id_type", "prefix", "sequential")

    def last_id_display(self, obj):
        """Display the last generated ID."""
        return f"{obj.prefix}{obj.year}{obj.sequential:04d}"
    last_id_display.short_description = "Last Generated ID"

    def has_add_permission(self, request):
        """Prevent manual creation via admin."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion via admin."""
        return False


class GradingPeriodAdmin(admin.ModelAdmin):
    """Admin for GradingPeriod - managing academic grading periods (quarters)."""
    list_display = ("school_year", "label", "semester_group_display", "period_number", "start_date", "end_date", "is_current")
    list_filter = ("school_year", "semester_group", "is_current")
    search_fields = ("school_year",)
    ordering = ("-school_year", "semester_group", "period_number")
    readonly_fields = ("label", "created_at", "updated_at")
    change_list_template = "admin/core/gradingperiod/change_list.html"

    fieldsets = (
        ("Period Info", {
            "fields": ("school_year", "period_number", "semester_group", "is_current"),
        }),
        ("Dates", {
            "fields": ("start_date", "end_date"),
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def semester_group_display(self, obj):
        if obj.semester_group is None:
            return "Grades 7-10"
        return f"Semester {obj.semester_group} (Grade 11-12)"
    semester_group_display.short_description = "Group"
    semester_group_display.admin_order_field = "semester_group"

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('generate-periods/', self.admin_site.admin_view(self.generate_periods_view), name='core_gradingperiod_generate_periods'),
        ]
        return custom_urls + urls

    def generate_periods_view(self, request):
        """View for generating grading periods for a school year."""
        from django.shortcuts import render, redirect
        from django.contrib import messages
        from django.db import transaction
        from datetime import date, timedelta
        from .models import GradingPeriod

        if request.method == 'POST':
            school_year = request.POST.get('school_year')
            grade_level_group = request.POST.get('grade_level_group', '7-10')
            start_month = int(request.POST.get('start_month', 6))
            start_day = int(request.POST.get('start_day', 1))
            quarter_weeks = int(request.POST.get('quarter_weeks', 10))
            set_current = int(request.POST.get('set_current', 1))

            # Validate school year format
            try:
                years = school_year.split('-')
                if len(years) != 2:
                    raise ValueError()
                start_year = int(years[0])
                end_year = int(years[1])
                if end_year != start_year + 1:
                    raise ValueError()
            except (ValueError, IndexError):
                messages.error(request, f"Invalid school year format '{school_year}'. Expected format: YYYY-YYYY (e.g., 2024-2025)")
                return redirect(request.path)

            # Calculate start date
            try:
                start_date = date(start_year, start_month, start_day)
            except ValueError as e:
                messages.error(request, f"Invalid start date: {e}")
                return redirect(request.path)

            # Generate quarter periods
            periods_to_create = []
            current_date = start_date

            for quarter_num in range(1, 5):
                end_date = current_date + timedelta(weeks=quarter_weeks)
                if quarter_num < 4:
                    end_date = end_date - timedelta(days=1)

                # Determine semester_group
                if grade_level_group == '11-12':
                    semester_group = 1 if quarter_num <= 2 else 2
                else:
                    semester_group = None

                periods_to_create.append({
                    'school_year': school_year,
                    'period_type': 'quarter',
                    'period_number': quarter_num,
                    'semester_group': semester_group,
                    'start_date': current_date,
                    'end_date': end_date,
                    'is_current': quarter_num == set_current,
                })

                if quarter_num < 4:
                    current_date = end_date + timedelta(days=1)

            # Create periods
            created_count = 0
            with transaction.atomic():
                for period_data in periods_to_create:
                    _, created = GradingPeriod.objects.get_or_create(
                        school_year=period_data['school_year'],
                        semester_group=period_data['semester_group'],
                        period_number=period_data['period_number'],
                        defaults={
                            'start_date': period_data['start_date'],
                            'end_date': period_data['end_date'],
                            'is_current': period_data['is_current'],
                            'period_type': 'quarter',
                        }
                    )
                    if created:
                        created_count += 1

            messages.success(request, f"Successfully created {created_count} grading periods for {school_year}.")
            return redirect('..')

        # GET request - show form
        context = {
            'title': 'Generate Grading Periods',
            'opts': self.model._meta,
            'has_view_permission': True,
            'site_header': 'HNA Acadex Admin',
        }
        return render(request, 'admin/core/gradingperiod/generate_periods.html', context)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_generate_button'] = True
        return super().changelist_view(request, extra_context)


class GradeEntryAdmin(admin.ModelAdmin):
    """Admin for GradeEntry - per-student per-period grades."""
    list_display = ("student_name", "course_section", "grading_period", "score", "is_published", "adviser_overridden", "updated_at")
    list_filter = ("grading_period", "is_published", "adviser_overridden", "enrollment__course_section__course__code")
    search_fields = ("enrollment__student__first_name", "enrollment__student__last_name", "enrollment__student__email")
    readonly_fields = ("computed_score", "computed_at", "created_at", "updated_at")
    autocomplete_fields = ("enrollment", "grading_period")

    fieldsets = (
        ("Student & Course", {
            "fields": ("enrollment", "grading_period"),
        }),
        ("Grade", {
            "fields": ("computed_score", "override_score", "is_published", "adviser_overridden"),
        }),
        ("Metadata", {
            "fields": ("computed_at", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def student_name(self, obj):
        return obj.enrollment.student.get_full_name()
    student_name.short_description = "Student"
    student_name.admin_order_field = "enrollment__student__first_name"

    def course_section(self, obj):
        return str(obj.enrollment.course_section)
    course_section.short_description = "Course Section"
    course_section.admin_order_field = "enrollment__course_section"


class GradeWeightConfigAdmin(admin.ModelAdmin):
    """Admin for GradeWeightConfig - DepEd grade weight configuration per course section."""
    list_display = ("course_section_info", "written_works", "performance_tasks", "quarterly_assessment", "is_customized", "updated_by", "updated_at")
    list_filter = ("is_customized", "course_section__course__category")
    search_fields = ("course_section__course__code", "course_section__course__title", "course_section__section__name")
    autocomplete_fields = ("course_section", "updated_by")

    def course_section_info(self, obj):
        return f"{obj.course_section.course.code} - {obj.course_section.section.name}"
    course_section_info.short_description = "Course Section"
    course_section_info.admin_order_field = "course_section__course__code"


class AssignmentWeightAdmin(admin.ModelAdmin):
    """Admin for AssignmentWeight - teacher-defined weighting for categories."""
    list_display = ("course_section_info", "grading_period", "category", "weight_percent")
    list_filter = ("grading_period", "category")
    search_fields = ("course_section__course__code", "course_section__course__title")
    autocomplete_fields = ("course_section", "grading_period")

    def course_section_info(self, obj):
        return f"{obj.course_section.course.code} - {obj.course_section.section.name}"
    course_section_info.short_description = "Course Section"
    course_section_info.admin_order_field = "course_section__course__code"


class GradeSubmissionAdmin(admin.ModelAdmin):
    """Admin for GradeSubmission - tracks submission status per subject+period."""
    list_display = ("course_section_info", "grading_period", "status", "submitted_by", "submitted_at", "taken_back_at")
    list_filter = ("status", "grading_period")
    search_fields = ("course_section__course__code", "course_section__course__title")
    autocomplete_fields = ("course_section", "grading_period", "submitted_by")

    def course_section_info(self, obj):
        return f"{obj.course_section.course.code} - {obj.course_section.section.name}"
    course_section_info.short_description = "Course Section"
    course_section_info.admin_order_field = "course_section__course__code"


class SectionReportCardAdmin(admin.ModelAdmin):
    """Admin for SectionReportCard - tracks report card publication per section+period."""
    list_display = ("section_info", "grading_period", "is_published", "published_by", "published_at")
    list_filter = ("is_published", "grading_period")
    search_fields = ("section__name",)
    autocomplete_fields = ("section", "grading_period", "published_by")

    def section_info(self, obj):
        return f"{obj.section.name} (Grade {obj.section.grade_level})"
    section_info.short_description = "Section"


class AdviserOverrideLogAdmin(admin.ModelAdmin):
    """Admin for AdviserOverrideLog - read-only audit trail of adviser grade overrides."""
    list_display = ("grade_entry_info", "adviser", "previous_score", "new_score", "created_at")
    list_filter = ("created_at",)
    search_fields = ("adviser__first_name", "adviser__last_name", "adviser__email")
    readonly_fields = ("grade_entry", "adviser", "previous_score", "new_score", "created_at", "updated_at")

    def grade_entry_info(self, obj):
        return str(obj.grade_entry)
    grade_entry_info.short_description = "Grade Entry"


class TeacherAdvisoryAdmin(admin.ModelAdmin):
    """Admin for TeacherAdvisory model - managing section adviser assignments."""

    list_display = ("teacher_full_name", "section_name", "school_year", "is_active", "assigned_at", "assigned_by")
    list_filter = ("school_year", "is_active", "section__grade_level", "section__strand")
    search_fields = ("teacher__first_name", "teacher__last_name", "teacher__email", "section__name")
    readonly_fields = ("assigned_at",)
    autocomplete_fields = ("teacher", "section")

    fieldsets = (
        ("Advisory Assignment", {
            "fields": ("teacher", "section", "school_year", "is_active"),
        }),
        ("Metadata", {
            "fields": ("assigned_at", "assigned_by"),
            "classes": ("collapse",),
        }),
    )

    def teacher_full_name(self, obj):
        return obj.teacher.get_full_name()
    teacher_full_name.short_description = "Teacher"
    teacher_full_name.admin_order_field = "teacher__first_name"

    def section_name(self, obj):
        return obj.section.name
    section_name.short_description = "Section"
    section_name.admin_order_field = "section__name"

    def save_model(self, request, obj, form, change):
        if not change:  # Only on creation
            obj.assigned_by = request.user
        super().save_model(request, obj, form, change)


# Register all models to the custom admin site
# Enrollment category models
admin_site.register(User, UserAdmin)
admin_site.register(Section, SectionAdmin)
admin_site.register(Course, CourseAdmin)
admin_site.register(CourseSection, CourseSectionAdmin)
admin_site.register(CourseSectionGroup, CourseSectionGroupAdmin)
admin_site.register(Enrollment, EnrollmentAdmin)
admin_site.register(TeacherAdvisory, TeacherAdvisoryAdmin)

# Core category models
admin_site.register(WeeklyModule, WeeklyModuleAdmin)
admin_site.register(AssignmentGroup, AssignmentGroupAdmin)
admin_site.register(MeetingSession, MeetingSessionAdmin)
admin_site.register(AttendanceRecord, AttendanceRecordAdmin)
admin_site.register(Activity, ActivityAdmin)
admin_site.register(CourseFile, CourseFileAdmin)
admin_site.register(Quiz, QuizAdmin)
admin_site.register(QuizQuestion, QuizQuestionAdmin)
admin_site.register(QuizChoice, QuizChoiceAdmin)
admin_site.register(QuizAttempt, QuizAttemptAdmin)
admin_site.register(QuizAnswer, QuizAnswerAdmin)
admin_site.register(Submission, SubmissionAdmin)
admin_site.register(Announcement, AnnouncementAdmin)
admin_site.register(CalendarEvent, CalendarEventAdmin)
admin_site.register(TodoItem, TodoItemAdmin)
admin_site.register(Notification, NotificationAdmin)
admin_site.register(PasswordResetRequest, PasswordResetRequestAdmin)
admin_site.register(PushToken, PushTokenAdmin)
admin_site.register(ActivityReminder, ActivityReminderAdmin)
admin_site.register(IDCounter, IDCounterAdmin)
admin_site.register(GradingPeriod, GradingPeriodAdmin)
admin_site.register(GradeEntry, GradeEntryAdmin)
admin_site.register(GradeWeightConfig, GradeWeightConfigAdmin)
admin_site.register(AssignmentWeight, AssignmentWeightAdmin)
admin_site.register(GradeSubmission, GradeSubmissionAdmin)
admin_site.register(SectionReportCard, SectionReportCardAdmin)
admin_site.register(AdviserOverrideLog, AdviserOverrideLogAdmin)