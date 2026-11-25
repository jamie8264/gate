"""v1 与改进版共用的测试设施。

所有测试都通过 `build()` 构造限流器，参数名两边统一；v1 缺的能力
（可注入时钟、内存上界）由 `inject_v1_clock()` / `patch_v1_max_keys()` 补上，
这样同一个场景可以在两个实现上逐字对比。
"""

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# 原始版在 src/，改进版在 improved/，两个包名不同，可以同时导入。
for _path in (ROOT / "src", ROOT / "improved"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

V1 = "v1"
IMPROVED = "improved"
BOTH_IMPLS = (V1, IMPROVED)

V1_LIMITER = "gate_v1.limiter"
V1_PACKAGE = "gate_v1"

# 缺陷用例都标 xfail(strict=True)：默认跑是绿的，--runxfail 能看到真实报错，
# 一旦缺陷被修掉就变成 XPASS 而报错，提醒来更新用例。
DEFECT = pytest.mark.xfail(
    strict=True,
    reason="gate_v1 的已知缺陷，已由 improved/gate 修复",
)


def build(impl, limit, window=1.0, *, clock=None, max_keys=None):
    """按名字构造限流器，参数名两边统一。"""
    if impl == V1:
        from gate_v1 import Gate

        return Gate(limit, window)

    from gate import Gate

    kwargs = {}
    if clock is not None:
        kwargs["clock"] = clock
    if max_keys is not None:
        kwargs["max_keys"] = max_keys
    return Gate(limit, window, **kwargs)


def inject_v1_clock(monkeypatch, clock):
    """把 v1 内部的 time.time 换成可注入时钟。

    v1 里写的是 `time.time()`，所以给它一个只暴露 time() 的替身模块即可。
    """
    limiter = importlib.import_module(V1_LIMITER)

    class _ClockModule:
        @staticmethod
        def time():
            return clock()

    monkeypatch.setattr(limiter, "time", _ClockModule)


def patch_v1_max_keys(monkeypatch, max_keys):
    """v1 没有内存上界，测试里就地给它补一个（只为量出真实水位）。"""
    limiter = importlib.import_module(V1_LIMITER)

    original = limiter.Gate.__init__

    def __init__(self, limit, window=1.0):
        original(self, limit, window)
        self.max_keys = max_keys
        # 说明：这里刻意不实现淘汰逻辑，只是为了给测试暴露统一属性名。

    monkeypatch.setattr(limiter.Gate, "__init__", __init__)


@pytest.fixture
def clock():
    """手动时钟：时间只在测试显式推进时才走，永远不会 flaky。"""
    from gate import ManualClock

    return ManualClock(0.0)


@pytest.fixture
def gate_factory(clock):
    def _make(limit, window=1.0, **kwargs):
        return build(IMPROVED, limit, window, clock=clock, **kwargs)

    return _make


def pytest_generate_tests(metafunc):
    """凡是参数名叫 impl 的测试，自动在 v1 和改进版上各跑一遍。"""
    if "impl" in metafunc.fixturenames:
        metafunc.parametrize("impl", BOTH_IMPLS, ids=BOTH_IMPLS)
