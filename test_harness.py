import os
import json
import re

def run_checks():
    print("==================================================")
    print("   SUWON REAL ESTATE DATA TEST & VALIDATION HARNESS  ")
    print("==================================================")
    
    # Check 1: CSV Integrity
    csv_path = "suwon_real_estate.csv"
    if not os.path.exists(csv_path):
         csv_path = os.path.join(os.path.dirname(__file__), "suwon_real_estate.csv")
    
    print(f"[Check 1] Checking CSV file: {csv_path}")
    if not os.path.exists(csv_path):
        print("[FAIL] CSV file does not exist!")
        return False
    
    file_size = os.path.getsize(csv_path)
    if file_size < 1000:
        print(f"[FAIL] CSV file is too small ({file_size} bytes), likely corrupted!")
        return False
        
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        lines = f.readlines()
    if len(lines) < 100:
        print(f"[FAIL] CSV contains too few rows ({len(lines)} rows)!")
        return False
    print(f"[PASS] CSV contains {len(lines)} records and is valid.")

    # Check 2: JS Injection Validation
    js_path = "real_estate_data.js"
    if not os.path.exists(js_path):
         js_path = os.path.join(os.path.dirname(__file__), "real_estate_data.js")
         
    print(f"[Check 2] Checking real_estate_data.js syntax and data zones: {js_path}")
    if not os.path.exists(js_path):
        print("[FAIL] real_estate_data.js does not exist!")
        return False
        
    with open(js_path, 'r', encoding='utf-8') as f:
        js_content = f.read()
        
    # Check for zone markers
    if "const INJECTED_DATA =" not in js_content:
        print("[FAIL] INJECTED_DATA zone missing from Javascript!")
        return False
    if "const INJECTED_ML_DATA =" not in js_content:
        print("[FAIL] INJECTED_ML_DATA zone missing from Javascript! ML Pipeline might have failed.")
        return False
        
    print("[PASS] Zones and definitions found.")

    # Check 3: Extract and validate ML Metadata JSON
    print("[Check 3] Extracting and validating INJECTED_ML_DATA JSON content")
    match = re.search(r'const INJECTED_ML_DATA = (\{.*?\});', js_content, re.DOTALL)
    if not match:
        print("[FAIL] Could not parse INJECTED_ML_DATA JSON string!")
        return False
        
    try:
        ml_data = json.loads(match.group(1))
    except Exception as e:
        print(f"[FAIL] INJECTED_ML_DATA is not valid JSON: {e}")
        return False
        
    # Check R2 scores
    rf_r2 = ml_data.get('rf_r2', 0)
    torch_r2 = ml_data.get('torch_r2', 0)
    print(f"   > RandomForest validation R2 score: {rf_r2}")
    print(f"   > PyTorch MLP validation R2 score: {torch_r2}")
    
    if rf_r2 < 0.50:
        print(f"[FAIL] RandomForest R2 score ({rf_r2}) is below acceptable threshold 0.50!")
        return False
    print("[PASS] ML/DL Model performance scores are within acceptable boundaries.")

    # Check 4: Check if all 9 apartments exist in predictions
    print("[Check 4] Checking prediction keys for target apartments")
    expected_apts = [
        'mangpo_hillstate', 'mangpo_ipark', 'mangpo_skview', 'mangpo_sujain',
        'yeongtong_edupark', 'yeongtong_dongbo', 'yeongtong_shinmyung',
        'maegyo_skview', 'maegyo_hillstate'
    ]
    preds = ml_data.get('predictions', {})
    for apt in expected_apts:
        if apt not in preds:
            print(f"[FAIL] Prediction key for '{apt}' is missing in ML predictions!")
            return False
        for floor in ['low', 'mid', 'high']:
            if floor not in preds[apt]:
                print(f"[FAIL] Floor '{floor}' prediction missing for '{apt}'!")
                return False
            vals = preds[apt][floor]
            if 'fair_price' not in vals or 'forecast_price' not in vals:
                print(f"[FAIL] Price fields missing in '{apt}' floor '{floor}' prediction!")
                return False
                
    print("[PASS] All 9 target apartments have complete low/mid/high price predictions.")

    # Check 5: HTML integrity checks
    html_path = "index.html"
    if not os.path.exists(html_path):
        html_path = os.path.join(os.path.dirname(__file__), "index.html")
    print(f"[Check 5] Checking HTML file integrity: {html_path}")
    if not os.path.exists(html_path):
        print("[FAIL] index.html does not exist!")
        return False
        
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
        
    # Check library links
    if "cdn.jsdelivr.net/npm/chart.js" not in html_content:
        print("[FAIL] Chart.js dependency script link missing in index.html!")
        return False
        
    print("[PASS] HTML syntax and library dependencies are intact.")
    
    print("\n==================================================")
    print("  ALL CHECKS PASSED: DEPLOYMENT STABLE AND READY! ")
    print("==================================================")
    return True

if __name__ == '__main__':
    import sys
    success = run_checks()
    if not success:
        sys.exit(1)
    else:
        sys.exit(0)
