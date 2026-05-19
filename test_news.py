import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

query = "수원 부동산"
url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"

req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
        data = resp.read()
        root = ET.fromstring(data)
        items = root.findall('.//item')
        print(f"Found {len(items)} news items.")
        for idx, item in enumerate(items[:5]):
            title = item.findtext('title')
            link = item.findtext('link')
            pub_date = item.findtext('pubDate')
            print(f"{idx+1}. {title} ({pub_date}) - {link}")
except Exception as e:
    print(f"Error fetching news: {e}")
