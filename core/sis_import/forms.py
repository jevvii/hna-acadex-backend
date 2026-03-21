# SIS Import Forms
"""
Django forms for CSV import functionality.
"""

from django import forms


class SISImportForm(forms.Form):
    """Base form for CSV file uploads."""

    csv_file = forms.FileField(
        label="CSV File",
        help_text="Upload a CSV file with the data to import. Maximum 500 rows.",
        widget=forms.FileInput(attrs={
            'accept': '.csv',
            'class': 'csv-file-input',
        })
    )

    def clean_csv_file(self):
        """Validate the uploaded CSV file."""
        csv_file = self.cleaned_data.get('csv_file')

        if not csv_file:
            raise forms.ValidationError("Please select a CSV file")

        # Check file extension
        if not csv_file.name.lower().endswith('.csv'):
            raise forms.ValidationError("File must have a .csv extension")

        # Check file size (limit to 5MB)
        if csv_file.size > 5 * 1024 * 1024:
            raise forms.ValidationError("File size must be less than 5MB")

        # Check if file is empty
        if csv_file.size == 0:
            raise forms.ValidationError("The uploaded file is empty")

        # Try to decode and validate it's actually CSV
        try:
            csv_file.seek(0)
            content = csv_file.read()
            if isinstance(content, bytes):
                content.decode('utf-8')
            csv_file.seek(0)
        except UnicodeDecodeError:
            raise forms.ValidationError("File must be UTF-8 encoded")

        return csv_file


class UserImportForm(SISImportForm):
    """Form for user CSV imports with option to send credentials."""

    send_credentials = forms.BooleanField(
        required=False,
        initial=True,
        label="Send login credentials via email",
        help_text="If checked, login credentials will be sent to each user's personal email address."
    )