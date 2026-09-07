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
import lightgbm as lgb
import torch
import torch.nn as nn
import torch.optim as optim

# 12 Target Apartments Configuration (동, 키워드, 세대수, 준공연도)
APT_FILTERS = {
    'mangpo_hillstate':    ('망포동', '힐스테이트영통', 2140, 2017),
    'mangpo_ipark':        ('망포동', '아이파크캐슬1단지', 1783, 2019),
    'mangpo_skview':       ('망포동', '영통SKVIEW', 710, 2016),
    'mangpo_sujain':       ('망포동', '한양수자인', 530, 2013),
    'yeongtong_edupark':   ('영통동', '에듀파크', 1279, 1999),
    'yeongtong_dongbo':    ('영통동', '신나무실동보', 836, 1997),
    'yeongtong_shinmyung': ('영통동', '신나무실신명', 384, 1997),
    'yeongtong_geukdong':  ('영통동', '신나무실극동', 836, 1997),
    'yeongtong_punglim':   ('영통동', '신나무실풍림', 836, 1997),
    'maetan_weve':         ('매탄동', '위브하늘채', 3391, 2008),
    'maegyo_skview':       ('매교동', '푸르지오SKVIEW', 3603, 2022),
    'maegyo_hillstate':    ('매교동', '힐스테이트푸르지오', 2586, 2022),
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
    floor_str = str(floor_str).replace('층', '').strip()
    try:
        return int(floor_str)
    except:
        return 10

apt_id_map = {name: idx for idx, name in enumerate(APT_FILTERS.keys())}
other_idx = len(APT_FILTERS)

# Calculate complex-level rolling statistics (last 6 months momentum)
recent_threshold_date = 2026.0 - 0.5 # 2025.5 이후 거래

complex_recent_prices = {aid: [] for aid in APT_FILTERS}
complex_all_prices = {aid: [] for aid in APT_FILTERS}

for r in raw_data:
    dong = r.get('동', '')
    apt_name = r.get('아파트', '')
    try:
        price = float(r.get('금액(만원)', 0))
        d_val = date_to_num(r.get('거래일', '2024.01.01'))
        area = float(r.get('면적(㎡)', 0))
    except:
        continue
    
    if 75 <= area <= 90:
        for aid, meta in APT_FILTERS.items():
            if meta[0] in dong and meta[1] in apt_name:
                complex_all_prices[aid].append(price)
                if d_val >= recent_threshold_date:
                    complex_recent_prices[aid].append(price)
                break

complex_medians = {}
complex_momentums = {}
for aid in APT_FILTERS:
    all_p = complex_all_prices[aid]
    rec_p = complex_recent_prices[aid]
    med = np.median(all_p) if len(all_p) > 0 else 70000.0
    complex_medians[aid] = med
    if len(rec_p) > 0 and len(all_p) > 0:
        rec_med = np.median(rec_p)
        complex_momentums[aid] = (rec_med - med) / (med + 1e-5) * 100.0
    else:
        complex_momentums[aid] = 0.0

# 2. Extract advanced features
X_list = []
y_list = []

for r in raw_data:
    try:
        dong = r['동']
        apt_name = r['아파트']
        area = float(r['면적(㎡)'])
        floor = parse_floor(r['층'])
        price = float(r['금액(만원)'])
        date_val = date_to_num(r['거래일'])
        
        matched_id = None
        for aid, meta in APT_FILTERS.items():
            if meta[0] in dong and meta[1] in apt_name:
                matched_id = aid
                break
        
        if 75 <= area <= 90:
            apt_idx = apt_id_map[matched_id] if matched_id in apt_id_map else other_idx
            build_yr = APT_FILTERS[matched_id][3] if matched_id else 2000
            apt_age = max(1, 2026 - build_yr)
            momentum = complex_momentums.get(matched_id, 0.0)
            
            # Features: [apt_idx, floor, date_val, area, apt_age, momentum]
            X_list.append([apt_idx, floor, date_val, area, apt_age, momentum])
            y_list.append(price)
    except Exception as e:
        continue

X = np.array(X_list, dtype=np.float32)
y = np.array(y_list, dtype=np.float32)

print(f"Extracted {len(X)} training samples (84m^2 class subset).")

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 3. Train RandomForest model
print("Training RandomForest model...")
rf = RandomForestRegressor(n_estimators=120, max_depth=16, random_state=42, n_jobs=-1)
rf.fit(X_train, y_train)
y_pred_rf = rf.predict(X_test)
r2_rf = r2_score(y_test, y_pred_rf)
mae_rf = mean_absolute_error(y_test, y_pred_rf)
print(f"RandomForest validation - R2 score: {r2_rf:.4f}, MAE: {mae_rf:.1f} 만원")

# 4. Train LightGBM model
print("Training LightGBM Regressor model...")
lgb_model = lgb.LGBMRegressor(
    n_estimators=150,
    learning_rate=0.08,
    num_leaves=31,
    random_state=42,
    verbose=-1
)
lgb_model.fit(X_train, y_train)
y_pred_lgb = lgb_model.predict(X_test)
r2_lgb = r2_score(y_test, y_pred_lgb)
mae_lgb = mean_absolute_error(y_test, y_pred_lgb)
print(f"LightGBM validation - R2 score: {r2_lgb:.4f}, MAE: {mae_lgb:.1f} 만원")

# 5. Train PyTorch Deep Learning MLP model
print("Training PyTorch Deep Learning MLP model...")
X_train_mean = X_train.mean(axis=0)
X_train_std = X_train.std(axis=0)
X_train_std[X_train_std == 0] = 1.0

y_train_mean = y_train.mean()
y_train_std = y_train.std()
if y_train_std == 0:
    y_train_std = 1.0

X_train_scaled = (X_train - X_train_mean) / X_train_std
X_test_scaled = (X_test - X_train_mean) / X_train_std
y_train_scaled = (y_train - y_train_mean) / y_train_std

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

epochs = 150
for epoch in range(epochs):
    model.train()
    optimizer.zero_grad()
    predictions = model(X_train_tensor)
    loss = criterion(predictions, y_train_tensor)
    loss.backward()
    optimizer.step()

model.eval()
with torch.no_grad():
    y_pred_torch_scaled = model(X_test_tensor).numpy()
    y_pred_torch = y_pred_torch_scaled.flatten() * y_train_std + y_train_mean
    r2_torch = r2_score(y_test, y_pred_torch)
    mae_torch = mean_absolute_error(y_test, y_pred_torch)

print(f"PyTorch MLP validation - R2 score: {r2_torch:.4f}, MAE: {mae_torch:.1f} 만원")

# 6. Load live asking price bands from real_estate_data.js
data_js_path = "real_estate_data.js"
if not os.path.exists(data_js_path):
    data_js_path = os.path.join(os.path.dirname(__file__), "real_estate_data.js")

live_analysis_data = {}
with open(data_js_path, 'r', encoding='utf-8') as f:
    js_raw = f.read()
    match_ad = re.search(r'const INJECTED_ANALYSIS_DATA = (\{.*?\});', js_raw, re.DOTALL)
    if match_ad:
        try:
            live_analysis_data = json.loads(match_ad.group(1))
        except:
            pass

# 7. Generate Predictions for all 12 target apartments
predictions_output = {}
liquidity_metrics = {}
ai_reports = {}

current_date_num = date_to_num(datetime.datetime.now().strftime('%Y.%m.%d'))
future_date_num = current_date_num + 0.25 # 3 months later

floors = {
    'low': 2,
    'mid': 12,
    'high': 22
}

for aid, meta in APT_FILTERS.items():
    apt_idx = apt_id_map[aid]
    apt_name = meta[1]
    dong_name = meta[0]
    build_yr = meta[3]
    apt_age = max(1, 2026 - build_yr)
    momentum = complex_momentums.get(aid, 0.0)
    
    ad = live_analysis_data.get(aid, {})
    curr_trade_p = ad.get('curr', 70000)
    ask_low = ad.get('ask_low', curr_trade_p)
    ask_mid = ad.get('ask_mid', curr_trade_p)
    ask_high = ad.get('ask_high', curr_trade_p)
    
    predictions_output[aid] = {}
    
    for floor_name, floor_val in floors.items():
        feat_curr = np.array([[apt_idx, floor_val, current_date_num, 84.5, apt_age, momentum]], dtype=np.float32)
        feat_future = np.array([[apt_idx, floor_val, future_date_num, 84.5, apt_age, momentum]], dtype=np.float32)
        
        # RF
        rf_c = rf.predict(feat_curr)[0]
        rf_f = rf.predict(feat_future)[0]
        
        # LightGBM
        lgb_c = lgb_model.predict(feat_curr)[0]
        lgb_f = lgb_model.predict(feat_future)[0]
        
        # PyTorch
        fc_scaled = (feat_curr - X_train_mean) / X_train_std
        ff_scaled = (feat_future - X_train_mean) / X_train_std
        with torch.no_grad():
            tc_scaled = model(torch.tensor(fc_scaled, dtype=torch.float32)).item()
            tf_scaled = model(torch.tensor(ff_scaled, dtype=torch.float32)).item()
            tc = tc_scaled * y_train_std + y_train_mean
            tf = tf_scaled * y_train_std + y_train_mean
            
        # 3-Model Ensemble (Weighted: LightGBM 40%, RF 40%, PyTorch MLP 20%)
        fair_p = round(lgb_c * 0.4 + rf_c * 0.4 + tc * 0.2)
        forecast_p = round(lgb_f * 0.4 + rf_f * 0.4 + tf * 0.2)
        
        predictions_output[aid][floor_name] = {
            'rf_fair_price': round(rf_c),
            'rf_forecast_price': round(rf_f),
            'lgb_fair_price': round(lgb_c),
            'lgb_forecast_price': round(lgb_f),
            'torch_fair_price': round(tc),
            'torch_forecast_price': round(tf),
            'fair_price': fair_p,
            'forecast_price': forecast_p
        }

    # 8. Calculate Asking Spread, Bubble Index & Liquidity Index
    mid_fair = predictions_output[aid]['mid']['fair_price']
    spread_amt = ask_mid - curr_trade_p
    spread_pct = round((spread_amt / curr_trade_p) * 100.0, 1) if curr_trade_p > 0 else 0.0
    
    # Bubble Index: 호가가 AI 적정가치 및 직전 거래를 얼마나 초과하는지 (0 ~ 100)
    bubble_score = max(10, min(95, round(50 + spread_pct * 3.0)))
    
    # Liquidity / Digestibility Index (호가 소화 가능성: 0 ~ 100%)
    fair_gap_pct = ((ask_mid - mid_fair) / mid_fair) * 100.0
    liquidity_score = max(15, min(98, round(85 - fair_gap_pct * 2.5 + (momentum * 0.5))))
    
    if liquidity_score >= 75:
        digest_verdict = "즉시 체결 유력 (소화율 높음)"
        digest_color = "text-emerald-600 bg-emerald-50 border-emerald-200"
    elif liquidity_score >= 50:
        digest_verdict = "호가 조정 후 체결 (보통)"
        digest_color = "text-amber-600 bg-amber-50 border-amber-200"
    else:
        digest_verdict = "매수자 관망 / 가격 네고 필수 (소화 정체)"
        digest_color = "text-rose-600 bg-rose-50 border-rose-200"
        
    liquidity_metrics[aid] = {
        'asking_mid': ask_mid,
        'recent_trade': curr_trade_p,
        'spread_amt': spread_amt,
        'spread_pct': spread_pct,
        'bubble_score': bubble_score,
        'liquidity_score': liquidity_score,
        'digest_verdict': digest_verdict,
        'digest_color': digest_color
    }

    # 9. LLM-grade AI Appraisal Report Generator
    hill_ask = live_analysis_data.get('mangpo_hillstate', {}).get('ask_mid', 160000)
    ratio_to_leader = round((ask_mid / hill_ask) * 100.0, 1) if hill_ask > 0 else 0.0
    
    report_text = (
        f"**[AI 감정평가사 정밀 소견 - {apt_name} (전용 84㎡)]**\n"
        f"• **실거래-호가 갭 분석**: 최근 실거래가({(curr_trade_p/10000):.2f}억) 대비 현재 네이버 대표 호가는 {(ask_mid/10000):.2f}억으로 "
        f"{'+' if spread_amt >= 0 else ''}{(spread_amt/10000):.2f}억({'+' if spread_pct >= 0 else ''}{spread_pct}%)의 호가 스프레드가 형성되어 있습니다.\n"
        f"• **3종 ML 앙상블 가치 평가**: LightGBM, RandomForest, PyTorch MLP 앙상블 모델이 산출한 중층 기준 공정가치는 "
        f"**{(mid_fair/10000):.2f}억**이며, 3개월 후 예상 가격은 **{(predictions_output[aid]['mid']['forecast_price']/10000):.2f}억**입니다.\n"
        f"• **권역 대장주 대비 위상**: 망포 대장주(힐스테이트영통 16.0억) 대비 가격 비중은 **{ratio_to_leader}%** 수준입니다.\n"
        f"• **매수 소화율 및 네고 가이드**: 매물 소화율 지수는 **{liquidity_score}점({digest_verdict})**입니다. "
        f"현 호가에서 최저호가인 {(ask_low/10000):.2f}억 선 이하로 진입 시 안전 마진이 확보됩니다."
    )
    
    ai_reports[aid] = {
        'title': f"{apt_name} 국평(84㎡) AI 가치 감정서",
        'summary': f"AI 공정가치 {(mid_fair/10000):.2f}억 | 호가 소화율 {liquidity_score}% ({digest_verdict})",
        'body': report_text,
        'fair_mid': mid_fair,
        'forecast_mid': predictions_output[aid]['mid']['forecast_price'],
        'spread_pct': spread_pct,
        'liquidity_score': liquidity_score,
        'bubble_score': bubble_score
    }

# Save output
ml_metadata = {
    'rf_r2': round(float(r2_rf), 4),
    'rf_mae': round(float(mae_rf), 1),
    'lgb_r2': round(float(r2_lgb), 4),
    'lgb_mae': round(float(mae_lgb), 1),
    'torch_r2': round(float(r2_torch), 4),
    'torch_mae': round(float(mae_torch), 1),
    'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
    'predictions': predictions_output,
    'liquidity_metrics': liquidity_metrics,
    'ai_reports': ai_reports
}

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

with open(data_js_path, 'w', encoding='utf-8') as f:
    f.write(js_content + ml_injection)

print("Upgraded ML/LLM pipeline execution completed successfully! INJECTED_ML_DATA injected into real_estate_data.js.")

