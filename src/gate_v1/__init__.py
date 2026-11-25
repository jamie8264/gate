"""gate_v1 —— 原始版限流闸口（用于对照，不要在生产使用）。"""

from .limiter import Gate

__all__ = ["Gate"]
__version__ = "0.1.0"
