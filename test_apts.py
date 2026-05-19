import urllib.request
import xml.etree.ElementTree as ET
import ssl

key = "4b7ee22fae222a8c2abb5e3f41bb9d54bef87843d68922dcbbe9b55824817d12"
lawd_cds = ['41117', '41115']
months = ['202312', '202401', '202402', '202403']

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

apt_names = set()

for month in months:
    for cd in lawd_cds:
        url = f"https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade?serviceKey={key}&pageNo=1&numOfRows=1000&LAWD_CD={cd}&DEAL_YMD={month}"
        try:
            req = urllib.request.Request(url)
            response = urllib.request.urlopen(req, context=ctx)
            root = ET.fromstring(response.read())
            for item in root.iter('item'):
                umdNm = item.findtext('umdNm') or ''
                aptNm = item.findtext('aptNm') or ''
                excluUseAr = float(item.findtext('excluUseAr') or '0')
                if 80 <= excluUseAr <= 86:
                    apt_names.add(f"[{umdNm}] {aptNm}")
        except:
            pass

with open(r"C:\Users\재영\.gemini\antigravity\scratch\test_apts.txt", "w", encoding="utf-8") as f:
    for name in sorted(apt_names):
        f.write(name + "\n")
