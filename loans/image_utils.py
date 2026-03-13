"""
Image compression utilities for ID documents and selfies.
Resizes and compresses images on upload for consistent quality and size.
"""
import io
import logging
from PIL import Image
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

# ID document settings — landscape card format
ID_MAX_WIDTH  = 1200
ID_MAX_HEIGHT = 800
ID_QUALITY    = 88  # JPEG quality — good balance of size vs clarity

# Selfie settings — portrait
SELFIE_MAX_WIDTH  = 600
SELFIE_MAX_HEIGHT = 600
SELFIE_QUALITY    = 90


def compress_id_image(image_file, filename=None):
    """
    Resize and compress an ID document image.
    Returns a ContentFile ready to save to ImageField.
    """
    try:
        img = Image.open(image_file)

        # Convert RGBA/palette to RGB (JPEG doesn't support alpha)
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1])
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Auto-rotate based on EXIF orientation
        try:
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        # Resize maintaining aspect ratio
        img.thumbnail((ID_MAX_WIDTH, ID_MAX_HEIGHT), Image.LANCZOS)

        # Save compressed
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=ID_QUALITY, optimize=True)
        output.seek(0)

        fname = filename or 'id_document.jpg'
        if not fname.lower().endswith('.jpg'):
            fname = fname.rsplit('.', 1)[0] + '.jpg'

        size_kb = len(output.getvalue()) / 1024
        logger.info(f"ID image compressed: {img.size[0]}x{img.size[1]}px, {size_kb:.0f}KB")

        return ContentFile(output.read(), name=fname)

    except Exception as e:
        logger.error(f"ID image compression failed: {e}")
        # Return original file unchanged if compression fails
        image_file.seek(0)
        return image_file


def compress_selfie(base64_str, filename='kyc_selfie.jpg'):
    """
    Decode a base64 selfie, resize and compress it.
    Returns a ContentFile ready to save to ImageField.
    """
    import base64

    try:
        # Strip data URI prefix
        if ',' in base64_str:
            base64_str = base64_str.split(',')[1]

        img_bytes = base64.b64decode(base64_str)
        img = Image.open(io.BytesIO(img_bytes))

        if img.mode != 'RGB':
            img = img.convert('RGB')

        img.thumbnail((SELFIE_MAX_WIDTH, SELFIE_MAX_HEIGHT), Image.LANCZOS)

        output = io.BytesIO()
        img.save(output, format='JPEG', quality=SELFIE_QUALITY, optimize=True)
        output.seek(0)

        size_kb = len(output.getvalue()) / 1024
        logger.info(f"Selfie compressed: {img.size[0]}x{img.size[1]}px, {size_kb:.0f}KB")

        return ContentFile(output.read(), name=filename)

    except Exception as e:
        logger.error(f"Selfie compression failed: {e}")
        return None