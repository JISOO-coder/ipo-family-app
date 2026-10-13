"""앱 푸시 알림 보내기 (매일 아침 자동 실행 때 한 번)
- data/ipos.json 에서 '오늘' 청약 시작·마감·상장인 종목을 골라 등록된 모든 폰에 보냄
- 문구(내 증권사, 청약함/패스 반영)는 각 폰의 서비스 워커(web/sw.js)가 만듦 → 서버는 개인 선택을 모름
- 비밀 값은 GitHub 저장소 Secret 에서 받음 (자동 실행 설정 collect.yml 에 이름을 적어 둔 것만 넘어옴)
    VAPID_PRIVATE_KEY : 알림용 비밀 키 (한 번만 등록)
    PUSH_SUB_이름      : 폰마다 하나씩, 앱의 '알림 코드'
                         (JISOO, MOM, DAD, EXTRA1~3 칸이 준비돼 있음. 더 필요하면 collect.yml 에 줄 추가)
- 수동 실행에서 '테스트 알림'을 고르면 지금 바로 테스트 알림을 보냄
자동 실행에서만 필요한 설치: pip install pywebpush
"""
import base64
import datetime as dt
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IPOS = ROOT / "data" / "ipos.json"
LOG = ROOT / "data" / "push_log.json"      # 같은 날 두 번 보내지 않도록 마지막으로 보낸 날짜 기록
KST = dt.timezone(dt.timedelta(hours=9))
VAPID_SUB = "https://jisoo-coder.github.io"   # 알림 보내는 쪽 연락처 (경로 없이 주소만 허용됨)
MORNING_UNTIL = 12                         # 이 시각(한국시간) 전 실행에서만 하루 알림을 보냄


def events_for(items: list, today: dt.date) -> list:
    """오늘 일정: [{key, name, kind(sub_start/sub_end/listing), brokers}]"""
    t = today.isoformat()
    out = []
    for it in items:
        base = {"key": it["name"] + "|" + it["sub_start"], "name": it["name"],
                "brokers": it.get("brokers") or [it["broker"]]}
        if it["sub_start"] == t:
            out.append(dict(base, kind="sub_start"))
        if it["sub_end"] == t and it["sub_end"] != it["sub_start"]:
            out.append(dict(base, kind="sub_end"))
        if it.get("listing_date") == t:
            out.append(dict(base, kind="listing"))
    return out


def subscriptions(env: dict) -> dict:
    """환경 변수 중 PUSH_SUB 로 시작하는 것 → {이름: 구독 정보}. 앱의 알림 코드는 base64(JSON)
    (자동 실행 설정에서 폰마다 Secret 하나씩 이름을 적어 넘김. 등록 안 된 칸은 비어 있어 건너뜀)"""
    subs = {}
    for name, val in env.items():
        if not name.startswith("PUSH_SUB") or not (val or "").strip():
            continue
        try:
            s = val.strip()
            subs[name] = json.loads(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode("utf-8"))
        except Exception:
            print(f"{name}: 알림 코드를 읽지 못했습니다 (복사가 덜 됐는지 확인)")
    return subs


def main():
    now = dt.datetime.now(KST)
    test = os.environ.get("PUSH_TEST") == "true"
    key = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    if not key:
        print("VAPID_PRIVATE_KEY 가 없어 알림을 건너뜁니다")
        return
    subs = subscriptions(dict(os.environ))
    if not subs:
        print("등록된 폰(PUSH_SUB_…)이 없어 알림을 건너뜁니다")
        return

    if test:
        payload = {"type": "test"}
    else:
        today = now.date()
        if now.hour >= MORNING_UNTIL:
            print("아침 실행이 아니라 알림을 보내지 않습니다")
            return
        log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}
        if log.get("last_daily") == today.isoformat():
            print("오늘 알림은 이미 보냈습니다")
            return
        items = json.loads(IPOS.read_text(encoding="utf-8")).get("items", [])
        events = events_for(items, today)
        if not events:
            print("오늘 일정이 없어 알림을 보내지 않습니다")
            return
        payload = {"type": "daily", "date": today.isoformat(), "events": events}

    from pywebpush import WebPushException, webpush
    sent = 0
    for name, sub in subs.items():
        try:
            webpush(sub, json.dumps(payload, ensure_ascii=False), vapid_private_key=key,
                    vapid_claims={"sub": VAPID_SUB}, ttl=6 * 3600)
            sent += 1
        except WebPushException as e:
            code = getattr(e.response, "status_code", "")
            hint = " → 이 폰은 알림을 다시 켜고 새 코드로 바꿔 주세요" if code in (404, 410) else ""
            print(f"{name}: 보내기 실패 {code}{hint}")
    print(f"알림 보냄: {sent}/{len(subs)}대 ({payload['type']})")
    if not test and sent:
        LOG.write_text(json.dumps({"last_daily": payload["date"]}), encoding="utf-8")


if __name__ == "__main__":
    main()
