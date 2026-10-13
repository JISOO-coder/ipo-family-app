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


def _float_shares(text: str, offered: int):
    """'공모후 유통가능 물량' 표 → (상장일 유통가능 주식수, 그중 기존주주 주식수). 못 읽으면 None
    표 모양이 회사마다 달라서 머리글을 보고 칸 순서를 정함:
      '…매각제한물량 유통가능물량' 이면 합계 줄의 마지막 칸이 유통가능,
      '…유통가능물량 매각제한물량' 이면 끝에서 두 번째 칸이 유통가능,
      유통가능 칸이 없으면 '공모 후 − 매각제한' 으로 계산."""
    head = re.search(r"공모\s*후\s*유통\s*가능\s*물량(?:\([^)]*\))?", text)
    if not head:
        return None
    end = text.find("요약재무", head.end())
    table = text[head.end(): end if end > 0 else head.end() + 8000]   # 재무제표의 '총계'를 잘못 읽지 않게
    # '주식수 지분율' 한 쌍 (지분율에 %가 빠진 표도 있음)
    pair = r"([\d,]{4,})\s+(\d{1,3}(?:\.\d+)?)\s*%?(?=\s|$)"
    tot = None
    for t in re.finditer(r"(?:총\s*계|합\s*계)", table):              # 표의 마지막 합계 줄
        if re.search(pair, table[t.end():t.end() + 300]):
            tot = t
    if not tot:
        return None
    pairs = re.findall(pair, table[tot.end():tot.end() + 300])
    if len(pairs) < 2:
        return None
    a, b = int(_num(pairs[-2][0])), int(_num(pairs[-1][0]))
    hdr = table[:300]
    t_at = re.search(r"유통\s*가능\s*물량", hdr)
    r_at = re.search(r"(?:매각\s*제한|보호\s*예수)\s*물량", hdr)
    tradable_first = bool(t_at and r_at and t_at.start() < r_at.start())
    if t_at and r_at:
        tradable = a if tradable_first else b
    elif r_at:
        if len(pairs) < 3:
            return None
        tradable = a - b
    else:
        tradable = b                                                  # 머리글을 못 읽으면 예전 방식
    public = _public_tradable(table[:tot.start()], offered, tradable_first)
    existing = tradable - public
    if tradable <= 0 or existing < 0:
        return None                                                   # 앞뒤가 안 맞으면 못 읽은 것으로
    return tradable, existing


def _row_pairs(s: str) -> list:
    """표 한 줄의 글자 → [주식수, …] (빈칸 '-'는 0). 줄 이름 같은 한글은 건너뛰고, 다음 한글이 나오면 줄 끝"""
    toks = s.split()
    i = 0
    while i < len(toks) and re.search(r"[가-힣]", toks[i]):
        i += 1
    cells = []
    for tk in toks[i:]:
        if re.search(r"[가-힣]", tk):
            break
        cells.append(tk)
    if len(cells) % 2:
        cells = cells[:-1]                                            # 끝의 '기간' 칸 '-'
    return [int(_num(c)) if re.fullmatch(r"[\d,]+", c) else 0 for c in cells[::2]]


def _public_tradable(body: str, offered: int, tradable_first: bool) -> int:
    """공모주 중 상장일에 팔 수 있는 주식수
    1순위: '공모주주 소계' 줄의 유통가능 칸 (우리사주·주관사 의무인수처럼 묶인 물량이 빠진 값)
    2순위: 총공모주식수 − 공모주주 구간의 우리사주 물량
    (기존주주 중에도 '우리사주조합'이 있을 수 있어, 공모주주 구간 이후에 나오는 것만 셈)"""
    m = re.search(r"공모주주[^\d%]{0,20}?소계", body)
    if m:
        cols = _row_pairs(body[m.end():m.end() + 200])
        if len(cols) >= 2:
            v = cols[-2] if tradable_first else cols[-1]
            if 0 < v <= offered:
                return v
    pub = re.search(r"공모주주|공모주식|신주모집|일반공모", body)
    sec = body[pub.start():] if pub else body
    m = re.search(r"우리사주", sec)
    if m:
        n = re.search(r"[\d,]{4,}", sec[m.end():m.end() + 120])
        locked = int(_num(n.group())) if n else 0
        if 0 < locked < offered:
            return offered - locked
    return offered


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

    out = {"name": name, "market": None, "sub_start": sub_start, "sub_end": sub_end,
           "listing_date": None, "band_low": None, "band_high": None,
           "final_price": None, "inst_competition": None, "lockup_ratio": None,
           "float_amount": None, "existing_holder_ratio": None,
           "broker": None, "brokers": []}

    m = re.search(r"시장구분\s*(코스닥|유가증권|코넥스)", text)
    if m:
        out["market"] = m.group(1)

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
    fs = _float_shares(text, offered) if offered else None
    if fs:
        tradable, existing = fs
        out["existing_holder_ratio"] = round(existing / tradable * 100, 2)
        price = out["final_price"] or out["band_high"]
        if price:
            out["float_amount"] = round(tradable * price / 1e8, 1)
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
        d["no"] = str(no)                       # 38 종목 번호 (상장 결과 기록에서 같은 종목을 찾는 데 씀)
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
