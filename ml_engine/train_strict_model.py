import pandas as pd
import numpy as np
import joblib
import json
import os
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

np.random.seed(42)
N = 500

os.makedirs("ml_engine/model", exist_ok=True)
os.makedirs("ml_engine/data", exist_ok=True)

# ─────────────────────────────────────────────
# 1. CREDIT TRAINING DATA — strict approval logic
# ─────────────────────────────────────────────
def generate_credit_data(n):
    ages = np.random.randint(21, 60, n)  # no teens
    monthly_income = np.random.randint(15000, 300000, n)
    repayment_period = np.random.choice([3, 6, 9, 12, 18, 24, 36], n)
    credit_history = np.random.choice([0, 1], n, p=[0.4, 0.6])
    previous_loan_count = np.random.randint(0, 10, n)
    on_time_repayment_count = np.array([
        np.random.randint(0, max(1, prev + 1)) for prev in previous_loan_count
    ])
    past_default_flag = np.random.choice([0, 1], n, p=[0.65, 0.35])
    recent_application_count = np.random.randint(0, 8, n)
    fraud_score = np.round(np.random.beta(2, 5, n), 3)

    qualified_amount = monthly_income * 0.4
    debt_to_income_ratio = np.round(qualified_amount / (monthly_income + 1), 3)

    # STRICT score — harder to pass
    score = (
        (credit_history * 3.0)                                          # must have good credit
        + (on_time_repayment_count / (previous_loan_count + 1) * 2.0)  # repayment record matters
        - (past_default_flag * 4.0)                                     # any default = heavy penalty
        - (fraud_score * 5.0)                                           # fraud risk kills application
        - (recent_application_count * 0.6)                              # velocity penalty
        - (debt_to_income_ratio * 3.0)                                  # high DTI penalised
        + (np.log1p(monthly_income) * 0.15)                             # income helps slightly
        - 2.5                                                            # base difficulty offset
    )
    prob = 1 / (1 + np.exp(-score))
    # Use high threshold so only ~25-30% approved
    approved = (prob > np.random.uniform(0.55, 0.85, n)).astype(int)

    return pd.DataFrame({
        "age": ages,
        "monthly_income": monthly_income,
        "repayment_period": repayment_period,
        "credit_history": credit_history,
        "debt_to_income_ratio": debt_to_income_ratio,
        "past_default_flag": past_default_flag,
        "previous_loan_count": previous_loan_count,
        "on_time_repayment_count": on_time_repayment_count,
        "fraud_score": fraud_score,
        "recent_application_count": recent_application_count,
        "approved": approved,
    })

credit_df = generate_credit_data(N)
credit_df.to_csv("ml_engine/data/credit_training_data.csv", index=False)
print(f"Credit data: {N} rows | Approval rate: {credit_df['approved'].mean():.1%}")

# ─────────────────────────────────────────────
# 2. LOAN TRAINING DATA — penalise unemployed/students
# ─────────────────────────────────────────────
def generate_loan_data(n):
    employment_options = ["Employed", "Self-employed", "Unemployed", "Student"]
    employment_status = np.random.choice(employment_options, n, p=[0.55, 0.25, 0.12, 0.08])
    ages = np.random.randint(21, 60, n)
    monthly_income = np.where(
        employment_status == "Unemployed", np.random.randint(0, 8000, n),
        np.where(employment_status == "Student", np.random.randint(0, 12000, n),
        np.random.randint(20000, 300000, n))
    )
    loan_amount = monthly_income * np.random.uniform(0.5, 5, n)
    repayment_period = np.random.choice([6, 12, 18, 24, 36], n)
    credit_history = np.random.choice([0, 1], n, p=[0.35, 0.65])

    emp_penalty = np.where(employment_status == "Unemployed", -3.5,
                  np.where(employment_status == "Student", -2.5,
                  np.where(employment_status == "Self-employed", -0.5, 0)))

    score = (
        (credit_history * 2.0)
        + (np.log1p(monthly_income) * 0.25)
        - (loan_amount / (monthly_income + 1) * 0.8)
        + (repayment_period * 0.01)
        + emp_penalty
        - 3.0   # strict base offset
    )
    prob = 1 / (1 + np.exp(-score))
    approved = (prob > np.random.uniform(0.5, 0.85, n)).astype(int)

    return pd.DataFrame({
        "age": ages,
        "employment_status": employment_status,
        "monthly_income": monthly_income,
        "loan_amount": loan_amount.astype(int),
        "repayment_period": repayment_period,
        "credit_history": credit_history,
        "approved": approved,
    })

loan_df = generate_loan_data(N)
loan_df.to_csv("ml_engine/data/loan_data.csv", index=False)
print(f"Loan data: {N} rows | Approval rate: {loan_df['approved'].mean():.1%}")

# ─────────────────────────────────────────────
# 3. FRAUD DATA — more sensitive detection
# ─────────────────────────────────────────────
def generate_fraud_data(n):
    ages = np.random.randint(18, 65, n)
    monthly_income = np.random.randint(5000, 250000, n)
    loan_amount = monthly_income * np.random.uniform(0.3, 4, n)
    repayment_period = np.random.choice([6, 12, 24, 36], n)
    credit_history = np.random.choice([0, 1], n, p=[0.4, 0.6])
    device_change_count = np.random.choice([0,1,2,3,4,5,6], n, p=[0.45,0.2,0.12,0.1,0.07,0.04,0.02])
    ip_change_count = np.random.choice([0,1,2,3,4,5,6], n, p=[0.45,0.2,0.12,0.1,0.07,0.04,0.02])
    accounts_per_phone = np.random.choice([1,2,3,4,5], n, p=[0.55,0.22,0.12,0.07,0.04])
    recent_applications = np.random.choice([0,1,2,3,4,5], n, p=[0.45,0.2,0.15,0.1,0.06,0.04])
    id_reuse_flag = np.random.choice([0,1], n, p=[0.82,0.18])
    income_age_ratio = monthly_income / (ages + 1)

    # More sensitive fraud scoring
    fraud_score = (
        (device_change_count * 0.18)
        + (ip_change_count * 0.18)
        + ((accounts_per_phone - 1) * 0.25)
        + (recent_applications * 0.18)
        + (id_reuse_flag * 0.6)
        + (np.where(income_age_ratio > 12000, 0.25, 0))
        + np.random.normal(0, 0.04, n)
    )
    fraud = (fraud_score > np.random.uniform(0.4, 0.9, n)).astype(int)

    return pd.DataFrame({
        "age": ages,
        "monthly_income": monthly_income,
        "loan_amount": loan_amount.astype(int),
        "repayment_period": repayment_period,
        "credit_history": credit_history,
        "device_change_count": device_change_count,
        "ip_change_count": ip_change_count,
        "accounts_per_phone": accounts_per_phone,
        "recent_applications": recent_applications,
        "id_reuse_flag": id_reuse_flag,
        "income_age_ratio": np.round(income_age_ratio, 2),
        "fraud": fraud,
    })

fraud_df = generate_fraud_data(N)
fraud_df.to_csv("ml_engine/data/fraud_training_data.csv", index=False)
print(f"Fraud data: {N} rows | Fraud rate: {fraud_df['fraud'].mean():.1%}")

# ─────────────────────────────────────────────
# TRAIN: CREDIT MODEL
# ─────────────────────────────────────────────
print("\n── Training Credit Model ──")
X = credit_df.drop("approved", axis=1)
y = credit_df["approved"]
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)
X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)

credit_model = GradientBoostingClassifier(
    n_estimators=300, max_depth=5, learning_rate=0.08,
    min_samples_split=8, random_state=42
)
credit_model.fit(X_train, y_train)
preds = credit_model.predict(X_test)
print(f"Accuracy: {accuracy_score(y_test, preds):.2%}")
print(classification_report(y_test, preds))

joblib.dump(credit_model, "ml_engine/credit_model.pkl")
joblib.dump(scaler, "ml_engine/credit_scaler.pkl")
joblib.dump(list(X.columns), "ml_engine/credit_features.pkl")
print("✅ Credit model saved")

# ─────────────────────────────────────────────
# TRAIN: LOAN MODEL
# ─────────────────────────────────────────────
print("\n── Training Loan Model ──")
le = LabelEncoder()
loan_df["employment_status"] = le.fit_transform(loan_df["employment_status"])
X = loan_df.drop("approved", axis=1)
y = loan_df["approved"]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

loan_model = RandomForestClassifier(
    n_estimators=300, max_depth=8, min_samples_split=8,
    class_weight={0: 1.5, 1: 1.0},   # weight rejections higher
    random_state=42
)
loan_model.fit(X_train, y_train)
preds = loan_model.predict(X_test)
print(f"Accuracy: {accuracy_score(y_test, preds):.2%}")
print(classification_report(y_test, preds))

joblib.dump(loan_model, "ml_engine/model/loan_model.pkl")
joblib.dump(le, "ml_engine/model/employment_encoder.pkl")
print("✅ Loan model saved")

# ─────────────────────────────────────────────
# TRAIN: FRAUD MODEL
# ─────────────────────────────────────────────
print("\n── Training Fraud Model ──")
X = fraud_df.drop("fraud", axis=1)
y = fraud_df["fraud"]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

fraud_model = RandomForestClassifier(
    n_estimators=300, max_depth=10, min_samples_split=4,
    class_weight={0: 1.0, 1: 1.8},   # weight fraud detection higher
    random_state=42
)
fraud_model.fit(X_train, y_train)
preds = fraud_model.predict(X_test)
print(f"Accuracy: {accuracy_score(y_test, preds):.2%}")
print(classification_report(y_test, preds))

feature_importance = dict(zip(X.columns, fraud_model.feature_importances_))
with open("ml_engine/fraud_feature_importance.json", "w") as f:
    json.dump(feature_importance, f, indent=2)

joblib.dump(fraud_model, "ml_engine/fraud_model.pkl")
joblib.dump(list(X.columns), "ml_engine/fraud_features.pkl")
print("✅ Fraud model saved")

print("\n✅ All strict models trained successfully.")