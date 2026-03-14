try:
    import pandas
except ImportError:
    pandas = None  # not available in production as pd
try:
    import joblib
except ImportError:
    joblib = None  # not available in production
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import json

data = pd.DataFrame({

    'age': [22, 45, 30, 19, 40, 28, 50, 23],
    'monthly_income': [20000, 150000, 50000, 1000000, 80000, 30000, 200000, 15000],
    'loan_amount': [10000, 50000, 20000, 700000, 40000, 15000, 100000, 8000],
    'repayment_period': [30, 90, 60, 7, 120, 30, 180, 14],
    'credit_history': [1, 1, 0, 0, 1, 0, 1, 0],

    'device_change_count': [0, 1, 0, 5, 0, 2, 0, 4],
    'ip_change_count': [0, 0, 1, 6, 0, 1, 0, 3],
    'accounts_per_phone': [1, 1, 1, 3, 1, 2, 1, 4],
    'recent_applications': [0, 1, 0, 5, 0, 2, 0, 3],
    'id_reuse_flag': [0, 0, 0, 1, 0, 1, 0, 1],
    'income_age_ratio': [900, 3300, 1600, 52000, 2000, 1070, 4000, 650],

    # Target variable (1 = fraud, 0 = safe)
    'fraud': [0, 0, 0, 1, 0, 1, 0, 1]
})



X = data.drop("fraud", axis=1)
y = data["fraud"]



model = RandomForestClassifier()
model.fit(X, y)


feature_importance = dict(
    zip(X.columns, model.feature_importances_)
)

with open("ml_engine/fraud_feature_importance.json", "w") as f:
    json.dump(feature_importance, f)



joblib.dump(model, "ml_engine/fraud_model.pkl")

print("Fraud model trained and saved successfully!")
