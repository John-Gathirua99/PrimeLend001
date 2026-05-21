import os
import sys

# Add project root to sys.path
PROJECT_ROOT = r"c:\Users\HP\Desktop\Ai_Loan_System"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ai_Loan_System.settings')
import django
django.setup()

from django.contrib.auth.models import User
from accounts.models import UserProfile

def clear_face_data(email):
    print(f"--- Clearing Face Data for: {email} ---")
    try:
        user = User.objects.get(email=email)
        profile = UserProfile.objects.get(user=user)
        
        profile.face_embedding = ""
        profile.face_kyc_verified = False
        profile.save(update_fields=['face_embedding', 'face_kyc_verified'])
        
        print(f"SUCCESS: Face registry cleared for user {user.username} ({email})")
    except User.DoesNotExist:
        print(f"ERROR: User with email {email} not found.")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    if len(sys.path) > 1 and sys.argv[1:]:
        target_email = sys.argv[1]
    else:
        target_email = "server@gmail.com" # Default for your test case
        
    clear_face_data(target_email)
