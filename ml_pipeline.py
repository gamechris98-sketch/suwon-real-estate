import csv
import os
import re
import datetime
import json
import numpy as np
import polars as pl
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error
import torch
import torch.nn as nn
import torch.optim as optim

# Define target apartments
APT_FILTERS = {
    'mangpo_hillstate':    ('망포동', '힐스테이트영통', 2140),
    'mangpo_ipark':        ('망포동', '아이파크캐슬1단지', 1783),
    'mangpo_skview':       ('망포동', '영통SKVIEW', 710),
    'mangpo_sujain':       ('망포동', '한양수자인', 530),
    'yeongtong_edupark':   ('영통동', '에듀파크', 1279),
    'yeongtong_dongbo':    ('영통동', '신나무실동보', 836),
    'yeongtong_shinmyung': ('영통동', '신나무실신명', 384),
    'maegyo_skview':       ('매교동', '푸르지오SKVIEW', 3603),
    'maegyo_hillstate':    ('매교동', '힐스테이트푸르지오', 2586),
}

# 1. Load data
csv_path = "suwon_real_estate.csv"
if not os.path.exists(csv_path):
    csv_path = os.path.join(os.path.dirname(__file__), "suwon_real_estate.csv")

print(f"Loading real estate data from {csv_path}...")

raw_data = []
with open(csv_path, 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        raw_data.append(row)

print(f"Loaded {len(raw_data)} raw transaction records.")

# 2. Extract features
X_list = []
y_list = []

# Date to float helper
def date_to_num(date_str):
    try:
        parts = date_str.split('.')
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
        return year + (month - 1) / 12.0 + (day - 1) / 365.0
    except:
        return 2024.0

# Floor helper
def parse_floor(floor_str):
    if not floor_str:
        return 10
    floor_str = floor_str.replace('층', '').strip()
    try:
        return int(floor_str)
    except:
        return 10

apt_id_map = {name: idx for idx, name in enumerate(APT_FILTERS.keys())}
# 'other' category mapping
other_idx = len(APT_FILTERS)

for r in raw_data:
    try:
        dong = r['동']
        apt_name = r['아파트']
        area = float(r['면적(㎡)'])
        floor = parse_floor(r['층'])
        price = float(r['금액(만원)'])
        date_val = date_to_num(r['거래일'])
        
        # Identify which target apartment it is
        matched_id = None
        for aid, meta in APT_FILTERS.items():
            if meta[0] in dong and meta[1] in apt_name:
                matched_id = aid
                break
        
        # Only train on the core 84m^2 target class and associated neighborhood listings to maintain high-quality signal
        if 75 <= area <= 90:
            apt_idx = apt_id_map[matched_id] if matched_id in apt_id_map else other_idx
            # Feature representation: [apt_idx, floor, date_val, area]
            X_list.append([apt_idx, floor, date_val, area])
            y_list.append(price)
    except Exception as e:
        continue

X = np.array(X_list, dtype=np.float32)
y = np.array(y_list, dtype=np.float32)

print(f"Extracted {len(X)} training samples (84m^2 class subset).")

# Split dataset
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 3. Train RandomForest model
print("Training RandomForest model...")
rf = RandomForestRegressor(n_estimators=100, random_state=42)
rf.fit(X_train, y_train)

y_pred_rf = rf.predict(X_test)
r2_rf = r2_score(y_test, y_pred_rf)
mae_rf = mean_absolute_error(y_test, y_pred_rf)
print(f"RandomForest validation - R2 score: {r2_rf:.4f}, MAE: {mae_rf:.1f} 만원")

# 4. Train PyTorch Deep Learning MLP model
print("Training PyTorch Deep Learning MLP model...")
# Scale features and targets for neural net
X_train_mean = X_train.mean(axis=0)
X_train_std = X_train.std(axis=0)
X_train_std[X_train_std == 0] = 1.0 # prevent division by zero

y_train_mean = y_train.mean()
y_train_std = y_train.std()
if y_train_std == 0:
    y_train_std = 1.0

X_train_scaled = (X_train - X_train_mean) / X_train_std
X_test_scaled = (X_test - X_train_mean) / X_train_std
y_train_scaled = (y_train - y_train_mean) / y_train_std

# Convert to tensors
X_train_tensor = torch.tensor(X_train_scaled, dtype=torch.float32)
y_train_tensor = torch.tensor(y_train_scaled, dtype=torch.float32).unsqueeze(1)
X_test_tensor = torch.tensor(X_test_scaled, dtype=torch.float32)

class PriceMLP(nn.Module):
    def __init__(self, input_dim):
        super(PriceMLP, self).__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1)
        )
        
    def forward(self, x):
        return self.net(x)

model = PriceMLP(X_train.shape[1])
criterion = nn.MSELoss()
optimizer = optim.Adam(model.parameters(), lr=0.01)

# Training loop
epochs = 150
for epoch in range(epochs):
    model.train()
    optimizer.zero_grad()
    predictions = model(X_train_tensor)
    loss = criterion(predictions, y_train_tensor)
    loss.backward()
    optimizer.step()

# Evaluate PyTorch Model
model.eval()
with torch.no_grad():
    y_pred_torch_scaled = model(X_test_tensor).numpy()
    # Unscale predictions
    y_pred_torch = y_pred_torch_scaled.flatten() * y_train_std + y_train_mean
    r2_torch = r2_score(y_test, y_pred_torch)
    mae_torch = mean_absolute_error(y_test, y_pred_torch)

print(f"PyTorch MLP validation - R2 score: {r2_torch:.4f}, MAE: {mae_torch:.1f} 만원")

# 5. Generate Predictions for the 9 target apartments
predictions_output = {}
current_date_num = date_to_num(datetime.datetime.now().strftime('%Y.%m.%d'))
future_date_num = current_date_num + 0.25 # 3 months later

# Floor categories mapping
floors = {
    'low': 2,
    'mid': 12,
    'high': 22
}

for aid in APT_FILTERS.keys():
    apt_idx = apt_id_map[aid]
    predictions_output[aid] = {}
    
    for floor_name, floor_val in floors.items():
        # Feature representation: [apt_idx, floor, date_val, area]
        features_curr = np.array([[apt_idx, floor_val, current_date_num, 84.5]], dtype=np.float32)
        features_future = np.array([[apt_idx, floor_val, future_date_num, 84.5]], dtype=np.float32)
        
        # RandomForest predictions
        rf_price_curr = rf.predict(features_curr)[0]
        rf_price_future = rf.predict(features_future)[0]
        
        # PyTorch predictions
        features_curr_scaled = (features_curr - X_train_mean) / X_train_std
        features_future_scaled = (features_future - X_train_mean) / X_train_std
        
        with torch.no_grad():
            torch_price_curr_scaled = model(torch.tensor(features_curr_scaled, dtype=torch.float32)).item()
            torch_price_future_scaled = model(torch.tensor(features_future_scaled, dtype=torch.float32)).item()
            # Unscale predictions
            torch_price_curr = torch_price_curr_scaled * y_train_std + y_train_mean
            torch_price_future = torch_price_future_scaled * y_train_std + y_train_mean
            
        predictions_output[aid][floor_name] = {
            'rf_fair_price': round(rf_price_curr),
            'rf_forecast_price': round(rf_price_future),
            'torch_fair_price': round(torch_price_curr),
            'torch_forecast_price': round(torch_price_future),
            # Combined averaged ensemble estimation
            'fair_price': round((rf_price_curr + torch_price_curr) / 2),
            'forecast_price': round((rf_price_future + torch_price_future) / 2)
        }

# Save output
ml_metadata = {
    'rf_r2': round(float(r2_rf), 4),
    'rf_mae': round(float(mae_rf), 1),
    'torch_r2': round(float(r2_torch), 4),
    'torch_mae': round(float(mae_torch), 1),
    'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
    'predictions': predictions_output
}

# Append or rewrite js data injection
data_js_path = "real_estate_data.js"
if not os.path.exists(data_js_path):
    data_js_path = os.path.join(os.path.dirname(__file__), "real_estate_data.js")

# Read current content of real_estate_data.js
with open(data_js_path, 'r', encoding='utf-8') as f:
    js_content = f.read()

# Strip any existing INJECTED_ML_DATA if already present
js_content = re.sub(r'// ======== AUTO_UPDATE_ML_ZONE_START ========.*// ======== AUTO_UPDATE_ML_ZONE_END ========', '', js_content, flags=re.DOTALL)

# Format the new injection string
ml_injection = f"""
// ======== AUTO_UPDATE_ML_ZONE_START ========
const INJECTED_ML_DATA = {json.dumps(ml_metadata, ensure_ascii=False)};
// ======== AUTO_UPDATE_ML_ZONE_END ========"""

# Append to file
with open(data_js_path, 'w', encoding='utf-8') as f:
    f.write(js_content + ml_injection)

print("ML/DL pipeline execution completed successfully! INJECTED_ML_DATA injected into real_estate_data.js.")
