"""상장 결과 분석: data/history.json 을 '지금 필터'로 다시 판정해서 통과/탈락 종목의 상장일 수익률 비교
실행: python report.py   (사이트 접속 없음. 수익률은 공모가 대비 %)
"""
import json
import statistics as st
from pathlib import Path

from build import judge

HISTORY = Path(__file__).resolve().parent.parent / "data" / "history.json"


def summary(label: str, recs: list):
    if not recs:
        print(f"{label}: 0건")
        return
    o = [r["open_return"] for r in recs]
    c = [r["close_return"] for r in recs]
    print(f"{label}: {len(recs)}건 | 시초가 평균 {st.mean(o):+.1f}% 중앙값 {st.median(o):+.1f}% "
          f"| 첫날종가 평균 {st.mean(c):+.1f}% 중앙값 {st.median(c):+.1f}% "
          f"| 시초가 손실 {sum(x < 0 for x in o)}건 | 시초가 +100% 이상 {sum(x >= 100 for x in o)}건")


def line(r: dict) -> str:
    def v(k, f="{}"):
        return "-" if r.get(k) is None else f.format(r[k])
    top = ("상단초과" if r["final_price"] > r["band_high"] else
           "상단" if r["final_price"] == r["band_high"] else "상단미만")
    return (f"  {r['listing_date']} {r['name'][:14]:<14} [{r.get('market') or '?'}] "
            f"시초 {r['open_return']:+.0f}% 종가 {r['close_return']:+.0f}% | "
            f"경쟁률 {v('inst_competition', '{:.0f}')} 확약 {v('lockup_ratio', '{:.1f}')}% "
            f"유통 {v('float_amount', '{:.0f}')}억 기존주주 {v('existing_holder_ratio', '{:.1f}')}% "
            f"{top} | {r['now_reason']}")


def main():
    recs = [r for r in json.loads(HISTORY.read_text(encoding="utf-8")) if r.get("open_price")]
    for r in recs:
        g = judge(r)
        r["now_pass"], r["now_reason"] = (g["show"], g["reason"]) if g else (False, "판정 불가")
    recs.sort(key=lambda r: r["listing_date"])
    passed = [r for r in recs if r["now_pass"]]
    failed = [r for r in recs if not r["now_pass"]]
    print(f"기간: {recs[0]['listing_date']} ~ {recs[-1]['listing_date']} (스팩 제외 {len(recs)}건)\n")
    summary("전체", recs)
    summary("통과(앱에 나왔을 종목)", passed)
    summary("탈락", failed)
    print("\n[통과 종목]")
    for r in passed:
        print(line(r))
    print("\n[탈락했지만 시초가 +100% 이상]")
    for r in sorted(failed, key=lambda r: -r["open_return"]):
        if r["open_return"] >= 100:
            print(line(r))
    print("\n[탈락 사유별 건수]")
    reasons = {}
    for r in failed:
        reasons[r["now_reason"]] = reasons.get(r["now_reason"], 0) + 1
    for k, n in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  {k}: {n}건")


if __name__ == "__main__":
    main()
