import urllib.request, xml.etree.ElementTree as ET, ssl

key = "4b7ee22fae222a8c2abb5e3f41bb9d54bef87843d68922dcbbe9b55824817d12"
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

keywords = ['자이센트럴','신나무실','동보']
lawd_cds = ['41117','41115']
months = ['202501','202502','202503','202504','202601','202602','202603']

results = set()
for month in months:
    for cd in lawd_cds:
        url = f"https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade?serviceKey={key}&pageNo=1&numOfRows=1000&LAWD_CD={cd}&DEAL_YMD={month}"
        try:
            root = ET.fromstring(urllib.request.urlopen(urllib.request.Request(url), context=ctx).read())
            for item in root.iter('item'):
                umd = item.findtext('umdNm') or ''
                apt = item.findtext('aptNm') or ''
                area = float(item.findtext('excluUseAr') or '0')
                price = item.findtext('dealAmount') or '0'
                if any(k in apt for k in keywords):
                    results.add(f"[{umd}] {apt} | {area}sqm | {price.strip()}")
        except:
            pass

with open(r"C:\Users\재영\.gemini\antigravity\scratch\search2.txt", "w", encoding="utf-8") as f:
    for r in sorted(results):
        f.write(r + "\n")
