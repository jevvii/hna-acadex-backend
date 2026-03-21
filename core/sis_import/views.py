# SIS Import Views
"""
Django admin views for SIS CSV import functionality.
"""

import base64
from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib import messages
from django.urls import reverse

from .forms import SISImportForm, UserImportForm
from .processors import (
    CourseCSVProcessor,
    UserCSVProcessor,
    SectionCSVProcessor,
    EnrollmentCSVProcessor,
)


def sis_import_index(request):
    """SIS Import dashboard with links to all import types."""
    context = {
        'title': 'SIS Import',
        'import_types': [
            {
                'name': 'Courses',
                'description': 'Import courses (subjects) from CSV',
                'url_name': 'hna_acadex_admin:sis_import_courses',
                'icon': 'book',
            },
            {
                'name': 'Users',
                'description': 'Import students and teachers from CSV',
                'url_name': 'hna_acadex_admin:sis_import_users',
                'icon': 'person',
            },
            {
                'name': 'Sections',
                'description': 'Import class sections from CSV',
                'url_name': 'hna_acadex_admin:sis_import_sections',
                'icon': 'class',
            },
            {
                'name': 'Enrollments',
                'description': 'Import student enrollments from CSV',
                'url_name': 'hna_acadex_admin:sis_import_enrollments',
                'icon': 'school',
            },
        ],
    }
    return render(request, 'admin/sis_import/index.html', context)


def sis_import_courses(request):
    """Handle course CSV import."""
    processor = CourseCSVProcessor()

    if request.method == 'POST':
        action = request.POST.get('action', 'validate')

        if action == 'import':
            # Get stored CSV content from session
            csv_content_b64 = request.session.get('sis_import_courses_csv')
            if not csv_content_b64:
                messages.error(request, "Session expired. Please re-upload the CSV file.")
                return redirect('sis_import_courses')

            csv_content = base64.b64decode(csv_content_b64).decode('utf-8')

            # Create a file-like object from the stored content
            import io
            csv_file = io.StringIO(csv_content)

            # Execute import
            result = processor.execute_import(csv_file)

            # Clear session data
            request.session.pop('sis_import_courses_csv', None)
            request.session.pop('sis_import_courses_result', None)

            if result.success:
                messages.success(request, result.message)
            else:
                messages.error(request, result.message)

            context = {
                'title': 'Import Courses - Result',
                'result': result,
                'import_type': 'courses',
                'step': 'result',
            }
            return render(request, 'admin/sis_import/import_courses.html', context)

        else:  # action == 'validate'
            form = SISImportForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES['csv_file']

                # Read and store file content for later import
                csv_file.seek(0)
                csv_content = csv_file.read()
                if isinstance(csv_content, bytes):
                    csv_content = csv_content.decode('utf-8')

                # Store in session (base64 encoded)
                request.session['sis_import_courses_csv'] = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')

                # Validate
                import io
                csv_file.seek(0)
                validation_result = processor.validate_all(csv_file)

                # Store validation result for display
                request.session['sis_import_courses_result'] = {
                    'rows': [
                        {
                            'row_number': r.row_number,
                            'data': r.data,
                            'action': r.action,
                            'message': r.message,
                            'warnings': r.warnings,
                        }
                        for r in validation_result.rows
                    ],
                    'error_count': validation_result.error_count,
                    'warning_count': validation_result.warning_count,
                    'is_valid': validation_result.is_valid,
                }

                context = {
                    'title': 'Import Courses - Preview',
                    'form': form,
                    'validation_result': validation_result,
                    'import_type': 'courses',
                    'step': 'preview',
                }
                return render(request, 'admin/sis_import/import_courses.html', context)
    else:
        form = SISImportForm()

    context = {
        'title': 'Import Courses',
        'form': form,
        'import_type': 'courses',
        'required_headers': processor.required_headers,
        'optional_headers': processor.optional_headers,
        'step': 'upload',
    }
    return render(request, 'admin/sis_import/import_courses.html', context)


def sis_import_users(request):
    """Handle user CSV import."""
    processor = UserCSVProcessor()

    if request.method == 'POST':
        action = request.POST.get('action', 'validate')

        if action == 'import':
            # Get stored data from session
            csv_content_b64 = request.session.get('sis_import_users_csv')
            send_credentials = request.session.get('sis_import_users_send_credentials', False)

            if not csv_content_b64:
                messages.error(request, "Session expired. Please re-upload the CSV file.")
                return redirect('sis_import_users')

            csv_content = base64.b64decode(csv_content_b64).decode('utf-8')

            # Create a file-like object from the stored content
            import io
            csv_file = io.StringIO(csv_content)

            # Execute import
            result = processor.execute_import(csv_file, send_credentials=send_credentials)

            # Clear session data
            request.session.pop('sis_import_users_csv', None)
            request.session.pop('sis_import_users_send_credentials', None)
            request.session.pop('sis_import_users_result', None)

            if result.success:
                messages.success(request, result.message)
            else:
                messages.error(request, result.message)

            context = {
                'title': 'Import Users - Result',
                'result': result,
                'import_type': 'users',
                'send_credentials': send_credentials,
                'step': 'result',
            }
            return render(request, 'admin/sis_import/import_users.html', context)

        else:  # action == 'validate'
            form = UserImportForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES['csv_file']
                send_credentials = form.cleaned_data.get('send_credentials', False)

                # Read and store file content for later import
                csv_file.seek(0)
                csv_content = csv_file.read()
                if isinstance(csv_content, bytes):
                    csv_content = csv_content.decode('utf-8')

                # Store in session
                request.session['sis_import_users_csv'] = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')
                request.session['sis_import_users_send_credentials'] = send_credentials

                # Validate
                import io
                csv_file.seek(0)
                validation_result = processor.validate_all(csv_file)

                context = {
                    'title': 'Import Users - Preview',
                    'form': form,
                    'validation_result': validation_result,
                    'import_type': 'users',
                    'send_credentials': send_credentials,
                    'step': 'preview',
                }
                return render(request, 'admin/sis_import/import_users.html', context)
    else:
        form = UserImportForm()

    context = {
        'title': 'Import Users',
        'form': form,
        'import_type': 'users',
        'required_headers': processor.required_headers,
        'optional_headers': processor.optional_headers,
        'step': 'upload',
    }
    return render(request, 'admin/sis_import/import_users.html', context)


def sis_import_sections(request):
    """Handle section CSV import."""
    processor = SectionCSVProcessor()

    if request.method == 'POST':
        action = request.POST.get('action', 'validate')

        if action == 'import':
            # Get stored CSV content from session
            csv_content_b64 = request.session.get('sis_import_sections_csv')
            if not csv_content_b64:
                messages.error(request, "Session expired. Please re-upload the CSV file.")
                return redirect('sis_import_sections')

            csv_content = base64.b64decode(csv_content_b64).decode('utf-8')

            # Create a file-like object from the stored content
            import io
            csv_file = io.StringIO(csv_content)

            # Execute import
            result = processor.execute_import(csv_file)

            # Clear session data
            request.session.pop('sis_import_sections_csv', None)
            request.session.pop('sis_import_sections_result', None)

            if result.success:
                messages.success(request, result.message)
            else:
                messages.error(request, result.message)

            context = {
                'title': 'Import Sections - Result',
                'result': result,
                'import_type': 'sections',
                'step': 'result',
            }
            return render(request, 'admin/sis_import/import_sections.html', context)

        else:  # action == 'validate'
            form = SISImportForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES['csv_file']

                # Read and store file content for later import
                csv_file.seek(0)
                csv_content = csv_file.read()
                if isinstance(csv_content, bytes):
                    csv_content = csv_content.decode('utf-8')

                # Store in session
                request.session['sis_import_sections_csv'] = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')

                # Validate
                import io
                csv_file.seek(0)
                validation_result = processor.validate_all(csv_file)

                context = {
                    'title': 'Import Sections - Preview',
                    'form': form,
                    'validation_result': validation_result,
                    'import_type': 'sections',
                    'step': 'preview',
                }
                return render(request, 'admin/sis_import/import_sections.html', context)
    else:
        form = SISImportForm()

    context = {
        'title': 'Import Sections',
        'form': form,
        'import_type': 'sections',
        'required_headers': processor.required_headers,
        'optional_headers': processor.optional_headers,
        'step': 'upload',
    }
    return render(request, 'admin/sis_import/import_sections.html', context)


def sis_import_enrollments(request):
    """Handle enrollment CSV import."""
    processor = EnrollmentCSVProcessor()

    if request.method == 'POST':
        action = request.POST.get('action', 'validate')

        if action == 'import':
            # Get stored CSV content from session
            csv_content_b64 = request.session.get('sis_import_enrollments_csv')
            if not csv_content_b64:
                messages.error(request, "Session expired. Please re-upload the CSV file.")
                return redirect('sis_import_enrollments')

            csv_content = base64.b64decode(csv_content_b64).decode('utf-8')

            # Create a file-like object from the stored content
            import io
            csv_file = io.StringIO(csv_content)

            # Execute import
            result = processor.execute_import(csv_file)

            # Clear session data
            request.session.pop('sis_import_enrollments_csv', None)
            request.session.pop('sis_import_enrollments_result', None)

            if result.success:
                messages.success(request, result.message)
            else:
                messages.error(request, result.message)

            context = {
                'title': 'Import Enrollments - Result',
                'result': result,
                'import_type': 'enrollments',
                'step': 'result',
            }
            return render(request, 'admin/sis_import/import_enrollments.html', context)

        else:  # action == 'validate'
            form = SISImportForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES['csv_file']

                # Read and store file content for later import
                csv_file.seek(0)
                csv_content = csv_file.read()
                if isinstance(csv_content, bytes):
                    csv_content = csv_content.decode('utf-8')

                # Store in session
                request.session['sis_import_enrollments_csv'] = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')

                # Validate
                import io
                csv_file.seek(0)
                validation_result = processor.validate_all(csv_file)

                context = {
                    'title': 'Import Enrollments - Preview',
                    'form': form,
                    'validation_result': validation_result,
                    'import_type': 'enrollments',
                    'step': 'preview',
                }
                return render(request, 'admin/sis_import/import_enrollments.html', context)
    else:
        form = SISImportForm()

    context = {
        'title': 'Import Enrollments',
        'form': form,
        'import_type': 'enrollments',
        'required_headers': processor.required_headers,
        'optional_headers': processor.optional_headers,
        'step': 'upload',
    }
    return render(request, 'admin/sis_import/import_enrollments.html', context)


# Template download views

def download_courses_template(request):
    """Download CSV template for courses import."""
    processor = CourseCSVProcessor()
    csv_content = processor.get_template_csv()

    response = HttpResponse(csv_content, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="courses_import_template.csv"'
    return response


def download_users_template(request):
    """Download CSV template for users import."""
    processor = UserCSVProcessor()
    csv_content = processor.get_template_csv()

    response = HttpResponse(csv_content, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="users_import_template.csv"'
    return response


def download_sections_template(request):
    """Download CSV template for sections import."""
    processor = SectionCSVProcessor()
    csv_content = processor.get_template_csv()

    response = HttpResponse(csv_content, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sections_import_template.csv"'
    return response


def download_enrollments_template(request):
    """Download CSV template for enrollments import."""
    processor = EnrollmentCSVProcessor()
    csv_content = processor.get_template_csv()

    response = HttpResponse(csv_content, content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="enrollments_import_template.csv"'
    return response