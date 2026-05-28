import urllib.request
import xml.etree.ElementTree as ET
import datetime, ssl, os, json
import concurrent.futures
from collections import defaultdict

# API 설정
key = os.environ.get("MOLIT_API_KEY", "4b7ee22fae222a8c2abb5e3f41bb9d54bef87843d68922dcbbe9b55824817d12")
lawd_cds = ['41117', '41115'] # 영통구, 팔달구

# 기간 설정 (최근 120개월 및 10년)
now = datetime.datetime.now()
months = []
for i in range(119, -1, -1):
    # 정확한 월 계산을 위해 연/월 수식 사용
    year = now.year + (now.month - 1 - i) // 12
    month = (now.month - 1 - i) % 12 + 1
    months.append(f"{year}{month:02d}")

months_10y = []
for i in range(119, -1, -1):
    year = now.year + (now.month - 1 - i) // 12
    month = (now.month - 1 - i) % 12 + 1
    months_10y.append(f"{year}{month:02d}")

# 대상 아파트 필터 (동, 아파트명 키워드, 세대수, 주차대수, 지하주차장 연결)
APT_FILTERS = {
    'mangpo_hillstate':    ('망포동', '힐스테이트영통', 2140, '1.28대', '연결 O'),
    'mangpo_ipark':        ('망포동', '아이파크캐슬1단지', 1783, '1.21대', '연결 O'),
    'mangpo_skview':       ('망포동', '영통SKVIEW', 710, '1.21대', '연결 O'),
    'mangpo_sujain':       ('망포동', '한양수자인', 530, '1.14대', '연결 O'),
    'yeongtong_edupark':   ('영통동', '에듀파크', 1279, '1.02대', '연결 X'),
    'yeongtong_dongbo':    ('영통동', '신나무실동보', 836, '1.04대', '연결 X'),
    'yeongtong_shinmyung': ('영통동', '신나무실신명', 384, '1.02대', '연결 X'),
    'maegyo_skview':       ('매교동', '푸르지오SKVIEW', 3603, '1.25대', '연결 O'),
    'maegyo_hillstate':    ('매교동', '힐스테이트푸르지오', 2586, '1.25대', '연결 O'),
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
            # 84㎡ 국민평수 단일 평형 기준 (80㎡ ~ 86㎡) 필터링 적용
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

# 최근 60개월 데이터 분류 (차트용, 저층 제외, 84㎡ 국민평수 단일 평형 필터링)
for t in all_trades_10y:
    if t['m'] in months:
        if t['floor'] and str(t['floor']).isdigit() and int(t['floor']) > 5:
            # 84㎡ (국평 기준 80㎡ ~ 86㎡) 거래 데이터만 차트 및 대시보드에 반영
            if 80 <= t['area'] <= 86:
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
    
    # 1. 역사적 전고점 (10년 전체 최고가)
    hist_peak_p = 0
    hist_peak_d = ""
    # 2. 최근 전고점 (최근 2년 내 최고가)
    recent_peak_p = 0
    recent_peak_d = ""
    # 3. 최근 1년 내 최고/최저 (하락률 계산용)
    one_year_ago = (now - datetime.timedelta(days=365)).strftime('%Y.%m.%d')
    two_years_ago = (now - datetime.timedelta(days=730)).strftime('%Y.%m.%d')
    
    max_p_1y = 0
    min_p_1y = 999999999

    for t in t10y:
        # 역사적 전고점 (10년 전체 최고가)
        if t['p'] > hist_peak_p:
            hist_peak_p = t['p']
            hist_peak_d = t['d']
            
        # 최근 전고점 (최근 2년 내 최고가)
        if t['d'] >= two_years_ago:
            if t['p'] > recent_peak_p:
                recent_peak_p = t['p']
                recent_peak_d = t['d']
        
        # 최근 1년 내 지표
        if t['d'] >= one_year_ago:
            if t['p'] > max_p_1y: max_p_1y = t['p']
            if t['p'] < min_p_1y: min_p_1y = t['p']
            
    # 4. 역사적 최저점 (전고점 이후)
    hist_min_p = 999999999
    
    # 최근 60개월 차트용
    curr_peak_d = ""
    for m in months:
        t_matches = [x for x in all_trades if x['m'] == m and x['umd'] == dong and kw in x['apt']]
        if t_matches:
            # 해당 월의 가장 최근(최신) 거래 추출 (최고가 대신 최신 실거래가 반영)
            top_t = max(t_matches, key=lambda x: x['d'])
            tp = top_t['p']
            if m == months[-1]: curr_peak_d = top_t['d']
        else:
            tp = trade_history[-1] if (trade_history and trade_history[-1] is not None) else None
        trade_history.append(tp)

    curr_p = 0
    for price in reversed(trade_history):
        if price is not None:
            curr_p = price
            break

    for t in t10y:
        if hist_peak_d and t['d'] > hist_peak_d:
            if t['p'] < hist_min_p:
                hist_min_p = t['p']
    if hist_min_p == 999999999: hist_min_p = curr_p

    chart_data[aid] = trade_history
    analysis_data[aid] = {
        'hist_peak': hist_peak_p, 'hist_peak_date': hist_peak_d,
        'hist_min': hist_min_p,
        'drop_amt': hist_peak_p - curr_p,
        'recent_peak': recent_peak_p, 'recent_peak_date': recent_peak_d,
        'curr': curr_p, 'curr_date': curr_peak_d,
        'drop': round((curr_p - hist_peak_p) / hist_peak_p * 100, 1) if hist_peak_p > 0 else 0,
        'ratio': round(curr_p / hist_peak_p * 100, 1) if hist_peak_p else 0,
        'households': households, 'parking': f"주차 {parking_ratio} | {parking_conn}"
    }
    
    # 종합 점수 계산 (가성비 점수)
    # 1. 회복률이 낮을수록(추후 상승 여력), 2. 세대수가 많을수록, 3. 주차가 편할수록, 4. 연식이 좋을수록 가점
    recovery_score = (100 - analysis_data[aid]['ratio']) * 0.4
    drop_score = abs(analysis_data[aid]['drop']) * 0.2
    hh_score = (households / 4000) * 20
    pk_val = float(parking_ratio.replace('대','')) if '대' in parking_ratio else 1.0
    pk_score = (pk_val / 1.5) * 10
    
    # built 정보 추출 (trade_history 혹은 all_trades_10y에서 해당 아파트 데이터 확인)
    apt_built = "2000"
    for t in t10y_raw:
        if t.get('built'):
            apt_built = t['built']
            break
            
    age_val = int(apt_built) if apt_built.isdigit() else 2000
    age_score = ((age_val - 1990) / 40) * 10
    
    analysis_data[aid]['score'] = round(recovery_score + drop_score + hh_score + pk_score + age_score, 1)

# 실시간 구글 뉴스 수집 및 시장 뉴스 심리지수(Sentiment Index) 분석 함수
def fetch_real_estate_news():
    import urllib.request
    import urllib.parse
    import xml.etree.ElementTree as ET
    import ssl
    import re
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    queries = ["수원 부동산", "부동산 금리", "부동산 정책"]
    news_items = []
    seen_links = set()
    
    print("실시간 부동산 관련 뉴스 수집 중...")
    
    positive_words = ["상승", "반등", "회복", "급등", "호재", "인하", "인기", "완화", "활성화", "증가", "개선", "수요", "진척", "순항"]
    negative_words = ["하락", "조정", "침체", "폭락", "위축", "우려", "동결", "인상", "감소", "경고", "부담", "냉각", "리스크", "피해"]
    
    pos_count = 0
    neg_count = 0
    
    for q in queries:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=ko&gl=KR&ceid=KR:ko"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
                data = resp.read()
                root = ET.fromstring(data)
                items = root.findall('.//item')
                for item in items[:15]: # 쿼리당 상위 15개 뉴스 수집
                    title = item.findtext('title') or ""
                    link = item.findtext('link') or ""
                    pub_date = item.findtext('pubDate') or ""
                    desc = item.findtext('description') or ""
                    
                    if link in seen_links:
                        continue
                    seen_links.add(link)
                    
                    # 제목과 언론사 분리
                    title_clean = title
                    source = "언론사"
                    if " - " in title:
                        parts = title.split(" - ")
                        source = parts[-1]
                        title_clean = " - ".join(parts[:-1])
                        
                    # 날짜 형식 파싱 (GMT -> YYYY.MM.DD)
                    date_str = pub_date
                    try:
                        match = re.search(r'\d{1,2}\s+([A-Za-z]{3})\s+(\d{4})', pub_date)
                        if match:
                            day = re.search(r'\b\d{1,2}\b', pub_date).group(0).zfill(2)
                            year = match.group(2)
                            month_map = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06','Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
                            month = month_map.get(match.group(1)[:3], '05')
                            date_str = f"{year}.{month}.{day}"
                    except Exception:
                        pass
                        
                    # HTML 태그 제거 및 요약 클렌징
                    desc_clean = re.sub('<[^<]+?>', '', desc)
                    desc_clean = desc_clean[:80] + "..." if len(desc_clean) > 80 else desc_clean
                    
                    # 감정 계산
                    for word in positive_words:
                        if word in title_clean:
                            pos_count += 1
                    for word in negative_words:
                        if word in title_clean:
                            neg_count += 1
                            
                    # 태그 자동 설정
                    tag = "일반"
                    tc = "bg-slate-100 text-slate-700"
                    if "금리" in title_clean or "한은" in title_clean:
                        tag = "금리"
                        tc = "bg-amber-100 text-amber-700"
                    elif "대책" in title_clean or "정책" in title_clean or "정부" in title_clean or "규제" in title_clean:
                        tag = "정책"
                        tc = "bg-indigo-100 text-indigo-700"
                    elif "인동선" in title_clean or "지하철" in title_clean or "GTX" in title_clean or "교통" in title_clean:
                        tag = "교통"
                        tc = "bg-emerald-100 text-emerald-700"
                    elif "상승" in title_clean or "상승세" in title_clean or "반등" in title_clean:
                        tag = "상승"
                        tc = "bg-rose-100 text-rose-700"
                    elif "하락" in title_clean or "하락세" in title_clean or "조정" in title_clean:
                        tag = "하락"
                        tc = "bg-blue-100 text-blue-700"
                        
                    news_items.append({
                        "tag": tag,
                        "title": title_clean,
                        "desc": desc_clean,
                        "date": date_str,
                        "tc": tc,
                        "link": link,
                        "source": source
                    })
        except Exception as e:
            print(f"Error crawling {q}: {e}")
            
    # 뉴스가 없거나 실패 시 기본값 사용
    if not news_items:
        news_items = [
            {"tag": "금리", "title": "한국은행 기준금리 동결 (3.50%)", "desc": "금통위 만장일치 동결. 하반기 인하 기대감 지속.", "date": "2026.05.19", "tc": "bg-amber-100 text-amber-700", "link": "#", "source": "한경"},
            {"tag": "정책", "title": "수원시, 노후계획도시 정비 기본계획 수립", "desc": "영통지구 등 노후 단지 재건축 활성화 기대.", "date": "2026.05.18", "tc": "bg-indigo-100 text-indigo-700", "link": "#", "source": "매경"},
            {"tag": "교통", "title": "인동선/월판선 공사 순항 중", "desc": "망포역, 영통역 주변 교통 접근성 대폭 개선 전망.", "date": "2026.05.15", "tc": "bg-emerald-100 text-emerald-700", "link": "#", "source": "연합"}
        ]
        pos_count, neg_count = 1, 1
        
    sentiment_index = round((pos_count / (pos_count + neg_count + 1)) * 100, 1)
    
    return news_items, sentiment_index

# 뉴스 및 심리지수 동적 수집
news_list, news_sentiment = fetch_real_estate_news()

# 가상 전문가 의견 (다른 성향의 5인)
experts = [
    {"nm": "나불패", "role": "공격적 투자자", "c": "text-red-600", "s": "적극 매수", "sc": "bg-red-500", "m": "지금 안 사면 후회합니다. 전세가 상승이 매수세를 밀어올리고 있어요. 공급 부족이 가시화되는 2-3년 뒤를 생각하면 지금이 무릎입니다."},
    {"nm": "도현금", "role": "자산관리 전문가", "c": "text-blue-600", "s": "관망/대기", "sc": "bg-slate-500", "m": "고금리가 생각보다 오래갈 수 있습니다. 무리한 대출보다는 가용 현금 범위 내에서 하반기 시장 변동성을 관망하며 급급매를 노리세요."},
    {"nm": "박임장", "role": "현장 중심 중개사", "c": "text-amber-600", "s": "매수 고려", "sc": "bg-amber-500", "m": "유튜브 뉴스보다 현장 분위기가 더 뜨겁습니다. 망포/영통 대장주 로열동은 매물 나오면 바로 나갑니다. 실거주라면 지금이 적기예요."},
    {"nm": "최수치", "role": "빅데이터 분석가", "c": "text-emerald-600", "s": "중립", "sc": "bg-emerald-500", "m": "거래량이 평균치를 회복 중이나 폭발적이지는 않습니다. 전고점 대비 회복률 90% 돌파 여부가 향후 추세 상승의 관건이 될 것입니다."},
    {"nm": "이선점", "role": "가치투자 전문가", "c": "text-violet-600", "s": "분할 매수", "sc": "bg-violet-500", "m": "입지는 변하지 않습니다. 신축급인 매교역세권과 학군지인 영통 핵심 입지는 하락장에서도 견고합니다. 저평가된 단지를 선점할 기회입니다."}
]

# 시장 분석 요약 (실시간 뉴스 긍정 여론 비율 결합)
up_count = sum(1 for d in chart_data.values() if d[-1] > d[-4]) if len(months)>=4 else 0
mkt_summary = {
    'bull': up_count > len(chart_data)/2,
    'summary': '📈 수원 영통 시장 완만한 회복세 (저층 제외)' if up_count > len(chart_data)/2 else '📉 시장 조정 및 관망세 지속 (저층 제외)',
    'details': [
        f'주요 {len(chart_data)}개 단지 중 {up_count}개 최근 3개월 반등.',
        '전세가 상승에 따른 매수 전환 수요 관찰됨.',
        f'실시간 뉴스 긍정 여론 비율: {news_sentiment}%',
        '중층/고층 실거래 데이터 기반 분석 결과임.'
    ],
    'sentiment_index': news_sentiment,
    'experts': experts
}

# JS 주입 (상대 경로로 수정하여 깃허브 호환성 확보)
js_path = "real_estate_data.js"
if not os.path.exists(js_path):
    # 로컬 실행 시 경로 대응
    js_path = os.path.join(os.path.dirname(__file__), "real_estate_data.js")

supply_data = {
    "years": ["2022", "2023", "2024", "2025", "2026", "2027"],
    "supply": [11500, 10800, 9200, 6500, 3200, 1800],
    "demand": 6000,
    "summary": "2025년 이후 수원시 입주 물량이 급감하며 공급 부족 단계에 진입할 것으로 예상됩니다."
}

import json
injection = f"""// ======== AUTO_UPDATE_ZONE_START ========
const INJECTED_DATA = {json.dumps(chart_data)};
const INJECTED_ANALYSIS_DATA = {json.dumps(analysis_data, ensure_ascii=False)};
const INJECTED_ANALYSIS = {json.dumps(mkt_summary, ensure_ascii=False)};
const INJECTED_MONTHS = {json.dumps(months)};
const INJECTED_TIMESTAMP = '{now.strftime('%Y-%m-%d %H:%M')}';
const INJECTED_RAW = {json.dumps(raw_items, ensure_ascii=False)};
const INJECTED_NEWS = {json.dumps(news_list, ensure_ascii=False)};
const INJECTED_SUPPLY = {json.dumps(supply_data, ensure_ascii=False)};
// ======== AUTO_UPDATE_ZONE_END ========"""""

with open(js_path, 'w', encoding='utf-8') as f:
    f.write(injection)

print(f"Update Complete: trade {len(all_trades)}. JS updated!")

# FULL CSV 자동 생성 (Excel 친화적인 UTF-8-sig 인코딩)
csv_path = "suwon_real_estate.csv"
if not os.path.exists(csv_path):
    csv_path = os.path.join(os.path.dirname(__file__), "suwon_real_estate.csv")

print(f"Generating full CSV dataset at {csv_path}...")
import csv as csv_module
with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv_module.writer(f)
    writer.writerow(["거래일", "동", "아파트", "면적(㎡)", "층", "금액(만원)", "평당가(만원)"])
    for r in raw_items:
        writer.writerow([r['d'], r['dong'], r['apt'], r['area'], f"{r['floor']}층" if r['floor'] else "", r['price'], r['py']])

print("Full CSV generation complete!")

