"""실행: python test_push.py  (실제로 보내지 않고 계산만 시험)"""
import base64
import datetime as dt
import json

from push import events_for, subscriptions

ITEMS = [
    {"name": "가나", "broker": "KB증권", "brokers": ["KB증권", "NH투자증권"],
     "sub_start": "2026-10-20", "sub_end": "2026-10-21", "listing_date": "2026-10-29"},
    {"name": "다라", "broker": "대신증권", "sub_start": "2026-10-01", "sub_end": "2026-10-02",
     "listing_date": "2026-10-21"},
    {"name": "미정", "broker": "삼성증권", "sub_start": "2026-10-21", "sub_end": "2026-10-22",
     "listing_date": None},
]


def test_events_for_day():
    ev = events_for(ITEMS, dt.date(2026, 10, 21))
    assert [(e["name"], e["kind"]) for e in ev] == [("가나", "sub_end"), ("다라", "listing"),
                                                     ("미정", "sub_start")]
    assert ev[0]["key"] == "가나|2026-10-20" and ev[0]["brokers"] == ["KB증권", "NH투자증권"]
    assert ev[1]["brokers"] == ["대신증권"]                     # brokers 없으면 대표 1곳

def test_no_events():
    assert events_for(ITEMS, dt.date(2026, 10, 25)) == []

def test_subscriptions_from_secrets():
    sub = {"endpoint": "https://example.push/abc", "keys": {"p256dh": "x", "auth": "y"}}
    code = base64.urlsafe_b64encode(json.dumps(sub).encode()).decode().rstrip("=")
    secrets = json.dumps({"PUSH_SUB_JISOO": code + "\n", "VAPID_PRIVATE_KEY": "k",
                          "PUSH_SUB_BAD": "!!!", "github_token": "t"})
    subs = subscriptions(secrets)
    assert list(subs) == ["PUSH_SUB_JISOO"] and subs["PUSH_SUB_JISOO"] == sub


if __name__ == "__main__":
    fns = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for f in fns:
        f(); print("OK ", f.__name__)
    print(f"\n{len(fns)}개 테스트 모두 통과")
