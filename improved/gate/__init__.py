"""改进版限流闸口 `gate`。

对外 API 与 gate_v1 保持兼容（`Gate(limit, window).allow(key) -> bool`），
另外提供 `check(key) -> Decision` 返回剩余额度与建议重试时间。
"""

from .clock import ManualClock
from .limiter import Decision, Gate

__all__ = ["Decision", "Gate", "ManualClock"]
__version__ = "1.0.0"
