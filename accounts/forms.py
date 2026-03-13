from django import forms
from django.contrib.auth.models import User
from .models import UserProfile


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model  = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'First name'}),
            'last_name':  forms.TextInput(attrs={'placeholder': 'Last name'}),
            'email':      forms.EmailInput(attrs={'placeholder': 'Email address'}),
        }


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model  = UserProfile
        fields = [
            # Existing
            'full_name', 'age', 'address', 'postal_code', 'county',
            # New loan-required
            'phone_number', 'national_id', 'date_of_birth',
            'employment_status', 'monthly_income',
        ]
        widgets = {
            'full_name':         forms.TextInput(attrs={'placeholder': 'Full legal name'}),
            'age':               forms.NumberInput(attrs={'placeholder': 'e.g. 28', 'min': 18, 'max': 80}),
            'address':           forms.TextInput(attrs={'placeholder': 'Street address'}),
            'postal_code':       forms.TextInput(attrs={'placeholder': 'e.g. 00100'}),
            'county':            forms.TextInput(attrs={'placeholder': 'e.g. Nairobi'}),
            'phone_number':      forms.TextInput(attrs={'placeholder': '+254712345678'}),
            'national_id':       forms.TextInput(attrs={'placeholder': 'e.g. 12345678'}),
            'date_of_birth':     forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'employment_status': forms.Select(),
            'monthly_income':    forms.NumberInput(attrs={'placeholder': 'e.g. 45000', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Format date for HTML date input
        if self.instance and self.instance.date_of_birth:
            self.initial['date_of_birth'] = self.instance.date_of_birth.strftime('%Y-%m-%d')