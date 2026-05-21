import os
import sys
import logging

# Add project root to sys.path
PROJECT_ROOT = r"c:\Users\HP\Desktop\Ai_Loan_System"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ai_Loan_System.settings')
import django
django.setup()

from ml_engine.kyc_face import verify_face_kyc
import base64

# Configure logging to see EVERYTHING
logging.basicConfig(level=logging.INFO)

def diagnose_kyc():
    id_img = r"ids\front\front_62.jpg"
    selfie_path = r"media\kyc\selfies\kyc_selfie_107.jpg"
    
    with open(selfie_path, "rb") as f:
        selfie_b64 = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    
    # Run verification
    print("\n--- Starting Verification Diagnosis ---")
    result = verify_face_kyc(selfie_b64, id_img)
    
    print(f"\nResult: match={result.match}, distance={result.distance}, confidence={result.confidence}")
    print(f"Error: {result.error}")
    print(f"Selfie Face: {result.selfie_face_found}, ID Face: {result.id_face_found}")

if __name__ == "__main__":
    diagnose_kyc()
