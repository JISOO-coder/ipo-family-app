"""실행: python test_history.py  (사이트 접속 없이 저장된 글자로만 시험)"""
import datetime as dt

from history import apply_rows, parse_listed, record_judgement, record_result

TODAY = dt.date(2026, 10, 13)

# 2026-10-13 38커뮤니케이션 '신규상장' 목록의 실제 줄 모양 (상장 완료 1건, 상장 예정 1건, 스팩 1건)
LISTED_HTML = """
<tr><td height=30><a href="./?o=v&amp;no=2324&amp;l=" ><font color="333333">엠에스바이오</font></a></td>
<td  align="center">2026/10/22</td><td  align="right">-&nbsp;</td>
<td  align="right"><font color="333333">%</font>&nbsp;</td><td  align="RIGHT">7,800&nbsp;</td>
<td  align="right"><font color="333333">-%</font>&nbsp;</td><td  align="right">-&nbsp;</td>
<td  align="right"><font color="333333">%</font>&nbsp;</td><td  align="right">예정&nbsp;</td></tr>
<tr bgColor="#FFFFFF"><td height=30><a href="./?o=v&amp;no=2307&amp;l=" ><font color="333333">브릴스</font></a></td>
<td  align="center">2026/10/01</td><td  align="right">18,860&nbsp;</td>
<td  align="right"><font color="0066CC">-7.78%</font>&nbsp;</td><td  align="RIGHT">19,500&nbsp;</td>
<td  align="right"><font color="0066CC">-3.28%</font>&nbsp;</td><td  align="right">61,800&nbsp;</td>
<td  align="right"><font color="E3231E">216.92%</font>&nbsp;</td><td  align="right">31,350&nbsp;</td></tr>
<tr><td height=30><a href="./?o=v&amp;no=2290&amp;l=" ><font color="333333">KB스팩34호</font></a></td>
<td  align="center">2026/09/22</td><td  align="right">1,895&nbsp;</td>
<td  align="right"><font color="0066CC">-0.05%</font>&nbsp;</td><td  align="RIGHT">2,000&nbsp;</td>
<td  align="right"><font color="0066CC">-5.25%</font>&nbsp;</td><td  align="right">4,000&nbsp;</td>
<td  align="right"><font color="E3231E">100%</font>&nbsp;</td><td  align="right">1,905&nbsp;</td></tr>
"""

BRILS = dict(name="브릴스", market="코스닥", sub_start="2026-09-18", sub_end="2026-09-19",
             listing_date="2026-10-01", band_low=16000, band_high=19500, final_price=19500,
             inst_competition=1200.5, lockup_ratio=20.0, float_amount=300.0,
             existing_holder_ratio=10.0, broker="KB증권", brokers=["KB증권"])


def test_parse_listed_rows():
    rows = parse_listed(LISTED_HTML)
    assert [r["name"] for r in rows] == ["엠에스바이오", "브릴스", "KB스팩34호"]
    assert rows[0]["open"] is None and rows[0]["close"] is None          # 상장 예정
    assert rows[1] == {"no": "2307", "name": "브릴스", "listing_date": "2026-10-01",
                       "price": 19500, "open": 61800, "close": 31350}

def test_record_judgement_keeps_failed_too():
    h = {}
    assert record_judgement(h, "1", dict(BRILS, inst_competition=300.0), TODAY)
    assert h["1"]["passed"] is False and h["1"]["reason"] == "기준 미달"
    assert record_judgement(h, "2", dict(BRILS, inst_competition=None), TODAY) is False  # 수요예측 전

def test_result_and_returns():
    h = {}
    record_judgement(h, "2307", BRILS, TODAY)
    added = apply_rows(h, parse_listed(LISTED_HTML), TODAY, TODAY)   # 이미 기록된 종목만 → 접속 없음
    assert added == 0
    r = h["2307"]
    assert (r["open_price"], r["close_price"]) == (61800, 31350)
    assert r["open_return"] == 216.9 and r["close_return"] == 60.8
    assert "2290" not in h                                            # 스팩은 기록 안 함

def test_result_written_once():
    rec = dict(BRILS, open_price=1)
    record_result(rec, {"listing_date": "2026-10-01", "price": 19500, "open": 2, "close": 3}, TODAY)
    assert rec["open_price"] == 1


if __name__ == "__main__":
    fns = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for f in fns:
        f(); print("OK ", f.__name__)
    print(f"\n{len(fns)}개 테스트 모두 통과")
