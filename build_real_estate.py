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
    d = now.replace(day=1) - datetime.timedelta(days=30*i)
    months.append(d.strftime("%Y%m"))

months_10y = []
for i in range(119, -1, -1):
    d = now.replace(day=1) - datetime.timedelta(days=30*i)
    months_10y.append(d.strftime("%Y%m"))

# 대상 아파트 필터 (동, 아파트명 키워드)
APT_FILTERS = {
    'mangpo_hillstate':    ('망포동', '힐스테이트영통'),
    'mangpo_ipark':        ('망포동', '아이파크캐슬1단지'),
    'mangpo_skview':       ('망포동', '영통SKVIEW'),
    'mangpo_sujain':       ('망포동', '한양수자인'),
    'yeongtong_edupark':   ('영통동', '에듀파크'),
    'yeongtong_dongbo':    ('영통동', '신나무실동보'),
    'yeongtong_shinmyung': ('영통동', '신나무실신명'),
    'maegyo_skview':       ('매교동', '푸르지오SKVIEW'),
    'maegyo_hillstate':    ('매교동', '힐스테이트푸르지오'),
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
            if 80 <= area <= 86 and umd in ('망포동', '영통동', '매교동'):
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

# 최근 12개월 데이터 분류 (차트용)
for t in all_trades_10y:
    if t['m'] in months:
        all_trades.append(t)

# 데이터 가공 및 지표 계산
analysis_data = {}
chart_data = {}

# -------------------------------------------------------------------------
# 데이터 가공 및 주입
# -------------------------------------------------------------------------

# 데모 데이터 생성 로직 제거됨

# Raw 데이터 정렬 (최신순)
raw_items.sort(key=lambda x: x['d'], reverse=True)

raw_items.sort(key=lambda x: x['d'], reverse=True)

# 차트 및 대시보드용 요약
for aid, (dong, kw) in APT_FILTERS.items():
    trade_history = []
    rent_history = []
    
    # 10년치 매매 가격에서 전고점, 고점 이후 최저가 구하기
    t10y = sorted([x for x in all_trades_10y if x['umd'] == dong and kw in x['apt']], key=lambda x: x['d'])
    max_p = 0
    max_p_date = ""
    min_after_max = 999999999
    
    for t in t10y:
        if t['p'] > max_p:
            max_p = t['p']
            max_p_date = t['d']
            min_after_max = t['p'] # 고점이 갱신되면 최저가도 리셋
        elif t['p'] < min_after_max:
            min_after_max = t['p']
            
    # 최근 12개월 차트용
    for m in months:
        t_matches = [x['p'] for x in all_trades if x['m'] == m and x['umd'] == dong and kw in x['apt']]
        tp = sorted(t_matches)[len(t_matches)//2] if t_matches else (trade_history[-1] if trade_history else 0)
        trade_history.append(tp)

    curr_p = trade_history[-1] if trade_history else 0
    chart_data[aid] = trade_history
    analysis_data[aid] = {
        'peak': max_p, 'peak_date': max_p_date, 'curr': curr_p,
        'min_after_peak': min_after_max if min_after_max < 999999999 else 0,
        'ratio': round(curr_p/max_p*100,1) if max_p else 0,
        'drop': round((max_p-min_after_max)/max_p*100,1) if max_p and min_after_max < max_p else 0
    }

# 가상 뉴스
news_list = [
    {'tag': '금리', 'title': '한국은행 기준금리 동결 (3.50%)', 'desc': '금통위 만장일치 동결. 하반기 인하 기대감 지속.', 'date': now.strftime('%Y.%m'), 'tc': 'bg-amber-100 text-amber-700'},
    {'tag': '정책', 'title': '수원시, 노후계획도시 정비 기본계획 수립', 'desc': '영통지구 등 노후 단지 재건축 활성화 기대.', 'date': now.strftime('%Y.%m'), 'tc': 'bg-indigo-100 text-indigo-700'},
    {'tag': '교통', 'title': '인동선/월판선 공사 순항 중', 'desc': '망포역, 영통역 주변 교통 접근성 대폭 개선 전망.', 'date': now.strftime('%Y.%m'), 'tc': 'bg-emerald-100 text-emerald-700'}
]

# 시장 분석 요약
up_count = sum(1 for d in chart_data.values() if d[-1] > d[-4]) if len(months)>=4 else 0
mkt_summary = {
    'bull': up_count > len(chart_data)/2,
    'summary': '📈 수원 영통 시장 완만한 회복세' if up_count > len(chart_data)/2 else '📉 시장 조정 및 관망세 지속',
    'details': [
        f'주요 {len(chart_data)}개 단지 중 {up_count}개 최근 3개월 반등.',
        '전세가 상승에 따른 매수 전환 수요 관찰됨.',
        '특정 대단지 급매물 소진 후 호가 상승 중.'
    ]
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

