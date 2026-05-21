import os
import sys
import logging
import base64
from django.core.files.base import ContentFile

# Add project root to sys.path
PROJECT_ROOT = r"c:\Users\HP\Desktop\Ai_Loan_System"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ai_Loan_System.settings')
import django
django.setup()

from ml_engine.id_verify import verify_id_document
from ml_engine.kyc_face import verify_face_kyc

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_full_kyc(id_path, selfie_path, submitted_id, account_name):
    print(f"\n{'='*60}")
    print(f" FULL KYC PIPELINE TEST")
    print(f"{'='*60}")
    
    # 1. TEST OCR / ID EXTRACTION
    print(f"\n[STEP 1] Testing ID Extraction...")
    with open(id_path, "rb") as f:
        id_image_file = ContentFile(f.read(), name=os.path.basename(id_path))
        id_result = verify_id_document(id_image_file, submitted_id, account_name)
        
        print(f" - Extracted ID: {id_result.extracted_id} (Match: {id_result.id_number_match})")
        print(f" - Extracted Name: {id_result.extracted_name} (Match: {id_result.name_match})")
    
    # 2. TEST FACE VERIFICATION
    print(f"\n[STEP 2] Testing Face Verification...")
    with open(selfie_path, "rb") as f:
        selfie_b64 = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
        
        # We pass the relative path to verify_face_kyc as it expects an ImageField-like object
        id_rel_path = os.path.relpath(id_path, start=os.path.join(PROJECT_ROOT, "media"))
        face_result = verify_face_kyc(selfie_b64, id_rel_path)
        
        print(f" - Face Match:  {'True' if face_result.match else 'False'}")
        print(f" - Distance:    {face_result.distance:.4f}")
        print(f" - Confidence:  {face_result.confidence:.1%}")
    
    print(f"\n{'='*60}")
    if id_result.id_number_match and id_result.name_match and face_result.match:
        print(" SUCCESS: ALL KYC STEPS PASSED")
    else:
        print(" FAILURE: SOME KYC STEPS FAILED")
    print(f"{'='*60}")

if __name__ == "__main__":
    # Using your actual images for verification
    id_img = r"c:\Users\HP\Desktop\Ai_Loan_System\media\ids\front\front_62.jpg"
    selfie_img = r"c:\Users\HP\Desktop\Ai_Loan_System\media\kyc\selfies\kyc_selfie_107.jpg"
    
    test_full_kyc(id_img, selfie_img, "41292983", "JOHN GATHIRUA MWANGI")
