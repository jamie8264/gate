"""时钟。

限流器应该只用单调时钟：墙钟（time.time）会被 NTP 校准、手工改时间、
容器迁移来回拨动，一旦回拨，原本已经过期的窗口就永远不过期了。
"""

from __future__ import annotations

import time
from typing import Callable

# 一个可调用对象，返回「秒」为单位的浮点时间戳。
Clock = Callable[[], float]

# 默认时钟：单调递增，不受系统时间调整影响。
system_clock: Clock = time.monotonic


class ManualClock:
    """测试用时钟：时间只在显式调用 advance/rewind 时前进或后退。"""

    __slots__ = ("_now",)

    def __init__(self, start: float = 0.0) -> None:
        self._now = float(start)

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> float:
        if seconds < 0:
            raise ValueError(f"advance 需要非负秒数，收到 {seconds}")
        self._now += float(seconds)
        return self._now

    def rewind(self, seconds: float) -> float:
        """模拟墙钟回拨。单调时钟不该出现这种行为，测试用它来验证防护。"""
        self._now -= float(seconds)
        return self._now

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"ManualClock({self._now})"
