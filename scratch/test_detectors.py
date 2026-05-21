from deepface import DeepFace
import cv2
import os

id_path = r"media\ids\front\front_62.jpg"
if os.path.exists(id_path):
    # Try on the LEFT crop (where we expect it)
    print("\n--- Testing on LEFT CROP ---")
    img = cv2.imread(id_path)
    h, w = img.shape[:2]
    # Check if we need rotation ( raw cv2 rotate if portrait)
    if h > w:
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        h, w = img.shape[:2]
    
    left_crop = img[0:h, 0:int(w*0.42)]
    crop_path = r"scratch\test_left_crop.jpg"
    cv2.imwrite(crop_path, left_crop)
    
    # Try mtcnn on the crop
    try:
        result = DeepFace.extract_faces(img_path=crop_path, detector_backend='mtcnn', enforce_detection=True)
        print(f"Faces found in LEFT CROP (mtcnn): {len(result)}")
        for i, f in enumerate(result):
            print(f" - Face {i}: {f['facial_area']}")
    except Exception as e:
        print(f"MTCNN on crop failed: {e}")
