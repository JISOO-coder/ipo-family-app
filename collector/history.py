"""상장 결과 기록 → data/history.json  (필터가 실제로 맞았는지 나중에 확인하기 위한 자료)
매일 자동 실행 끝에 돌아갑니다. 설치할 것 없음.
1) 오늘 수집한 종목(raw.json) 중 수요예측 결과가 나온 종목의 판정 값을 기록 (탈락 종목도 함께)
2) 38커뮤니케이션 '신규상장' 목록에서 시초가·첫날 종가를 채움
3) history.json 이 없으면(처음 한 번) 지난 24개월 상장 종목을 거꾸로 모아 채움
실행: python history.py               기간을 직접 정할 때: python history.py --backfill 24
사이트 접속이 안 되면 경고만 남기고 끝납니다(앱 데이터 갱신을 막지 않음).
"""
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

from build import judge
from fetch_ipo import DELAY_SEC, DETAIL_URL, download, html_to_text, parse_detail

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw.json"
HISTORY = ROOT / "data" / "history.json"
KST = dt.timezone(dt.timedelta(hours=9))

LISTED_URL = "http://www.38.co.kr/html/fund/index.htm?o=nw&page={page}"
BACKFILL_MONTHS = 24    # history.json 이 없을 때 거꾸로 모을 기간
RECENT_DAYS = 30        # 매일 실행 때, 기록에 없던 최근 상장 종목은 상세 페이지를 읽어 채움
MAX_PAGES = 20          # 신규상장 목록을 넘겨 보는 최대 쪽수

# 판정 당시 값으로 남겨 둘 항목 (나중에 기준을 바꿔도 같은 값으로 다시 판정해 볼 수 있게)
KEEP = ["name", "market", "sub_start", "sub_end", "listing_date", "band_low", "band_high",
        "final_price", "inst_competition", "lockup_ratio", "float_amount",
        "existing_holder_ratio", "broker", "brokers"]


# ---------- 신규상장 목록 해석 ----------
_ROW = re.compile(
    r"o=v&(?:amp;)?no=(\d+)[^>]*>\s*(?:<font[^>]*>)?([^<]+?)(?:</font>)?\s*</a>\s*</td>"  # 번호, 종목명
    r"\s*<td[^>]*>\s*(\d{4})/(\d{2})/(\d{2})\s*</td>"                                      # 신규상장일
    r"((?:\s*<td[^>]*>.*?</td>){7})", re.S)                                                 # 나머지 7칸


def _int(s: str):
    s = s.replace(",", "").strip()
    return int(s) if s.isdigit() else None


def parse_listed(html: str) -> list:
    """신규상장 목록 → [{no, name, listing_date, price, open, close}]
    칸 순서: 현재가 / 전일비 / 공모가 / 공모가대비 / 시초가 / 시초·공모 / 첫날종가 (상장 전이면 '-', '예정')"""
    rows = []
    for m in _ROW.finditer(html):
        cells = [re.sub(r"<[^>]+>|&nbsp;", "", c).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", m.group(6), re.S)]
        if len(cells) < 7:
            continue
        rows.append({"no": m.group(1), "name": m.group(2).strip(),
                     "listing_date": f"{m.group(3)}-{m.group(4)}-{m.group(5)}",
                     "price": _int(cells[2]), "open": _int(cells[4]), "close": _int(cells[6])})
    return rows


# ---------- 기록 ----------
def load() -> dict:
    if not HISTORY.exists():
        return {}
    return {r["no"]: r for r in json.loads(HISTORY.read_text(encoding="utf-8"))}


def save(history: dict):
    recs = sorted(history.values(),
                  key=lambda r: r.get("listing_date") or r.get("sub_start") or "", reverse=True)
    HISTORY.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")


def record_judgement(history: dict, no: str, d: dict, today: dt.date) -> bool:
    """판정 값 기록 (수요예측 결과가 없으면 기록하지 않음). 이미 있으면 최신 값으로 갱신"""
    g = judge(dict(d, broker=d.get("broker") or "?"))   # 주관사를 못 읽어도 판정 기록은 남김
    if g is None:
        return False
    rec = history.setdefault(no, {"no": no})
    rec.update({k: d.get(k) for k in KEEP})
    rec.update({"passed": g["show"], "grade": g["grade"], "reason": g["reason"],
                "judged_at": today.isoformat()})
    return True


def record_result(rec: dict, row: dict, today: dt.date):
    """상장 결과(시초가·첫날 종가)와 공모가 대비 수익률(%) 기록"""
    price = row["price"] or rec.get("final_price")
    if not (price and row["open"] and row["close"]) or rec.get("open_price"):
        return
    rec.update({"listing_date": row["listing_date"], "open_price": row["open"],
                "close_price": row["close"],
                "open_return": round((row["open"] / price - 1) * 100, 1),
                "close_return": round((row["close"] / price - 1) * 100, 1),
                "result_at": today.isoformat()})


def apply_rows(history: dict, rows: list, fetch_since: dt.date, today: dt.date) -> int:
    """목록의 상장 결과를 기록에 반영. 기록에 없던 종목은 fetch_since 이후 상장분만 상세 페이지를 읽어 추가"""
    added = 0
    for row in rows:
        if row["open"] is None or "스팩" in row["name"]:
            continue                                   # 아직 상장 전이거나 스팩(판정 대상 아님)
        if row["no"] not in history:
            if dt.date.fromisoformat(row["listing_date"]) < fetch_since:
                continue
            time.sleep(DELAY_SEC)
            try:
                d = parse_detail(html_to_text(download(DETAIL_URL.format(no=row["no"]))))
            except Exception as e:
                print(f"  {row['name']} 상세 페이지 실패: {e}")
                continue
            if not d or not record_judgement(history, row["no"], d, today):
                continue                               # 수요예측 정보가 없는 종목
            added += 1
        record_result(history[row["no"]], row, today)
    return added


def main():
    today = dt.datetime.now(KST).date()
    months = BACKFILL_MONTHS
    if "--backfill" in sys.argv:
        i = sys.argv.index("--backfill")
        months = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else BACKFILL_MONTHS
    first_run = not HISTORY.exists() or "--backfill" in sys.argv
    fetch_since = today - dt.timedelta(days=months * 31 if first_run else RECENT_DAYS)

    history = load()
    try:
        # 1) 오늘 수집한 종목의 판정 값
        raw = json.loads(RAW.read_text(encoding="utf-8")) if RAW.exists() else []
        judged = sum(record_judgement(history, r["no"], r, today) for r in raw if r.get("no"))
        print(f"판정 기록: {judged}건")

        # 2) 신규상장 목록에서 결과 채우기 (처음이면 지난 몇 달치까지 거꾸로)
        added = 0
        for page in range(1, MAX_PAGES + 1):
            if page > 1:
                time.sleep(DELAY_SEC)
            rows = parse_listed(download(LISTED_URL.format(page=page)))
            if not rows:
                break
            added += apply_rows(history, rows, fetch_since, today)
            if min(r["listing_date"] for r in rows) < fetch_since.isoformat():
                break                                  # 이 쪽에서 기간을 다 봤음
        print(f"새로 추가한 상장 종목: {added}건")
    except Exception as e:                             # 사이트 문제 등 → 모은 데까지만 저장
        print("상장 결과 기록 중 문제가 생겼습니다(앱 데이터에는 영향 없음):", e)
    save(history)
    done = sum(1 for r in history.values() if r.get("open_price"))
    print(f"저장 완료: 전체 {len(history)}건 (상장 결과까지 있는 종목 {done}건) → {HISTORY}")


if __name__ == "__main__":
    main()
