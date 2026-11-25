"""一致性测试：两个实现都必须通过，用来证明改进版没有破坏原有契约。"""

import time

from conftest import build


def test_allows_exactly_limit_then_blocks(impl):
    gate = build(impl, limit=3, window=0.2)
    assert [gate.allow("k") for _ in range(3)] == [True, True, True]
    assert [gate.allow("k") for _ in range(5)] == [False] * 5


def test_window_expiry_restores_quota(impl):
    gate = build(impl, limit=2, window=0.05)
    assert gate.allow("k") is True
    assert gate.allow("k") is True
    assert gate.allow("k") is False

    time.sleep(0.08)
    assert gate.allow("k") is True


def test_keys_are_independent(impl):
    gate = build(impl, limit=1, window=0.2)
    assert gate.allow("alice") is True
    assert gate.allow("alice") is False
    assert gate.allow("bob") is True


def test_allow_returns_real_bool(impl):
    """返回值必须是 True/False，而不是被隐式转换的其它对象。"""
    gate = build(impl, limit=1, window=0.2)
    assert gate.allow("k") is True
    assert gate.allow("k") is False


def test_rejections_do_not_extend_the_ban(impl):
    """拒绝的请求不占额度，也不应把封禁时间往后推。"""
    gate = build(impl, limit=1, window=0.05)
    assert gate.allow("k") is True
    for _ in range(20):
        assert gate.allow("k") is False

    time.sleep(0.08)
    assert gate.allow("k") is True
