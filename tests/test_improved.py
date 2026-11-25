"""改进版独有的契约：Decision 语义、参数校验、时钟防护、与参考模型逐位一致。"""

import math
import random

import pytest

from gate import Decision, Gate, ManualClock


# ------------------------------------------------------------------ Decision


def test_decision_reports_remaining_and_reset(clock):
    gate = Gate(limit=3, window=10.0, clock=clock)
    clock.advance(100.0)

    first = gate.check("k")
    assert isinstance(first, Decision)
    assert (first.allowed, first.remaining) == (True, 2)
    assert first.retry_after == 0.0
    assert first.reset_at == pytest.approx(110.0)

    gate.check("k")
    third = gate.check("k")
    assert (third.allowed, third.remaining) == (True, 0)

    blocked = gate.check("k")
    assert (blocked.allowed, blocked.remaining) == (False, 0)
    # 额度在最早的命中滑出窗口时释放：t=100 的那一发在 t=110 释放。
    assert blocked.retry_after == pytest.approx(10.0)
    assert blocked.retry_after_ms == 10_000


def test_decision_retry_after_shrinks_as_time_passes(clock):
    gate = Gate(limit=1, window=10.0, clock=clock)

    assert gate.allow("k") is True
    clock.advance(4.0)
    d = gate.check("k")
    assert d.allowed is False
    assert d.retry_after == pytest.approx(6.0)


def test_decision_is_truthy_when_allowed(clock):
    gate = Gate(limit=1, window=10.0, clock=clock)
    assert bool(gate.check("k")) is True
    assert bool(gate.check("k")) is False
    # 拒绝的判定也能安全地放进上报头里
    assert gate.check("k").retry_after_ms > 0


# ------------------------------------------------------------------ 参数校验


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 0},
        {"limit": -1},
        {"limit": 1.5},
        {"limit": True},
        {"limit": 1, "window": 0},
        {"limit": 1, "window": -1.0},
        {"limit": 1, "window": float("inf")},
        {"limit": 1, "window": float("nan")},
        {"limit": 1, "max_keys": "10"},
    ],
)
def test_invalid_config_is_rejected_loudly(kwargs):
    """配置错误必须在构造时炸，而不是在第一次请求时才炸。"""
    with pytest.raises((TypeError, ValueError)):
        Gate(**kwargs)


def test_reset_none_clears_everything(clock):
    gate = Gate(limit=1, window=10.0, clock=clock)
    gate.allow("a")
    gate.allow("b")
    assert len(gate) == 2

    gate.reset()  # None 表示「全部清空」，不是「key=None」
    assert len(gate) == 0


# ------------------------------------------------------------------ 时钟防护


def test_clock_rewind_does_not_reissue_quota(clock):
    """单调时钟回拨时，内部时间冻结，不会凭空多发额度。"""
    gate = Gate(limit=1, window=10.0, clock=clock)

    clock.advance(20.0)
    assert gate.allow("k") is True
    assert gate.allow("k") is False

    clock.rewind(10.0)  # 模拟 NTP 校准，真实时间退回 t=10
    assert gate.allow("k") is False, "回拨不该像 v1 那样重新发一个额度"
    assert gate.allow("k") is False, "而且持续被冻结，不会越试越有额度"

    # 冻结期间消耗掉 10 秒：真实时间 t=20，内部时钟仍是 t=20，尚未过期。
    clock.advance(10.0)
    assert gate.allow("k") is False

    # 再走 10 秒，真实时间 t=30，最早那次命中（t=20）才滑出窗口。
    clock.advance(10.0)
    assert gate.allow("k") is True


def test_default_clock_is_monotonic():
    gate = Gate(limit=1, window=1.0)
    assert gate._clock is __import__("time").monotonic


# ------------------------------------------------------------------ 参考模型


def _reference_allow(timeline, limit, window):
    """教科书式滑动窗口：只保留窗口内的命中，简单到不可能错。"""
    hits = []
    out = []
    for now in timeline:
        hits = [t for t in hits if t > now - window]
        if len(hits) < limit:
            hits.append(now)
            out.append(True)
        else:
            out.append(False)
    return out


@pytest.mark.parametrize("seed", range(12))
def test_matches_reference_model_on_random_timelines(seed):
    rng = random.Random(seed)
    limit = rng.randint(1, 6)
    window = rng.choice([1.0, 2.5, 10.0])

    gate = Gate(limit=limit, window=window, clock=ManualClock(0.0))
    clock = gate._clock

    timeline = []
    expected_now = 0.0
    for _ in range(200):
        step = rng.choice([0.0, 0.0, 0.1, 0.5, 1.0, 3.0])
        expected_now += step
        clock._now = expected_now  # 直接设定，保证和参考模型的输入完全一致
        timeline.append(round(expected_now, 6))

    expected = _reference_allow([round(t, 6) for t in timeline], limit, window)

    clock._now = 0.0
    gate._last_now = -math.inf
    actual = []
    for t in timeline:
        clock._now = t
        actual.append(gate.allow("k"))

    assert actual == expected
