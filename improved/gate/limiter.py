"""改进版限流闸口：精确滑动窗口 + 可注入时钟 + 有界内存 + 线程安全。

与 gate_v1 相比的关键差异（详见 NOTES.md）：

1. 滑动窗口（accept 时间戳队列）而不是固定窗口，消除「窗口边界 2x 突发」。
2. 只依赖单调时钟；时钟若回拨，内部时钟原地冻结，不重复发放额度。
3. 内存有上界：超限时先清理过期桶，再按 LRU 淘汰最久未使用的 key。
4. 拒绝路径不创建新桶，伪造 key 无法撑爆内存。
5. key 类型强校验，避免 None/int 混用坍缩成同一个桶。
6. 线程安全；对外暴露 Decision，可拿到 remaining / retry_after。
"""

from __future__ import annotations

import math
import threading
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Deque, Optional

from .clock import Clock, system_clock

DEFAULT_MAX_KEYS = 10_000


@dataclass(frozen=True)
class Decision:
    """一次限流判定的完整结果。"""

    allowed: bool
    limit: int
    remaining: int
    retry_after: float
    """秒。allowed 时恒为 0.0；拒绝时表示最早一个额度何时释放。"""
    reset_at: float
    """秒。窗口完全清空的时钟读数（可用作 X-RateLimit-Reset）。"""

    def __bool__(self) -> bool:
        # 让 `if gate.check(key):` 这种写法能直观工作。
        return self.allowed

    @property
    def retry_after_ms(self) -> int:
        """retry_after 的毫秒整数表示，可直接放进 Retry-After 头。"""
        return int(math.ceil(self.retry_after * 1000))


class _Bucket:
    """单个 key 的滑动窗口状态：窗口内被放行的时间戳，升序。"""

    __slots__ = ("hits",)

    def __init__(self) -> None:
        self.hits: Deque[float] = deque()

    def evict_before(self, threshold: float) -> None:
        """丢掉所有 <= threshold 的旧命中（它们已经滑出窗口）。"""
        hits = self.hits
        while hits and hits[0] <= threshold:
            hits.popleft()


class Gate:
    """按 key 计数的滑动窗口限流闸口。

    参数
    ----
    limit:      每个窗口内允许的请求数，>= 1 的整数。
    window:     窗口长度（秒），> 0。
    clock:      返回秒的可调用对象，默认 time.monotonic。测试注入 ManualClock。
    max_keys:   最多跟踪多少个 key，超出按 LRU 淘汰。<= 0 表示不限制（谨慎使用）。

    线程安全：所有状态变更都在内部锁里完成，同一个实例可在多线程下共享。
    进程安全：状态在内存里，多进程/多实例部署请换成 Redis 等共享后端。
    """

    __slots__ = (
        "_buckets",
        "_clock",
        "_last_now",
        "_limit",
        "_lock",
        "_max_keys",
        "_window",
    )

    def __init__(
        self,
        limit: int,
        window: float = 1.0,
        *,
        clock: Optional[Clock] = None,
        max_keys: int = DEFAULT_MAX_KEYS,
    ) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError(f"limit 必须是 int，收到 {type(limit).__name__}")
        if limit < 1:
            raise ValueError(f"limit 必须 >= 1，收到 {limit}")

        window = float(window)
        if not math.isfinite(window) or window <= 0:
            raise ValueError(f"window 必须是有限正数，收到 {window}")

        if isinstance(max_keys, bool) or not isinstance(max_keys, int):
            raise TypeError(f"max_keys 必须是 int，收到 {type(max_keys).__name__}")

        self._limit = limit
        self._window = window
        self._clock = clock if clock is not None else system_clock
        self._max_keys = max_keys
        self._buckets: "OrderedDict[str, _Bucket]" = OrderedDict()
        self._lock = threading.Lock()
        # 单调时钟回拨时内部时钟冻结在这个读数上。
        self._last_now = -math.inf

    # ------------------------------------------------------------------ 核心

    def check(self, key: str) -> Decision:
        """判定一次请求，并在放行时消耗一个额度。"""
        self._validate_key(key)

        with self._lock:
            now = self._now()

            bucket = self._buckets.get(key)
            if bucket is None:
                # 只在新 key 确实要被放行时才建桶：拒绝路径不分配内存。
                bucket = self._buckets[key] = _Bucket()
                self._enforce_capacity()
            else:
                self._buckets.move_to_end(key)

            bucket.evict_before(now - self._window)
            hits = bucket.hits

            if len(hits) < self._limit:
                hits.append(now)
                return Decision(
                    allowed=True,
                    limit=self._limit,
                    remaining=self._limit - len(hits),
                    retry_after=0.0,
                    reset_at=hits[0] + self._window,
                )

            oldest = hits[0]
            return Decision(
                allowed=False,
                limit=self._limit,
                remaining=0,
                retry_after=max(0.0, oldest + self._window - now),
                reset_at=oldest + self._window,
            )

    def allow(self, key: str) -> bool:
        """兼容 gate_v1 的布尔接口。"""
        return self.check(key).allowed

    def reset(self, key: Optional[str] = None) -> None:
        """清空某个 key 的额度；key 为 None 时清空全部。"""
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._validate_key(key)
                self._buckets.pop(key, None)

    # ------------------------------------------------------------ 运维/观测

    def sweep(self) -> int:
        """主动清理所有已过期的桶，返回清理掉的 key 数量。"""
        with self._lock:
            now = self._now()
            threshold = now - self._window
            stale = [k for k, b in self._buckets.items() if not b.hits or b.hits[-1] <= threshold]
            for k in stale:
                del self._buckets[k]
            return len(stale)

    def stats(self) -> dict:
        """给监控用的快照，不加锁读到的数字可能有一个请求的误差。"""
        with self._lock:
            return {
                "tracked_keys": len(self._buckets),
                "max_keys": self._max_keys,
                "limit": self._limit,
                "window": self._window,
            }

    def __len__(self) -> int:
        with self._lock:
            return len(self._buckets)

    # ---------------------------------------------------------------- 内部

    def _now(self) -> float:
        """读取时钟，并保证返回给限流逻辑的时间永不倒退。"""
        now = float(self._clock())
        if now < self._last_now:
            # 时钟回拨：冻结在历史最高点。既不会凭空多发额度，
            # 也不会因为窗口「永远差一点过期」而长期误封。
            return self._last_now
        self._last_now = now
        return now

    def _enforce_capacity(self) -> None:
        """新 key 加入后调用，保证桶数量不超过 max_keys。"""
        if self._max_keys <= 0 or len(self._buckets) <= self._max_keys:
            return

        # 先尝试回收真正过期的空桶（最久未使用的一定在头部）。
        threshold = self._last_now - self._window
        limit = self._max_keys
        while len(self._buckets) > limit:
            key, bucket = next(iter(self._buckets.items()))
            if bucket.hits and bucket.hits[-1] > threshold:
                break  # 头部这个桶还活跃，后面的更活跃，只能 LRU 淘汰
            del self._buckets[key]

        # 仍然超限说明活跃 key 比容量还多，按 LRU 淘汰，保证内存有上界。
        while len(self._buckets) > limit:
            self._buckets.popitem(last=False)

    @staticmethod
    def _validate_key(key: str) -> None:
        if not isinstance(key, str):
            raise TypeError(
                f"key 必须是 str，收到 {type(key).__name__}。"
                "不同类型的 key 混用会坍缩到同一个桶，请显式统一格式。"
            )
