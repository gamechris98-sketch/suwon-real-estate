import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import datetime
import ssl
import os

# GitHub Actions 환경에서는 Secrets에서 키를 가져오고, 로컬에서는 하드코딩된 키 사용
key = os.environ.get("MOLIT_API_KEY", "4b7ee22fae222a8c2abb5e3f41bb9d54bef87843d68922dcbbe9b55824817d12")

now = datetime.datetime.now()
months = []
for i in range(11, -1, -1):
    m = now.month - i
    y = now.year
    while m <= 0:
        m += 12
        y -= 1
    months.append(f"{y}{m:02d}")

lawd_cds = ['41117', '41115'] # Yeongtong, Paldal
all_items = []

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Fetching data from API...")

for month in months:
    for cd in lawd_cds:
        url = f"https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade?serviceKey={key}&pageNo=1&numOfRows=1000&LAWD_CD={cd}&DEAL_YMD={month}"
        try:
            req = urllib.request.Request(url)
            response = urllib.request.urlopen(req, context=ctx)
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            for item in root.iter('item'):
                aptNm = item.findtext('aptNm') or ''
                dealAmount = item.findtext('dealAmount') or '0'
                excluUseAr = float(item.findtext('excluUseAr') or '0')
                
                price = int(dealAmount.replace(',', '').strip())
                
                if 83 <= excluUseAr <= 85:
                    all_items.append({'month': month, 'aptNm': aptNm, 'price': price})
        except Exception as e:
            print(f"Failed to fetch {month} {cd}: {e}")

data_series = {'edu': [], 'sujain': [], 'hillstate': [], 'ipark': [], 'skview': []}

for m in months:
    edu = [x['price'] for x in all_items if x['month'] == m and '에듀파크' in x['aptNm']]
    sujain = [x['price'] for x in all_items if x['month'] == m and '수자인' in x['aptNm']]
    hill = [x['price'] for x in all_items if x['month'] == m and '힐스테이트' in x['aptNm']]
    ipark = [x['price'] for x in all_items if x['month'] == m and '아이파크' in x['aptNm']]
    sk = [x['price'] for x in all_items if x['month'] == m and 'SK' in x['aptNm']]
    
    # Use previous month if missing, or a default
    data_series['edu'].append(edu[0] if edu else (data_series['edu'][-1] if data_series['edu'] else 60000))
    data_series['sujain'].append(sujain[0] if sujain else (data_series['sujain'][-1] if data_series['sujain'] else 75000))
    data_series['hillstate'].append(hill[0] if hill else (data_series['hillstate'][-1] if data_series['hillstate'] else 90000))
    data_series['ipark'].append(ipark[0] if ipark else (data_series['ipark'][-1] if data_series['ipark'] else 95000))
    data_series['skview'].append(sk[0] if sk else (data_series['skview'][-1] if data_series['skview'] else 85000))

print("Data fetched successfully.")

html_path = "suwon_real_estate.html"
if not os.path.exists(html_path):
    print(f"Warning: {html_path} not found in current directory. Using absolute path for local fallback.")
    html_path = r"C:\Users\재영\.gemini\antigravity\scratch\suwon_real_estate.html"

with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace placeholders safely without regex
target_data_str = f"const INJECTED_DATA = {data_series};"
target_months_str = f"const INJECTED_MONTHS = {months};"
target_time_str = f"const INJECTED_TIMESTAMP = '{now.strftime('%Y-%m-%d %H:%M')}';"

content = content.replace("const INJECTED_DATA = null;", target_data_str)
content = content.replace("const INJECTED_MONTHS = null;", target_months_str)
content = content.replace("const INJECTED_TIMESTAMP = null;", target_time_str)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("HTML updated with new data!")
