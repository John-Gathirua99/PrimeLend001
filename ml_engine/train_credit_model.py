import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

# Example training dataset (replace with real data later)
data = pd.read_csv("ml_engine/data/credit_training_data.csv")

X = data.drop("approved", axis=1)
y = data["approved"]

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

X_train, X_test, y_train, y_test = train_test_split(
    X_scaled, y, test_size=0.2, random_state=42
)

model = RandomForestClassifier(
    n_estimators=300,
    max_depth=12,
    min_samples_split=5
)

model.fit(X_train, y_train)

joblib.dump(model, "ml_engine/credit_model.pkl")
joblib.dump(scaler, "ml_engine/credit_scaler.pkl")

print("Credit model trained successfully")





