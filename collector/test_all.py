"""실행: python test_all.py   (설치할 것 없음)"""
import datetime as dt
import json
from pathlib import Path
from grading import Ipo, grade, margin_for_10_shares
import build

TODAY = dt.date(2026, 10, 13)
# 실제 수집 데이터(data/raw.json)는 매일 바뀌므로, 테스트는 고정 샘플 3건을 씀
SAMPLE = Path(__file__).resolve().parent / "test_sample_raw.json"


def load_sample():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


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

def test_exception1_label():
    assert grade(make(inst_competition=600, lockup_ratio=36, float_amount=900))["reason"] == "예외1: 확약 35% 이상"

def test_exception3_big_strong_demand():
    g = grade(make(inst_competition=1100, lockup_ratio=26, float_amount=2000))
    assert g["grade"] == 4 and g["reason"] == "예외3: 수요 강한 중대형주"

def test_exception3_needs_lockup_25():
    assert grade(make(inst_competition=1100, lockup_ratio=24, float_amount=2000))["show"] is False

def test_msbio_real_values_pass():
    # 2026-10 엠에스바이오 실제 값 (기존주주 비율은 우리사주를 뺀 새 계산 기준)
    ms = Ipo("엠에스바이오", 6800, 7800, 7800, 1096.56, 30.62, 495.1, 39.5)
    assert grade(ms)["reason"] == "예외3: 수요 강한 중대형주"

def test_exception4_high_lockup_allows_existing_under_70():
    # 큐리오시스(2025-11) 실제 값: 기존주주 53.8%였지만 확약 55.7%
    g = grade(make(inst_competition=1031, lockup_ratio=55.7, float_amount=552,
                   existing_holder_ratio=53.8))
    assert g["show"] is True and g["reason"].startswith("예외4")

def test_exception4_limits():
    assert grade(make(lockup_ratio=49, existing_holder_ratio=55))["show"] is False       # 확약 부족
    assert grade(make(lockup_ratio=60, existing_holder_ratio=70))["show"] is False       # 기존주주 70% 이상
    assert grade(make(lockup_ratio=60, existing_holder_ratio=55,
                      inst_competition=400))["show"] is False                            # 경쟁률 부족
    assert grade(make(lockup_ratio=60, existing_holder_ratio=55,
                      final_price=11000))["show"] is False                               # 밴드 상단 미만

def test_missing_float_shown_as_check():
    base = dict(name="표못읽음", band_low=10000, band_high=12000, final_price=12000,
                inst_competition=1200, lockup_ratio=20, float_amount=None,
                existing_holder_ratio=None, sub_start="2026-10-20", sub_end="2026-10-21",
                listing_date="2026-10-29", broker="KB증권")
    items = build.build_items([base], TODAY)
    assert len(items) == 1 and items[0]["check"] is True
    weak = dict(base, name="약함", inst_competition=300)          # 어느 규칙으로도 통과 불가
    assert build.build_items([weak], TODAY) == []

def test_listing_date_missing_still_shown():
    r = dict(load_sample()[0], listing_date=None)
    items = build.build_items([r], TODAY)
    assert len(items) == 1 and items[0]["listing_date"] is None
    ics = build.build_ics(items, TODAY)
    assert ics.count("BEGIN:VEVENT") == 2                      # 청약 시작·마감만

def test_only_passing_items_shown():
    raw = load_sample()
    items = build.build_items(raw, TODAY)
    assert [i["name"] for i in items] == ["샘플알짜"]
    assert items[0]["margin"] == 60000
    assert items[0]["brokers"] == ["미래에셋증권"]   # brokers 없으면 대표 1곳으로

def test_listed_items_dropped():
    raw = load_sample()
    assert build.build_items(raw, dt.date(2026, 12, 1)) == []

def test_ics():
    raw = load_sample()
    ics = build.build_ics(build.build_items(raw, TODAY), TODAY)
    assert ics.count("BEGIN:VEVENT") == 3
    assert ics.count("TRIGGER:-PT10M") == 3
    assert "DTSTART:20261020T000000Z" in ics   # 청약 시작 10/20 09:00 KST
    assert "DTSTART:20261021T000000Z" in ics   # 청약 마감 10/21 09:00 KST
    assert "DTSTART:20261029T000000Z" in ics   # 상장일   10/29 09:00 KST
    assert all(len(l.encode()) <= 75 for l in ics.split("\r\n"))


if __name__ == "__main__":
    fns = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for f in fns:
        f()
        print("OK ", f.__name__)
    print(f"\n{len(fns)}개 테스트 모두 통과")
