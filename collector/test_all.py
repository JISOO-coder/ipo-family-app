"""실행: python test_all.py   (설치할 것 없음)"""
import datetime as dt
import json
from grading import Ipo, grade, margin_for_10_shares
import build

TODAY = dt.date(2026, 10, 13)


def make(**kw):
    base = dict(name="테스트", band_low=10000, band_high=12000, final_price=12000,
                inst_competition=1100, lockup_ratio=16, float_amount=350,
                existing_holder_ratio=10)
    base.update(kw)
    return Ipo(**base)


def test_basic_pass():
    assert grade(make())["grade"] == 4

def test_five_star():
    assert grade(make(final_price=13000, inst_competition=1600,
                      lockup_ratio=26, float_amount=250))["grade"] == 5

def test_big_deal_exception():
    assert grade(make(inst_competition=600, lockup_ratio=36, float_amount=900))["grade"] == 4

def test_light_exception():
    assert grade(make(inst_competition=850, lockup_ratio=11, float_amount=150))["grade"] == 4

def test_reject_existing_holders():
    assert grade(make(existing_holder_ratio=50))["show"] is False

def test_reject_band_low():
    assert grade(make(final_price=10000))["show"] is False

def test_fail_low_competition():
    assert grade(make(inst_competition=300))["show"] is False

def test_margin():
    assert margin_for_10_shares(12000) == 60000

def test_only_passing_items_shown():
    raw = json.loads(build.RAW.read_text(encoding="utf-8"))
    items = build.build_items(raw, TODAY)
    assert [i["name"] for i in items] == ["샘플알짜"]
    assert items[0]["margin"] == 60000

def test_listed_items_dropped():
    raw = json.loads(build.RAW.read_text(encoding="utf-8"))
    assert build.build_items(raw, dt.date(2026, 12, 1)) == []

def test_ics():
    raw = json.loads(build.RAW.read_text(encoding="utf-8"))
    ics = build.build_ics(build.build_items(raw, TODAY), TODAY)
    assert ics.count("BEGIN:VEVENT") == 3
    assert ics.count("TRIGGER:-PT10M") == 3
    assert "DTSTART:20261020T000000Z" in ics
    assert all(len(l.encode()) <= 75 for l in ics.split("\r\n"))


if __name__ == "__main__":
    fns = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for f in fns:
        f()
        print("OK ", f.__name__)
    print(f"\n{len(fns)}개 테스트 모두 통과")
