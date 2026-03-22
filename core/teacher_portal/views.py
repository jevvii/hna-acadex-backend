# Teacher Portal Views
"""
Views for the Teacher Portal.

These views handle:
- Dashboard (landing page for teachers)
- SIS Import functionality (scoped to teacher's advisory)
"""

import base64
import io

from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib import messages
from django.urls import reverse
from django.db.models import Q

from core.models import TeacherAdvisory, User, Section, CourseSection, Enrollment, CourseSectionGroup
from .site import teacher_portal_site


def get_teacher_advisory(user):
    """
    Get the active TeacherAdvisory for a user.

    Args:
        user: User instance

    Returns:
        TeacherAdvisory instance or None
    """
    return TeacherAdvisory.objects.filter(
        teacher=user,
        is_active=True
    ).select_related('section').first()


def get_context(request, **kwargs):
    """
    Get base context for teacher portal templates.

    Includes admin site context (has_permission, site_header, etc.)
    and any additional kwargs.

    Args:
        request: HttpRequest
        **kwargs: Additional context variables

    Returns:
        dict: Context dictionary
    """
    context = teacher_portal_site.each_context(request)
    context.update(kwargs)
    return context


def render_no_advisory(request):
    """Render the 'no advisory assigned' error page."""
    context = get_context(request, title='No Advisory Assigned')
    return render(request, 'teacher_portal/assign_advisory_error.html', context)


def dashboard(request):
    """Teacher portal dashboard view with live enrollment data."""
    from core.models import Course

    advisory = get_teacher_advisory(request.user)

    if not advisory:
        return render_no_advisory(request)

    # Build enrollment queryset (same as EnrollmentAdminTeacher.get_queryset)
    enrollments = Enrollment.objects.filter(
        Q(course_section__section=advisory.section) |
        Q(student__is_irregular=True, student__section=advisory.section.name)
    ).select_related('student', 'course_section__course', 'course_section__section', 'course_section__teacher')

    # Search filter
    q = request.GET.get('q', '').strip()
    if q:
        enrollments = enrollments.filter(
            Q(student__first_name__icontains=q) |
            Q(student__last_name__icontains=q) |
            Q(student__email__icontains=q) |
            Q(student__student_id__icontains=q)
        )

    # Course filter
    course_code = request.GET.get('course', '')
    if course_code:
        enrollments = enrollments.filter(course_section__course__code=course_code)

    # Active filter
    active = request.GET.get('active', '')
    if active == 'true':
        enrollments = enrollments.filter(is_active=True)
    elif active == 'false':
        enrollments = enrollments.filter(is_active=False)

    # Irregular filter
    irregular = request.GET.get('irregular', '')
    if irregular == 'true':
        enrollments = enrollments.filter(student__is_irregular=True)
    elif irregular == 'false':
        enrollments = enrollments.filter(student__is_irregular=False)

    # Order by enrolled_at descending
    enrollments = enrollments.order_by('-enrolled_at')

    # Calculate stats
    total_enrollments = enrollments.count()
    total_students = enrollments.values('student').distinct().count()
    irregular_students = enrollments.filter(student__is_irregular=True).values('student').distinct().count()
    active_enrollments = enrollments.filter(is_active=True).count()

    # Available courses for filter dropdown
    available_courses = CourseSection.objects.filter(
        section=advisory.section,
        is_active=True
    ).values_list('course__code', flat=True).distinct()

    context = get_context(request,
        title='Advisory Dashboard',
        teacher_advisory=advisory,
        enrollments=enrollments,
        search_query=q,
        total_enrollments=total_enrollments,
        total_students=total_students,
        irregular_students=irregular_students,
        active_enrollments=active_enrollments,
        available_courses=available_courses,
        current_filters={
            'course': course_code,
            'active': active,
            'irregular': irregular,
        },
    )
    return render(request, 'teacher_portal/index.html', context)


def sis_import_index(request):
    """SIS Import index page for teachers."""
    advisory = get_teacher_advisory(request.user)

    if not advisory:
        return render_no_advisory(request)

    context = get_context(request,
        title='SIS Import',
        teacher_advisory=advisory,
        import_types=[
            {
                'name': 'Students',
                'description': 'Import students into your advisory section',
                'url_name': 'teacher_portal:tp_sis_import_users',
                'icon': 'person',
            },
            {
                'name': 'Courses',
                'description': 'Import courses for your advisory curriculum',
                'url_name': 'teacher_portal:tp_sis_import_courses',
                'icon': 'book',
            },
            {
                'name': 'Course Sections',
                'description': 'Create class offerings for your advisory courses',
                'url_name': 'teacher_portal:tp_sis_import_course_sections',
                'icon': 'school',
            },
            {
                'name': 'Enrollments',
                'description': 'Import student enrollments for your advisory courses',
                'url_name': 'teacher_portal:tp_sis_import_enrollments',
                'icon': 'group',
            },
        ],
    )
    return render(request, 'teacher_portal/sis_import/index.html', context)


def sis_import_users(request):
    """Handle student CSV import for teacher's advisory."""
    from .sis_import.processors.users import TeacherScopedUserCSVProcessor

    advisory = get_teacher_advisory(request.user)

    if not advisory:
        return render_no_advisory(request)

    processor = TeacherScopedUserCSVProcessor(
        advisory_section_name=advisory.section.name,
        advisory_school_year=advisory.school_year,
        advisory_section=advisory.section,
    )

    if request.method == 'POST':
        action = request.POST.get('action', 'validate')

        if action == 'import':
            # Get stored CSV content from session
            csv_content_b64 = request.session.get('tp_sis_import_users_csv')
            if not csv_content_b64:
                messages.error(request, "Session expired. Please re-upload the CSV file.")
                return redirect('teacher_portal:tp_sis_import_users')

            csv_content = base64.b64decode(csv_content_b64).decode('utf-8')
            csv_file = io.StringIO(csv_content)

            # Execute import
            result = processor.execute_import(csv_file)

            # Clear session data
            request.session.pop('tp_sis_import_users_csv', None)
            request.session.pop('tp_sis_import_users_result', None)

            if result.success:
                messages.success(request, result.message)
            else:
                messages.error(request, result.message)

            context = get_context(request,
                title='Import Students - Result',
                result=result,
                teacher_advisory=advisory,
                step='result',
            )
            return render(request, 'teacher_portal/sis_import/import_users.html', context)

        else:  # action == 'validate'
            from .sis_import.forms import SISImportForm

            form = SISImportForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES['csv_file']

                # Read and store file content for later import
                csv_file.seek(0)
                csv_content = csv_file.read()
                if isinstance(csv_content, bytes):
                    csv_content = csv_content.decode('utf-8')

                # Store in session
                request.session['tp_sis_import_users_csv'] = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')

                # Validate
                csv_file.seek(0)
                validation_result = processor.validate_all(csv_file)

                context = get_context(request,
                    title='Import Students - Preview',
                    form=form,
                    validation_result=validation_result,
                    teacher_advisory=advisory,
                    step='preview',
                )
                return render(request, 'teacher_portal/sis_import/import_users.html', context)
    else:
        from .sis_import.forms import SISImportForm
        form = SISImportForm()

    context = get_context(request,
        title='Import Students',
        form=form,
        teacher_advisory=advisory,
        required_headers=processor.required_headers,
        optional_headers=processor.optional_headers,
        step='upload',
    )
    return render(request, 'teacher_portal/sis_import/import_users.html', context)


def sis_import_enrollments(request):
    """Handle enrollment CSV import for teacher's advisory."""
    from .sis_import.processors.enrollments import TeacherScopedEnrollmentCSVProcessor

    advisory = get_teacher_advisory(request.user)

    if not advisory:
        return render_no_advisory(request)

    processor = TeacherScopedEnrollmentCSVProcessor(
        advisory_section=advisory.section,
        advisory_school_year=advisory.school_year,
    )

    if request.method == 'POST':
        action = request.POST.get('action', 'validate')

        if action == 'import':
            csv_content_b64 = request.session.get('tp_sis_import_enrollments_csv')
            if not csv_content_b64:
                messages.error(request, "Session expired. Please re-upload the CSV file.")
                return redirect('teacher_portal:tp_sis_import_enrollments')

            csv_content = base64.b64decode(csv_content_b64).decode('utf-8')
            csv_file = io.StringIO(csv_content)

            result = processor.execute_import(csv_file)

            request.session.pop('tp_sis_import_enrollments_csv', None)
            request.session.pop('tp_sis_import_enrollments_result', None)

            if result.success:
                messages.success(request, result.message)
            else:
                messages.error(request, result.message)

            context = get_context(request,
                title='Import Enrollments - Result',
                result=result,
                teacher_advisory=advisory,
                step='result',
            )
            return render(request, 'teacher_portal/sis_import/import_enrollments.html', context)

        else:  # action == 'validate'
            from .sis_import.forms import SISImportForm

            form = SISImportForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES['csv_file']

                csv_file.seek(0)
                csv_content = csv_file.read()
                if isinstance(csv_content, bytes):
                    csv_content = csv_content.decode('utf-8')

                request.session['tp_sis_import_enrollments_csv'] = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')

                csv_file.seek(0)
                validation_result = processor.validate_all(csv_file)

                context = get_context(request,
                    title='Import Enrollments - Preview',
                    form=form,
                    validation_result=validation_result,
                    teacher_advisory=advisory,
                    step='preview',
                )
                return render(request, 'teacher_portal/sis_import/import_enrollments.html', context)
    else:
        from .sis_import.forms import SISImportForm
        form = SISImportForm()

    context = get_context(request,
        title='Import Enrollments',
        form=form,
        teacher_advisory=advisory,
        required_headers=processor.required_headers,
        optional_headers=processor.optional_headers,
        step='upload',
    )
    return render(request, 'teacher_portal/sis_import/import_enrollments.html', context)


def sis_import_courses(request):
    """Handle course CSV import for teacher's advisory."""
    from .sis_import.processors.courses import TeacherScopedCourseCSVProcessor

    advisory = get_teacher_advisory(request.user)

    if not advisory:
        return render_no_advisory(request)

    processor = TeacherScopedCourseCSVProcessor(
        advisory_section=advisory.section,
    )

    if request.method == 'POST':
        action = request.POST.get('action', 'validate')

        if action == 'import':
            csv_content_b64 = request.session.get('tp_sis_import_courses_csv')
            if not csv_content_b64:
                messages.error(request, "Session expired. Please re-upload the CSV file.")
                return redirect('teacher_portal:tp_sis_import_courses')

            csv_content = base64.b64decode(csv_content_b64).decode('utf-8')
            csv_file = io.StringIO(csv_content)

            result = processor.execute_import(csv_file)

            request.session.pop('tp_sis_import_courses_csv', None)
            request.session.pop('tp_sis_import_courses_result', None)

            if result.success:
                messages.success(request, result.message)
            else:
                messages.error(request, result.message)

            context = get_context(request,
                title='Import Courses - Result',
                result=result,
                teacher_advisory=advisory,
                step='result',
            )
            return render(request, 'teacher_portal/sis_import/import_courses.html', context)

        else:  # action == 'validate'
            from .sis_import.forms import SISImportForm

            form = SISImportForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES['csv_file']

                csv_file.seek(0)
                csv_content = csv_file.read()
                if isinstance(csv_content, bytes):
                    csv_content = csv_content.decode('utf-8')

                request.session['tp_sis_import_courses_csv'] = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')

                csv_file.seek(0)
                validation_result = processor.validate_all(csv_file)

                context = get_context(request,
                    title='Import Courses - Preview',
                    form=form,
                    validation_result=validation_result,
                    teacher_advisory=advisory,
                    step='preview',
                )
                return render(request, 'teacher_portal/sis_import/import_courses.html', context)
    else:
        from .sis_import.forms import SISImportForm
        form = SISImportForm()

    context = get_context(request,
        title='Import Courses',
        form=form,
        teacher_advisory=advisory,
        required_headers=processor.required_headers,
        optional_headers=processor.optional_headers,
        step='upload',
    )
    return render(request, 'teacher_portal/sis_import/import_courses.html', context)


# Template download views

def download_users_template(request):
    """Download CSV template for student import."""
    from .sis_import.processors.users import TeacherScopedUserCSVProcessor

    advisory = get_teacher_advisory(request.user)
    processor = TeacherScopedUserCSVProcessor(
        advisory_section_name=advisory.section.name if advisory else '',
        advisory_school_year=advisory.school_year if advisory else '',
        advisory_section=advisory.section if advisory else None,
    )
    csv_content = processor.get_template_csv()

    response = HttpResponse(csv_content, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="students_import_template.csv"'
    return response


def download_enrollments_template(request):
    """Download CSV template for enrollment import."""
    from .sis_import.processors.enrollments import TeacherScopedEnrollmentCSVProcessor

    advisory = get_teacher_advisory(request.user)
    processor = TeacherScopedEnrollmentCSVProcessor(
        advisory_section=advisory.section if advisory else None,
        advisory_school_year=advisory.school_year if advisory else '',
    )
    csv_content = processor.get_template_csv()

    response = HttpResponse(csv_content, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="enrollments_import_template.csv"'
    return response


def download_courses_template(request):
    """Download CSV template for course import."""
    from .sis_import.processors.courses import TeacherScopedCourseCSVProcessor

    advisory = get_teacher_advisory(request.user)
    processor = TeacherScopedCourseCSVProcessor(
        advisory_section=advisory.section if advisory else None,
    )
    csv_content = processor.get_template_csv()

    response = HttpResponse(csv_content, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="courses_import_template.csv"'
    return response


def sis_import_course_sections(request):
    """Handle CourseSection CSV import for teacher's advisory."""
    from .sis_import.processors.course_sections import TeacherScopedCourseSectionCSVProcessor

    advisory = get_teacher_advisory(request.user)

    if not advisory:
        return render_no_advisory(request)

    processor = TeacherScopedCourseSectionCSVProcessor(
        advisory_section=advisory.section,
        advisory_school_year=advisory.school_year,
        teacher_user=request.user,
    )

    if request.method == 'POST':
        action = request.POST.get('action', 'validate')

        if action == 'import':
            csv_content_b64 = request.session.get('tp_sis_import_course_sections_csv')
            if not csv_content_b64:
                messages.error(request, "Session expired. Please re-upload the CSV file.")
                return redirect('teacher_portal:tp_sis_import_course_sections')

            csv_content = base64.b64decode(csv_content_b64).decode('utf-8')
            csv_file = io.StringIO(csv_content)

            result = processor.execute_import(csv_file)

            request.session.pop('tp_sis_import_course_sections_csv', None)
            request.session.pop('tp_sis_import_course_sections_result', None)

            if result.success:
                messages.success(request, result.message)
            else:
                messages.error(request, result.message)

            context = get_context(request,
                title='Import Course Sections - Result',
                result=result,
                teacher_advisory=advisory,
                step='result',
            )
            return render(request, 'teacher_portal/sis_import/import_course_sections.html', context)

        else:  # action == 'validate'
            from .sis_import.forms import SISImportForm

            form = SISImportForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES['csv_file']

                csv_file.seek(0)
                csv_content = csv_file.read()
                if isinstance(csv_content, bytes):
                    csv_content = csv_content.decode('utf-8')

                request.session['tp_sis_import_course_sections_csv'] = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')

                csv_file.seek(0)
                validation_result = processor.validate_all(csv_file)

                context = get_context(request,
                    title='Import Course Sections - Preview',
                    form=form,
                    validation_result=validation_result,
                    teacher_advisory=advisory,
                    step='preview',
                )
                return render(request, 'teacher_portal/sis_import/import_course_sections.html', context)
    else:
        from .sis_import.forms import SISImportForm
        form = SISImportForm()

    context = get_context(request,
        title='Import Course Sections',
        form=form,
        teacher_advisory=advisory,
        required_headers=processor.required_headers,
        optional_headers=processor.optional_headers,
        step='upload',
    )
    return render(request, 'teacher_portal/sis_import/import_course_sections.html', context)


def download_course_sections_template(request):
    """Download CSV template for CourseSection import."""
    from .sis_import.processors.course_sections import TeacherScopedCourseSectionCSVProcessor

    advisory = get_teacher_advisory(request.user)
    processor = TeacherScopedCourseSectionCSVProcessor(
        advisory_section=advisory.section if advisory else None,
        advisory_school_year=advisory.school_year if advisory else '',
        teacher_user=request.user if request.user.is_authenticated else None,
    )
    csv_content = processor.get_template_csv()

    response = HttpResponse(csv_content, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="course_sections_import_template.csv"'
    return response