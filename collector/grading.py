from dataclasses import dataclass


@dataclass
class Ipo:
    name: str
    band_low: int                 # 희망 공모가 하단 (원)
    band_high: int                # 희망 공모가 상단 (원)
    final_price: int              # 확정 공모가 (원)
    inst_competition: float       # 기관 경쟁률 (1200 → 1200:1)
    lockup_ratio: float           # 의무보유확약 비율 (%)
    float_amount: float           # 상장일 유통가능금액 (억원)
    existing_holder_ratio: float  # 유통물량 중 기존주주 비율 (%)


def grade(ipo: Ipo) -> dict:
    """grade 5 = 매우 좋음, 4 = 보통 이상, 0 = 미달/금지(앱에 노출 안 함)"""
    # 🛑 무조건 거절
    if ipo.existing_holder_ratio >= 50:
        return {"grade": 0, "show": False, "reason": "기존주주 물량 50% 이상"}
    if ipo.final_price <= ipo.band_low:
        return {"grade": 0, "show": False, "reason": "공모가 밴드 하단 이하"}

    at_or_above_top = ipo.final_price >= ipo.band_high
    above_top = ipo.final_price > ipo.band_high

    # 🌟 매우 좋음
    if (ipo.inst_competition >= 1500 and ipo.lockup_ratio >= 25
            and ipo.float_amount <= 300 and above_top):
        return {"grade": 5, "show": True, "reason": "매우 좋음(5단계)"}

    # 🟢 보통 이상
    if at_or_above_top:
        if (ipo.inst_competition >= 1000 and ipo.lockup_ratio >= 15
                and ipo.float_amount <= 400):
            return {"grade": 4, "show": True, "reason": "기본: 알짜 중소형주"}
        if ipo.inst_competition >= 500 and ipo.lockup_ratio >= 35:
            return {"grade": 4, "show": True, "reason": "예외1: 초대형 대어주"}
        if (ipo.float_amount <= 200 and ipo.inst_competition >= 800
                and ipo.lockup_ratio >= 10):
            return {"grade": 4, "show": True, "reason": "예외2: 초경량주"}

    return {"grade": 0, "show": False, "reason": "기준 미달"}


def margin_for(final_price: int, shares: int = 10, rate: float = 0.5) -> int:
    """청약 증거금 = 공모가 × 수량 × 증거금률(기본 50%)"""
    return int(final_price * shares * rate)


def margin_for_10_shares(final_price: int, margin_rate: float = 0.5) -> int:
    return margin_for(final_price, 10, margin_rate)
