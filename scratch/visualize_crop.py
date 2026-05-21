import cv2
import os

def visualize_kyc_crop(id_path, output_path):
    if not os.path.exists(id_path):
        print(f"Error: {id_path} not found.")
        return

    # Load image
    img = cv2.imread(id_path)
    h, w = img.shape[:2]

    # The same logic used in kyc_face.py and kyc_views.py
    # 1. Rotate if portrait (typical for mobile uploads)
    if h > w:
        print("Portrait detected - rotating for extraction...")
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        h, w = img.shape[:2]

    # 2. Extract the Face Region (Left 40% of the card)
    # This is where the face is located on Kenyan IDs
    face_crop = img[0:h, 0:int(w*0.42)]

    # Save the result
    cv2.imwrite(output_path, face_crop)
    print(f"SUCCESS: Face crop saved to {output_path}")
    print(f"Original: {w}x{h} | Crop: {face_crop.shape[1]}x{face_crop.shape[0]}")

if __name__ == "__main__":
    id_img = r"media\ids\front\front_62.jpg"
    out_img = r"scratch\id_face_crop.jpg"
    visualize_kyc_crop(id_img, out_img)
