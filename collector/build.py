"""data/raw.json → 등급 판정 → data/ipos.json (앱용) + web/ipo.ics (캘린더 구독용)"""
import datetime as dt
import json
from pathlib import Path

from grading import Ipo, grade, margin_for

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw.json"
OUT_JSON = ROOT / "data" / "ipos.json"
OUT_ICS = ROOT / "web" / "ipo.ics"
KST = dt.timezone(dt.timedelta(hours=9))

# 판정에 꼭 필요한 값. 하나라도 비어 있으면(수요예측 전 등) 노출하지 않음
REQUIRED = ["name", "band_low", "band_high", "final_price", "inst_competition",
            "lockup_ratio", "float_amount", "existing_holder_ratio",
            "sub_start", "sub_end", "listing_date", "broker"]


def build_items(raw: list, today: dt.date) -> list:
    items = []
    for r in raw:
        if any(r.get(k) is None for k in REQUIRED):
            continue
        if dt.date.fromisoformat(r["listing_date"]) < today:
            continue  # 이미 상장 끝난 종목은 제외
        ipo = Ipo(r["name"], r["band_low"], r["band_high"], r["final_price"],
                  r["inst_competition"], r["lockup_ratio"], r["float_amount"],
                  r["existing_holder_ratio"])
        g = grade(ipo)
        if not g["show"]:
            continue
        shares = r.get("min_shares") or 10
        items.append({
            "name": r["name"], "broker": r["broker"],
            "sub_start": r["sub_start"], "sub_end": r["sub_end"],
            "listing_date": r["listing_date"],
            "final_price": r["final_price"],
            "min_shares": shares,
            "margin": margin_for(r["final_price"], shares),
            "inst_competition": r["inst_competition"],
            "lockup_ratio": r["lockup_ratio"],
            "grade": g["grade"], "reason": g["reason"],
            "tag": "★ 추천 공모주",
        })
    items.sort(key=lambda x: x["sub_start"])
    return items


# ---------- 캘린더(.ics) ----------
def _esc(s: str) -> str:
    return (s.replace("\\", "\\\\").replace(";", "\\;")
             .replace(",", "\\,").replace("\n", "\\n"))


def _fold(line: str) -> list:
    """ICS는 한 줄 75바이트 제한 → 초과 시 접기(한글 깨짐 방지)"""
    b, out, limit = line.encode("utf-8"), [], 75
    while len(b) > limit:
        cut = limit
        while (b[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(b[:cut].decode("utf-8"))
        b, limit = b[cut:], 74
    out.append(b.decode("utf-8"))
    return [out[0]] + [" " + p for p in out[1:]]


def build_ics(items: list, today: dt.date) -> str:
    stamp = today.strftime("%Y%m%d") + "T000000Z"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//ipo-family-app//KO",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "X-WR-CALNAME:공모주 알림", "X-WR-TIMEZONE:Asia/Seoul"]
    kinds = [("sub_start", "청약 시작"), ("sub_end", "청약 마감"),
             ("listing_date", "상장일")]
    for it in items:
        for key, label in kinds:
            d = dt.date.fromisoformat(it[key])
            # 09:00 KST = 00:00 UTC. 알람은 10분 전 = 08:50
            start = d.strftime("%Y%m%d") + "T000000Z"
            end = d.strftime("%Y%m%d") + "T010000Z"
            desc = (f"주간사: {it['broker']}\n10주 증거금: {it['margin']:,}원\n"
                    f"공모가: {it['final_price']:,}원\n{it['reason']}")
            lines += ["BEGIN:VEVENT",
                      f"UID:{it['name']}-{key}-{it[key]}@ipo-family",
                      f"DTSTAMP:{stamp}", f"DTSTART:{start}", f"DTEND:{end}",
                      f"SUMMARY:{_esc('★ ' + it['name'] + ' ' + label)}",
                      f"DESCRIPTION:{_esc(desc)}",
                      "BEGIN:VALARM", "ACTION:DISPLAY",
                      f"DESCRIPTION:{_esc(it['name'] + ' ' + label)}",
                      "TRIGGER:-PT10M", "END:VALARM", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    folded = []
    for ln in lines:
        folded += _fold(ln)
    return "\r\n".join(folded) + "\r\n"


def main():
    today = dt.datetime.now(KST).date()
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    items = build_items(raw, today)
    OUT_JSON.write_text(json.dumps(
        {"updated": today.isoformat(), "items": items},
        ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_ICS.write_text(build_ics(items, today), encoding="utf-8", newline="")
    print(f"완료: 전체 {len(raw)}건 중 {len(items)}건 노출")


if __name__ == "__main__":
    main()
