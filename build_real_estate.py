import urllib.request
import xml.etree.ElementTree as ET
import datetime, ssl, os, json

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

APT_FILTERS = {
    'mangpo_hillstate':    ('망포동', '힐스테이트'),
    'mangpo_ipark':        ('망포동', '아이파크캐슬1단지'),
    'mangpo_skview':       ('망포동', 'SKVIEW'),
    'mangpo_sujain':       ('망포동', '수자인'),
    'yeongtong_edupark':   ('영통동', '에듀파크'),
    'yeongtong_dongbo':    ('영통동', '신나무실동보'),
    'yeongtong_shinmyung': ('영통동', '신나무실신명'),
    'maegyo_skview':       ('매교동', '푸르지오SKVIEW'),
    'maegyo_hillstate':    ('매교동', '힐스테이트푸르지오'),
}

lawd_cds = ['41117', '41115']
all_items = []     # for chart (84sqm only)
raw_items = []     # for raw data tab (all sizes)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Fetching data...")

for month in months:
    for cd in lawd_cds:
        url = (f"https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/"
               f"getRTMSDataSvcAptTrade?serviceKey={key}"
               f"&pageNo=1&numOfRows=1000&LAWD_CD={cd}&DEAL_YMD={month}")
        try:
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, context=ctx)
            root = ET.fromstring(resp.read())
            for item in root.iter('item'):
                umdNm = item.findtext('umdNm') or ''
                aptNm = item.findtext('aptNm') or ''
                excluUseAr = float(item.findtext('excluUseAr') or '0')
                dealAmount = item.findtext('dealAmount') or '0'
                price = int(dealAmount.replace(',', '').strip())
                dealYear = item.findtext('dealYear') or ''
                dealMonth = item.findtext('dealMonth') or ''
                dealDay = item.findtext('dealDay') or ''
                floor = item.findtext('floor') or ''
                buildYear = item.findtext('buildYear') or ''

                # Chart data: 84sqm only, matching apartments
                if 80 <= excluUseAr <= 86:
                    all_items.append({'month': month, 'umdNm': umdNm, 'aptNm': aptNm, 'price': price})

                # Raw data: all monitored dong transactions
                if umdNm in ('망포동', '영통동', '매교동'):
                    raw_items.append({
                        'd': f"{dealYear}.{dealMonth.zfill(2)}.{dealDay.zfill(2)}",
                        'dong': umdNm,
                        'apt': aptNm,
                        'area': round(excluUseAr, 1),
                        'floor': floor,
                        'price': price,
                        'built': buildYear
                    })
        except Exception as e:
            print(f"  Failed {month}/{cd}: {e}")

print(f"  Chart items: {len(all_items)}, Raw items: {len(raw_items)}")

# Sort raw by date desc
raw_items.sort(key=lambda x: x['d'], reverse=True)

# Chart data
data = {}
for apt_id, (dong, keyword) in APT_FILTERS.items():
    data[apt_id] = []
    for m in months:
        matches = [x['price'] for x in all_items
                   if x['month'] == m and x['umdNm'] == dong and keyword in x['aptNm']]
        if matches:
            matches.sort()
            data[apt_id].append(matches[len(matches) // 2])
        elif data[apt_id]:
            data[apt_id].append(data[apt_id][-1])
        else:
            data[apt_id].append(0)
    print(f"  {apt_id}: {data[apt_id]}")

# HTML update
html_path = "suwon_real_estate.html"
if not os.path.exists(html_path):
    html_path = r"C:\Users\재영\.gemini\antigravity\scratch\suwon_real_estate.html"

with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

ts = now.strftime('%Y-%m-%d %H:%M')

# 뉴스/정책 (여기서 내용 수정하면 자동 반영)
news = [
    {"tag":"금리","title":"한국은행 기준금리 동결 (2.75%)","desc":"금통위 만장일치 동결. 하반기 인하 기대감 지속.","date":"2026.04","tc":"bg-amber-100 text-amber-700"},
    {"tag":"정책","title":"스트레스 DSR 2단계 시행","desc":"변동금리 가산금리 적용, 대출 한도 축소.","date":"2026.03","tc":"bg-red-100 text-red-700"},
    {"tag":"개발","title":"수원 매교역 역세권 개발 본격화","desc":"매교역 복합개발 순항. 인프라 확충 기대.","date":"2026.02","tc":"bg-emerald-100 text-emerald-700"},
    {"tag":"교통","title":"GTX-A 수원 연장 추진","desc":"수원역 연장 타당성 조사 착수.","date":"2026.01","tc":"bg-blue-100 text-blue-700"},
    {"tag":"공급","title":"영통구 2026년 신규 입주 물량","desc":"영통·망포 약 2,000세대 입주 예정.","date":"2025.12","tc":"bg-slate-100 text-slate-600"},
]

content = content.replace("const INJECTED_DATA = null;", f"const INJECTED_DATA = {json.dumps(data)};")
content = content.replace("const INJECTED_MONTHS = null;", f"const INJECTED_MONTHS = {json.dumps(months)};")
content = content.replace("const INJECTED_TIMESTAMP = null;", f"const INJECTED_TIMESTAMP = '{ts}';")
content = content.replace("const INJECTED_RAW = null;", f"const INJECTED_RAW = {json.dumps(raw_items, ensure_ascii=False)};")
content = content.replace("const INJECTED_NEWS = null;", f"const INJECTED_NEWS = {json.dumps(news, ensure_ascii=False)};")

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"HTML updated at {ts}! ({len(raw_items)} raw records injected)")
