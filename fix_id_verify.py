"""
Run this script from your project folder:
  python fix_id_verify.py
It will patch id_verify.py in-place.
"""
import re, os

path = r"C:\Users\HP\Desktop\Ai_Loan_System\ml_engine\id_verify.py"
content = open(path, "r", encoding="utf-8").read()

changes = 0

# ── Fix 1: Remove adaptive threshold, replace with CLAHE ─────
pattern1 = re.compile(
    r"        # Denoise\n        gray = cv2\.fastNlMeansDenoising.*?return PILImage\.fromarray\(processed\)",
    re.DOTALL
)
replacement1 = """\
        # CLAHE - no binarization, preserves photo detail
        clahe    = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        kernel   = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        result   = cv2.filter2D(enhanced, -1, kernel)

        from PIL import Image as PILImage
        return PILImage.fromarray(result)"""

if pattern1.search(content):
    content = pattern1.sub(replacement1, content)
    print("Fix 1 applied: CLAHE replaces adaptiveThreshold")
    changes += 1
elif "adaptiveThreshold" not in content:
    print("Fix 1 skipped: adaptiveThreshold already removed")
else:
    print("Fix 1 FAILED: pattern not found")

# ── Fix 2: Disable deskew call ────────────────────────────────
pattern2 = re.compile(
    r"        # Step 1: Deskew.*?\n        img = _deskew\(img\)\n",
    re.DOTALL
)
replacement2 = "        # Deskew disabled - warps hand-held photos\n        # img = _deskew(img)\n"

if pattern2.search(content):
    content = pattern2.sub(replacement2, content)
    print("Fix 2 applied: deskew disabled")
    changes += 1
elif "# img = _deskew" in content:
    print("Fix 2 skipped: deskew already disabled")
else:
    # try simpler pattern
    pattern2b = re.compile(r"        img = _deskew\(img\)\n")
    if pattern2b.search(content):
        content = pattern2b.sub("        # img = _deskew(img)  # disabled\n", content)
        print("Fix 2 applied (simple): deskew disabled")
        changes += 1
    else:
        print("Fix 2 FAILED: deskew call not found")

# ── Fix 3: Replace _next_line_value body ─────────────────────
pattern3 = re.compile(
    r"(def _next_line_value\(text: str, label: str\) -> Optional\[str\]:.*?\"\"\".*?\"\"\")\n.*?return None",
    re.DOTALL
)

new_body = '''def _next_line_value(text: str, label: str) -> Optional[str]:
    """
    Kenyan IDs put label on one line, value on the NEXT line:
      SURNAME       <- label
      MWANGI        <- value
      GIVEN NAME    <- label
      JOHN GATHIRUA <- value
    """
    SKIP = {
        "REPUBLIC", "KENYA", "JAMHURI", "NATIONAL", "IDENTITY", "CARD",
        "KITAMBULISHO", "TAIFA", "MEANT", "PATA", "OF", "CHA", "YA",
        "SURNAME", "GIVEN", "NAME", "NAMES", "SEX", "DATE", "BIRTH",
        "PLACE", "ISSUE", "EXPIRY", "NATIONALITY", "NAMBA", "ID",
        "SERIAL", "MUNICIPALITY", "AND", "THE", "JINSIA",
    }
    lines = [l.strip() for l in text.upper().split("\\n")]
    for i, line in enumerate(lines):
        if label.upper() in line:
            for j in range(i + 1, min(i + 5, len(lines))):
                val = lines[j].strip()
                if not val:
                    continue
                val_clean = re.sub(r"[^A-Z\\s]", "", val).strip()
                if len(val_clean) < 2:
                    continue
                val_words = set(val_clean.split())
                if val_words.issubset(SKIP):
                    continue
                if any(phrase in val_clean for phrase in [
                    "REPUBLIC OF KENYA", "NATIONAL IDENTITY",
                    "JAMHURI YA KENYA", "KITAMBULISHO CHA TAIFA",
                ]):
                    continue
                return val_clean
    return None'''

if pattern3.search(content):
    content = pattern3.sub(new_body, content)
    print("Fix 3 applied: _next_line_value updated")
    changes += 1
elif "SKIP = {" in content:
    print("Fix 3 skipped: _next_line_value already updated")
else:
    print("Fix 3 FAILED: _next_line_value pattern not found")

# ── Save ──────────────────────────────────────────────────────
if changes > 0:
    open(path, "w", encoding="utf-8").write(content)
    print(f"\nSaved {changes} fix(es) to {path}")
else:
    print("\nNo changes needed or all fixes already applied")

# ── Verify ────────────────────────────────────────────────────
content2 = open(path, "r", encoding="utf-8").read()
print("\nVerification:")
print("  adaptiveThreshold:", "adaptiveThreshold" in content2)
print("  CLAHE:            ", "createCLAHE" in content2)
print("  deskew disabled:  ", "# img = _deskew" in content2 or "deskew disabled" in content2)
print("  SKIP set:         ", "SKIP = {" in content2)