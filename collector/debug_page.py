"""진단용: 한 종목 페이지에서 유통가능 물량 부분이 어떻게 보이는지 출력합니다.
실행:  python debug_page.py 2324     (숫자 = 종목 번호)
"""
import re
import sys
from fetch_ipo import download, html_to_text, DETAIL_URL

no = sys.argv[1] if len(sys.argv) > 1 else "2324"
text = html_to_text(download(DETAIL_URL.format(no=no)))
print("글자 수:", len(text))
for kw in ["총공모주식수", "유통가능", "총계", "합계", "총 계"]:
    hits = list(re.finditer(kw, text))
    print(f"\n=== '{kw}' 발견 {len(hits)}곳 ===")
    for m in hits[:2]:
        a = max(0, m.start() - 40)
        print("...", text[a:m.start() + 240], "...")
