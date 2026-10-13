"""38커뮤니케이션에서 공모주 정보를 가져와 data/raw.json 으로 저장합니다.
설치할 것 없음(파이썬 기본 기능만 사용).  실행:  python fetch_ipo.py
"""
import datetime as dt
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw.json"
MANUAL = ROOT / "data" / "manual.json"      # 직접 고치고 싶을 때 쓰는 파일(선택)
KST = dt.timezone(dt.timedelta(hours=9))

LIST_URL = "http://www.38.co.kr/html/fund/index.htm?o=k"
DETAIL_URL = "http://www.38.co.kr/html/fund/?o=v&no={no}"
UA = "Mozilla/5.0 (personal family IPO notifier)"
MAX_ITEMS = 40          # 최근 종목 번호 큰 순서대로 이만큼만 확인
DELAY_SEC = 0.8         # 사이트에 부담 주지 않도록 쉬는 시간


# ---------- 웹 가져오기 ----------
def _opener(relaxed: bool):
    """relaxed=True: 오래된 서버(38)와도 접속되도록 보안 수준을 낮춘 연결"""
    if not relaxed:
        return urllib.request.build_opener()
    ctx = ssl.create_default_context()
    try:
        ctx.set_ciphers("DEFAULT@SECLEVEL=0")
        ctx.minimum_version = ssl.TLSVersion.TLSv1
        ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
    except Exception:
        pass
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def download(url: str) -> str:
    last = None
    for relaxed in (False, True):          # 1차: 보통 연결, 2차: 완화된 연결
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with _opener(relaxed).open(req, timeout=25) as r:
                data = r.read()
            return data.decode("cp949", errors="replace")   # 38 사이트는 EUC-KR(cp949)
        except urllib.error.URLError as e:
            last = e
            if not isinstance(e.reason, ssl.SSLError):
                raise                       # SSL 문제가 아니면 바로 알림
        except ssl.SSLError as e:
            last = e
    raise last


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    return re.sub(r"\s+", " ", " ".join(p.parts)).strip()


def list_ids(list_html: str) -> list:
    ids = set(re.findall(r"/html/fund/(?:index\.htm)?\?o=v&(?:amp;)?no=(\d+)", list_html))
    return sorted((int(i) for i in ids), reverse=True)[:MAX_ITEMS]


# ---------- 상세 페이지 해석 ----------
def _num(s):
    return float(s.replace(",", ""))


def _date(y, m, d):
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def _public_float(table: str):
    """유통가능 물량 표에서 '공모주주'가 상장일에 팔 수 있는 주식수. 못 찾으면 None
    표 칸 순서: 공모 전 / 공모 후 / 매각제한 / 유통가능 (각각 '주식수 지분율', 빈칸은 '- -')"""
    m = re.search(r"공모주주\s*소계", table) or re.search(r"공모주주", table)
    if not m:
        return None
    cells = re.findall(r"(-|[\d,]+)\s+(-|[\d.]+\s*%)", table[m.end():m.end() + 300])
    if len(cells) < 4 or cells[3][0] == "-":
        return None
    return int(_num(cells[3][0]))


def parse_detail(text: str):
    """사이트 글자 → 우리 형식. 필수(이름·일정)가 없으면 None."""
    m = re.search(r"종목명\s+(.+?)\s+진행상황", text)
    if not m:
        return None
    name = m.group(1).strip()

    m = re.search(r"공모청약일\s*(\d{4})\.(\d{2})\.(\d{2})\s*~\s*(\d{4})\.(\d{2})\.(\d{2})", text)
    if not m:
        return None
    sub_start, sub_end = _date(*m.group(1, 2, 3)), _date(*m.group(4, 5, 6))

    out = {"name": name, "sub_start": sub_start, "sub_end": sub_end,
           "listing_date": None, "band_low": None, "band_high": None,
           "final_price": None, "inst_competition": None, "lockup_ratio": None,
           "float_amount": None, "existing_holder_ratio": None,
           "broker": None, "brokers": []}

    m = re.search(r"(?<!신규)상장일\s*(\d{4})\.(\d{2})\.(\d{2})", text) or \
        re.search(r"신규상장일\s*(\d{4})\.(\d{2})\.(\d{2})", text)
    if m:
        out["listing_date"] = _date(*m.group(1, 2, 3))

    m = re.search(r"희망공모가액\s*([\d,]+)\s*~\s*([\d,]+)\s*원", text)
    if m:
        out["band_low"], out["band_high"] = int(_num(m.group(1))), int(_num(m.group(2)))

    for m in re.finditer(r"확정공모가\W*([\d,]+)\s*원", text):
        out["final_price"] = int(_num(m.group(1)))
        break

    m = re.search(r"기관경쟁률\W*([\d,]+(?:\.\d+)?)\s*:\s*1", text)
    if m:
        out["inst_competition"] = _num(m.group(1))
    m = re.search(r"의무보유확약\W*([\d.]+)\s*%", text)
    if m:
        out["lockup_ratio"] = float(m.group(1))

    # 주관사: 인수회사 표에서 '대표주관'을 우선
    brokers, lead = [], None
    for m in re.finditer(
            r"([가-힣A-Za-z0-9·&]+?(?:증권|금융투자))\s+[\d,]+\s*(?:~\s*[\d,]+\s*)?주\s+"
            r"[\d,]+\s*(?:~\s*[\d,]+\s*)?주\s+([가-힣]*)", text):
        brokers.append(m.group(1))
        if "대표" in m.group(2) and lead is None:
            lead = m.group(1)
    if not brokers:
        m = re.search(r"주간사\s+(.+?)\s+주식수", text)
        if m:
            brokers = [b.strip() for b in m.group(1).split(",") if b.strip()]
    if brokers:
        out["brokers"] = brokers
        out["broker"] = lead or brokers[0]

    # 상장일 유통가능 물량 → 유통금액(억원), 기존주주 비율(%)
    m = re.search(r"총공모주식수\s*([\d,]+)\s*주", text)
    offered = int(_num(m.group(1))) if m else None
    head = re.search(r"공모\s*후\s*유통\s*가능\s*물량", text)
    if head and offered:
        seg = text[head.start():]
        tot = None
        for t in re.finditer(r"(?:총\s*계|합\s*계)", seg):   # 표의 마지막 합계 줄
            tot = t
            if re.search(r"[\d,]{4,}\s+[\d.]+\s*%", seg[t.start():t.start() + 300]):
                break
        if tot:
            pairs = re.findall(r"([\d,]{4,})\s+([\d.]+)\s*%", seg[tot.start():tot.start() + 300])
            if pairs:
                float_shares = int(_num(pairs[-1][0]))
                # 기존주주 물량 = 전체 유통가능 − 공모주 중 상장일에 팔 수 있는 물량
                # (우리사주 1년·상장주선인 의무인수분은 공모주라도 못 팔기 때문에 빼고 셈)
                public = _public_float(seg[:tot.start()])
                if not (public and public <= offered and public <= float_shares):
                    public = offered if float_shares >= offered else None   # 표를 못 읽으면 예전 방식
                if public:
                    out["existing_holder_ratio"] = round(
                        (float_shares - public) / float_shares * 100, 2)
                    price = out["final_price"] or out["band_high"]
                    if price:
                        out["float_amount"] = round(float_shares * price / 1e8, 1)
    if out["inst_competition"] is None:
        out["lockup_ratio"] = None
    return out


# ---------- 전체 흐름 ----------
def main():
    today = dt.datetime.now(KST).date()
    try:
        ids = list_ids(download(LIST_URL))
    except Exception as e:                      # 사이트 접속 실패 → 기존 데이터 유지
        print("목록 페이지를 가져오지 못했습니다:", e)
        sys.exit(1)
    if not ids:                                  # 차단/개편 등으로 목록이 비어 있음
        print("종목 목록을 찾지 못했습니다. (사이트 변경 또는 접속 차단 가능성)")
        sys.exit(1)
    print(f"확인할 종목 {len(ids)}개")

    items, parsed = [], 0
    for no in ids:
        try:
            time.sleep(DELAY_SEC)
            d = parse_detail(html_to_text(download(DETAIL_URL.format(no=no))))
        except Exception as e:
            print(f"  no={no} 실패: {e}")
            continue
        if not d:
            print(f"  no={no} 해석 실패(건너뜀)")
            continue
        parsed += 1
        end_of_life = d["listing_date"] or d["sub_end"]
        if dt.date.fromisoformat(end_of_life) < today:
            continue                            # 이미 끝난 종목
        items.append(d)
        print(f"  {d['name']}: 경쟁률={d['inst_competition']} 확약={d['lockup_ratio']}% "
              f"유통={d['float_amount']}억 확정가={d['final_price']}")

    if parsed == 0:                              # 한 건도 못 읽었으면 기존 데이터 보존
        print("종목 상세를 하나도 해석하지 못했습니다. 기존 데이터를 그대로 둡니다.")
        sys.exit(1)

    # 직접 고친 값(manual.json)이 있으면 같은 이름 종목에 덮어씀
    if MANUAL.exists():
        for m in json.loads(MANUAL.read_text(encoding="utf-8")):
            hit = next((x for x in items if x["name"] == m.get("name")), None)
            if hit:
                hit.update({k: v for k, v in m.items() if v is not None})
            else:
                items.append(m)

    items.sort(key=lambda x: x["sub_start"])
    RAW.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장 완료: {len(items)}건 → {RAW}")


if __name__ == "__main__":
    main()
