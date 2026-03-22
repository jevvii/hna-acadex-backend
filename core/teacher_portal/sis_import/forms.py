# Teacher Portal SIS Import Forms
"""
Forms for SIS import in the teacher portal.
"""

from django import forms


class SISImportForm(forms.Form):
    """Form for CSV file upload."""

    csv_file = forms.FileField(
        label='CSV File',
        help_text='Upload a CSV file to import data.',
        widget=forms.FileInput(attrs={'accept': '.csv'})
    )