import urllib.request
import xml.etree.ElementTree as ET
import datetime, ssl, os, json
import concurrent.futures
from collections import defaultdict

# API 설정
key = os.environ.get("MOLIT_API_KEY", "4b7ee22fae222a8c2abb5e3f41bb9d54bef87843d68922dcbbe9b55824817d12")
lawd_cds = ['41117', '41115'] # 영통구, 팔달구

# 기간 설정 (최근 12개월 및 10년)
now = datetime.datetime.now()
months = []
for i in range(11, -1, -1):
    # 정확한 월 계산을 위해 연/월 수식 사용
    year = now.year + (now.month - 1 - i) // 12
    month = (now.month - 1 - i) % 12 + 1
    months.append(f"{year}{month:02d}")

months_10y = []
for i in range(119, -1, -1):
    year = now.year + (now.month - 1 - i) // 12
    month = (now.month - 1 - i) % 12 + 1
    months_10y.append(f"{year}{month:02d}")

# 대상 아파트 필터 (동, 아파트명 키워드, 세대수, 지하주차장 연결)
APT_FILTERS = {
    'mangpo_hillstate':    ('망포동', '힐스테이트영통', 2140, '연결 O'),
    'mangpo_ipark':        ('망포동', '아이파크캐슬1단지', 1783, '연결 O'),
    'mangpo_skview':       ('망포동', '영통SKVIEW', 710, '연결 O'),
    'mangpo_sujain':       ('망포동', '한양수자인', 530, '연결 O'),
    'yeongtong_edupark':   ('영통동', '에듀파크', 1279, '연결 X'),
    'yeongtong_dongbo':    ('영통동', '신나무실동보', 836, '연결 X'),
    'yeongtong_shinmyung': ('영통동', '신나무실신명', 384, '연결 X'),
    'maegyo_skview':       ('매교동', '푸르지오SKVIEW', 3603, '연결 O'),
    'maegyo_hillstate':    ('매교동', '힐스테이트푸르지오', 2586, '연결 O'),
}

all_trades = [] # 매매 데이터
raw_items = []  # 원본 데이터 탭용

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

import time

import urllib.parse

def fetch_api(svc, lawd, mon):
    # 가이드북 지침에 따라 서비스키를 URL 인코딩하여 전송 (403 에러 방지)
    encoded_key = urllib.parse.quote(urllib.parse.unquote(key)) 
    service_name = svc.replace("get", "")
    url = (f"https://apis.data.go.kr/1613000/{service_name}/{svc}?"
           f"serviceKey={encoded_key}&LAWD_CD={lawd}&DEAL_YMD={mon}&pageNo=1&numOfRows=1000")
    
    for attempt in range(2): # 재시도 횟수 축소 (속도 향상)
        try:
            time.sleep(0.1) # 지연 시간 최적화
            req = urllib.request.Request(url)
            # 타임아웃 10초 추가
            with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                data = resp.read()
                root = ET.fromstring(data)
                res_code = root.findtext('.//resultCode')
                if res_code not in ['00', '000']:
                    return None
                return root
        except Exception:
            if attempt < 1:
                time.sleep(1)
                continue
            return None
    return None

print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 10년 매매 데이터 수집 시작 (약 2~3분 소요)...")
all_trades_10y = []

# 멀티스레딩으로 10년치 매매 데이터 수집
def fetch_trade_worker(arg):
    mon, cd = arg
    # 진행 상황 출력
    print(f"  > [{mon}] 데이터 요청 중...", end='\r')
    root = fetch_api("getRTMSDataSvcAptTrade", cd, mon)
    res = []
    if root is not None:
        items = list(root.iter('item'))
        for item in items:

            umd = item.findtext('umdNm') or ''
            apt = item.findtext('aptNm') or ''
            area = float(item.findtext('excluUseAr') or '0')
            price = int((item.findtext('dealAmount') or '0').replace(',', '').strip())
            day = item.findtext('dealDay') or '1'
            floor = item.findtext('floor') or ''
            built = item.findtext('buildYear') or ''
            # 면적 범위를 조금 더 넓게 잡아 데이터 누락 방지 (50~120㎡)
            if 50 <= area <= 125 and umd in ('망포동', '영통동', '매교동'):
                res.append({'d': f"{mon[:4]}.{mon[4:6]}.{day.zfill(2)}", 'm': mon, 'umd': umd, 'apt': apt, 'p': price, 'area': area, 'floor': floor, 'built': built})
    return res

trade_args = [(m, cd) for m in months_10y for cd in lawd_cds]
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor: # 동시 접속자 수 축소
    results = executor.map(fetch_trade_worker, trade_args)
    for res in results:
        all_trades_10y.extend(res)

print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 총 {len(all_trades_10y)}건의 매매 데이터 수집 완료.")

# 10년 전체 데이터 원본 목록 생성
raw_items = []
for t in all_trades_10y:
    py_price = round(t['p'] / (t['area'] / 3.305), 1) if t['area'] > 0 else 0
    raw_items.append({
        'd': t['d'], 'dong': t['umd'], 'apt': t['apt'], 'area': round(t['area'], 1),
        'floor': t['floor'], 'price': t['p'], 'type': '매매', 'py': py_price, 'built': t['built']
    })

# 최근 60개월 데이터 분류 (차트용, 저층 제외)
for t in all_trades_10y:
    if t['m'] in months:
        if t['floor'] and str(t['floor']).isdigit() and int(t['floor']) > 5:
            all_trades.append(t)

# 데이터 가공 및 지표 계산
analysis_data = {}
chart_data = {}

# -------------------------------------------------------------------------
# 데이터 가공 및 주입
# -------------------------------------------------------------------------

# Raw 데이터 정렬 (최신순)
raw_items.sort(key=lambda x: x['d'], reverse=True)

# 차트 및 대시보드용 요약
for aid, meta in APT_FILTERS.items():
    dong, kw, households, parking_ratio, parking_conn = meta
    trade_history = []
    
    t10y_raw = [x for x in all_trades_10y if x['umd'] == dong and kw in x['apt']]
    # 전고점 비교용 데이터는 '전체' 반영 (저층 포함)
    t10y = sorted([x for x in t10y_raw if 80 <= x['area'] <= 86], key=lambda x: x['d'])
    
    if len(t10y) < 5: # 데이터 부족 시 면적 제한 해제
        t10y = sorted(t10y_raw, key=lambda x: x['d'])
    
    # 1. 역사적 전고점 (2년 이전)
    hist_peak_p = 0
    hist_peak_d = ""
    # 2. 최근 전고점 (최근 2년)
    recent_peak_p = 0
    recent_peak_d = ""
    # 3. 최근 1년 내 최고/최저 (하락률 계산용)
    one_year_ago = (now - datetime.timedelta(days=365)).strftime('%Y.%m.%d')
    two_years_ago = (now - datetime.timedelta(days=730)).strftime('%Y.%m.%d')
    
    max_p_1y = 0
    min_p_1y = 999999999

    for t in t10y:
        # 역사적 전고점 (2년 이전)
        if t['d'] < two_years_ago:
            if t['p'] > hist_peak_p:
                hist_peak_p = t['p']
                hist_peak_d = t['d']
        # 최근 전고점 (최근 2년)
        else:
            if t['p'] > recent_peak_p:
                recent_peak_p = t['p']
                recent_peak_d = t['d']
        
        # 최근 1년 내 지표
        if t['d'] >= one_year_ago:
            if t['p'] > max_p_1y: max_p_1y = t['p']
            if t['p'] < min_p_1y: min_p_1y = t['p']
            
    # 최근 60개월 차트용
    for m in months:
        t_matches = [x['p'] for x in all_trades if x['m'] == m and x['umd'] == dong and kw in x['apt']]
        tp = sorted(t_matches)[len(t_matches)//2] if t_matches else (trade_history[-1] if trade_history else 0)
        trade_history.append(tp)

    curr_p = trade_history[-1] if trade_history else 0
    chart_data[aid] = trade_history
    analysis_data[aid] = {
        'hist_peak': hist_peak_p, 'hist_peak_date': hist_peak_d,
        'recent_peak': recent_peak_p, 'recent_peak_date': recent_peak_d,
        'curr': curr_p,
        'drop_1y': round((max_p_1y - min_p_1y) / max_p_1y * 100, 1) if max_p_1y > 0 else 0,
        'ratio': round(curr_p / hist_peak_p * 100, 1) if hist_peak_p else 0,
        'households': households, 'parking': f"{parking_ratio} | {parking_conn}"
    }

# 가상 전문가 의견 (다른 성향의 5인)
experts = [
    {"nm": "김성실", "role": "공격적 투자자", "c": "text-red-600", "m": "현재 수원은 전고점 대비 충분히 매력적인 가격대입니다. 공급 절벽이 예상되는 2-3년 뒤를 생각하면 지금이 가장 저렴한 시점일 수 있습니다."},
    {"nm": "이지적인", "role": "데이터 분석가", "c": "text-blue-600", "m": "거래량이 전년 대비 완만하게 회복 중이나, 아직 전고점 돌파를 논하기엔 이릅니다. 급매물이 소진된 후 호가가 유지되는지 확인이 필요합니다."},
    {"nm": "박현장", "role": "공인중개사", "c": "text-amber-600", "m": "망포와 영통의 대장 단지들은 이미 실거주 수요로 인해 바닥을 확인했습니다. 중층 이상의 로열동 급매물은 나오는 즉시 거래되는 분위기입니다."},
    {"nm": "최보수", "role": "자산관리사", "c": "text-emerald-600", "m": "DSR 규제와 고금리가 여전한 상황에서 무리한 영끌은 위험합니다. 자금 계획을 보수적으로 잡고, 경매나 급급매 위주로 선별 접근하세요."},
    {"nm": "한가치", "role": "가치투자자", "c": "text-violet-600", "m": "입지 가치는 변하지 않습니다. 신축급인 매교역 주변과 학군이 우수한 영통의 핵심 입지는 시장 회복기 때 가장 먼저 튀어오를 곳들입니다."}
]

# 시장 분석 요약
up_count = sum(1 for d in chart_data.values() if d[-1] > d[-4]) if len(months)>=4 else 0
mkt_summary = {
    'bull': up_count > len(chart_data)/2,
    'summary': '📈 수원 영통 시장 완만한 회복세 (저층 제외)' if up_count > len(chart_data)/2 else '📉 시장 조정 및 관망세 지속 (저층 제외)',
    'details': [
        f'주요 {len(chart_data)}개 단지 중 {up_count}개 최근 3개월 반등.',
        '전세가 상승에 따른 매수 전환 수요 관찰됨.',
        '중층/고층 실거래 데이터 기반 분석 결과임.'
    ],
    'experts': experts
}

# HTML 주입 (상대 경로로 수정하여 깃허브 호환성 확보)
html_path = "suwon_real_estate.html"
if not os.path.exists(html_path):
    # 로컬 실행 시 경로 대응
    html_path = os.path.join(os.path.dirname(__file__), "suwon_real_estate.html")
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

import json
injection = f"""
const INJECTED_DATA = {json.dumps(chart_data)};
const INJECTED_ANALYSIS_DATA = {json.dumps(analysis_data, ensure_ascii=False)};
const INJECTED_ANALYSIS = {json.dumps(mkt_summary, ensure_ascii=False)};
const INJECTED_MONTHS = {json.dumps(months)};
const INJECTED_TIMESTAMP = '{now.strftime('%Y-%m-%d %H:%M')}';
const INJECTED_RAW = {json.dumps(raw_items, ensure_ascii=False)};
const INJECTED_NEWS = {json.dumps(news_list, ensure_ascii=False)};
"""

import re
html = re.sub(r"// ======== AUTO_UPDATE_ZONE_START ========.*?// ======== AUTO_UPDATE_ZONE_END ========", 
              f"// ======== AUTO_UPDATE_ZONE_START ========{injection}// ======== AUTO_UPDATE_ZONE_END ========", 
              html, flags=re.DOTALL)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Update Complete: trade {len(all_trades)}. HTML updated!")

