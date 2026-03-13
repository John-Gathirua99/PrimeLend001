import re

path = r"C:\Users\HP\Desktop\Ai_Loan_System\ml_engine\id_verify.py"
content = open(path, "r", encoding="utf-8").read()
lines = content.split("\n")

# ── Fix 2: disable deskew ─────────────────────────────────────
fixed2 = False
for i, line in enumerate(lines):
    if "_deskew" in line and "def " not in line and "#" not in line:
        print(f"Found deskew call at line {i+1}: {repr(line)}")
        lines[i] = lines[i].replace("img = _deskew(img)", "# img = _deskew(img)  # disabled")
        print(f"  -> replaced with: {repr(lines[i])}")
        fixed2 = True

if not fixed2:
    print("Deskew call not found - searching for 'deskew':")
    for i, line in enumerate(lines):
        if "deskew" in line.lower():
            print(f"  line {i+1}: {repr(line)}")

# ── Fix 3: replace _next_line_value ───────────────────────────
content2 = "\n".join(lines)

# Find start and end of _next_line_value function
start = content2.find("def _next_line_value(")
if start == -1:
    print("\n_next_line_value NOT FOUND in file!")
else:
    # Find next function def after it
    end = content2.find("\ndef ", start + 10)
    print(f"\n_next_line_value found at char {start}, next def at {end}")
    print("Current function body:")
    print(content2[start:end])
    print("\n--- REPLACING ---")

    new_func = '''def _next_line_value(text: str, label: str):
    """
    Kenyan IDs put label on one line, value on the NEXT line.
    SURNAME -> MWANGI, GIVEN NAME -> JOHN GATHIRUA
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

    content2 = content2[:start] + new_func + content2[end:]
    print("Fix 3 applied")

# ── Save ──────────────────────────────────────────────────────
open(path, "w", encoding="utf-8").write(content2)
print("\nSaved!")
print("\nVerification:")
c = open(path, encoding="utf-8").read()
print("  adaptiveThreshold:", "adaptiveThreshold" in c)
print("  CLAHE:            ", "createCLAHE" in c)
print("  deskew disabled:  ", "# img = _deskew" in c)
print("  SKIP set:         ", 'SKIP = {' in c)