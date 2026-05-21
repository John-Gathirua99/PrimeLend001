import os
import sys
import cv2

# Add project root to sys.path
PROJECT_ROOT = r"c:\Users\HP\Desktop\Ai_Loan_System"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ai_Loan_System.settings')
import django
django.setup()

from ml_engine.kyc_face import _load_image_from_file, _best_id_crop

def test_robust_crop(id_path, output_path):
    print(f"\n--- Testing Robust Face Extraction: {os.path.basename(id_path)} ---")
    
    # Load using the new EXIF-aware loader
    img = _load_image_from_file(id_path)
    if img is None:
        print("Error: Could not load image.")
        return
        
    print(f"Loaded Shape: {img.shape}")
    
    # Get the best crop using the new redesigned logic
    found, crop = _best_id_crop(img)
    
    cv2.imwrite(output_path, crop)
    print(f"Result: Face Found={found}")
    print(f"Saved crop to: {output_path} ({crop.shape[1]}x{crop.shape[0]})")

if __name__ == "__main__":
    test_robust_crop(r"media\ids\front\front_62.jpg", r"scratch\id_face_crop_v2.jpg")
