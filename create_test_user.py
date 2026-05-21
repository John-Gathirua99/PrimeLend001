import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ai_Loan_System.settings')
django.setup()

from django.contrib.auth.models import User
from accounts.models import UserProfile

def create_test_user():
    username = 'testuser123'
    password = 'password123'
    email = 'testuser@example.com'
    
    if User.objects.filter(username=username).exists():
        user = User.objects.get(username=username)
        user.set_password(password)
        user.save()
    else:
        user = User.objects.create_user(username=username, email=email, password=password)
        user.first_name = 'Test'
        user.last_name = 'User'
        user.save()
        
    profile, created = UserProfile.objects.get_or_create(user=user)
    profile.is_phone_verified = True
    profile.phone_number = '254712345678'
    profile.national_id = '12345678'
    profile.date_of_birth = '1990-01-01'
    profile.employment_status = 'Employed'
    profile.monthly_income = 50000.00
    profile.save()
    
    print(f"User created: {username} / {password}")

if __name__ == '__main__':
    create_test_user()
