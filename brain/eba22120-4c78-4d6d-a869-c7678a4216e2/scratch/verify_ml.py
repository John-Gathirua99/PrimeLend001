import os
import sys

# Add project root to path (3 levels up from brain/<id>/scratch/)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ai_Loan_System.settings')
try:
    import django
    django.setup()
except Exception as setup_err:
    print(f"[Django setup skipped: {setup_err}]")

from ml_engine.fraud_predict import detect_fraud
from ml_engine.credit_predict import predict_credit

test_features = {
    "age": 25,
    "monthly_income": 50000,
    "loan_amount": 10000,
    "repayment_period": 6,
    "credit_history": 1,
    "device_change_count": 1,
    "ip_change_count": 1,
    "accounts_per_phone": 1,
    "recent_application_count": 0,
    "id_reuse_flag": 0,
    "kyc_face_verified": True,
    "ocr_id_verified": True,
    "ocr_name_match": True,
    "mrz_valid": True,
    "ela_score": 0.1,
    "night_application": 0,
    "vpn_usage": 0,
    "failed_kyc_attempts": 0,
    "multiple_ids_flag": 0,
    "app_completion_seconds": 120,
    "same_day_multiple_apps": 0
}

print("--- Testing Fraud Prediction ---")
try:
    score, flag, reasons = detect_fraud(test_features)
    print(f"Fraud Score: {score}")
    print(f"Fraud Flag: {flag}")
    print(f"Reasons: {reasons}")
    print("SUCCESS: Fraud prediction worked without feature name errors.")
except Exception as e:
    print(f"FAILED: Fraud prediction error: {e}")

print("\n--- Testing Credit Prediction ---")
try:
    # Add fields specific to credit
    test_features.update({
        "debt_to_income_ratio": 0.2,
        "past_default_flag": 0,
        "previous_loan_count": 0,
        "on_time_repayment_count": 0,
        "fraud_score": score if 'score' in locals() else 0.1,
        "id_reuse": 0
    })
    prediction = predict_credit(test_features)
    print(f"Credit Probability: {prediction['probability']}")
    print(f"Credit Decision: {prediction['status']}")
    print("SUCCESS: Credit prediction worked without feature name errors.")
except Exception as e:
    print(f"FAILED: Credit prediction error: {e}")
