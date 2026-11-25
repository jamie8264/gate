"""实测对比：同一组请求，三种实现分别放行了多少。

运行：.venv/bin/python examples/demo.py
"""

import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "improved")]

from gate import Gate, ManualClock  # noqa: E402
from gate_v1 import Gate as GateV1  # noqa: E402


def line(title):
    print(f"\n{title}\n" + "-" * 62)


class SlowStore:
    """模拟带网络往返的远程存储（Redis/DB）。"""

    def __init__(self, latency):
        self._data = {}
        self._latency = latency

    def get(self, slot):
        time.sleep(self._latency)
        return self._data.get(slot)

    def set(self, slot, value):
        time.sleep(self._latency)
        self._data[slot] = value

    def clear(self):
        self._data.clear()

    def drop_key(self, key):
        for s in [k for k in self._data if k[0] == key]:
            del self._data[s]

    def __len__(self):
        return len(self._data)


def demo_boundary_burst():
    line("1) 固定窗口的边界突发（limit=5/秒，看 0.2 秒内能过几个）")

    clock = ManualClock(0.0)

    class _T:
        @staticmethod
        def time():
            return clock()

    import gate_v1.limiter as v1

    v1.time = _T
    old = GateV1(limit=5, window=1.0)

    clock._now = 0.9
    a = sum(old.allow("ip") for _ in range(5))
    clock._now = 1.1
    b = sum(old.allow("ip") for _ in range(5))
    print(f"  gate_v1        : 0.9s 放行 {a} 个 + 1.1s 放行 {b} 个 = {a + b} 个")

    nogate = Gate(limit=5, window=1.0, clock=clock)
    clock._now = 0.9
    c = sum(nogate.allow("ip") for _ in range(5))
    clock._now = 1.1
    d = sum(nogate.allow("ip") for _ in range(5))
    print(f"  improved/gate  : 0.9s 放行 {c} 个 + 1.1s 放行 {d} 个 = {c + d} 个")


def demo_concurrency():
    line("2) 并发超发（limit=1，8 线程同时打同一个 key，存储有 10ms 往返）")

    results = {"v1": 0, "improved": 0}

    for name in ("v1", "improved"):
        if name == "v1":
            g = GateV1(1, 60.0, store=SlowStore(0.01))
        else:
            g = Gate(1, 60.0)

        barrier = threading.Barrier(8)
        got = []
        lock = threading.Lock()

        def worker():
            barrier.wait()
            r = g.allow("shared")
            with lock:
                got.append(r)

        ts = [threading.Thread(target=worker) for _ in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        results[name] = sum(got)

    print(f"  gate_v1        : 限 1 个，实际放行 {results['v1']} 个")
    print(f"  improved/gate  : 限 1 个，实际放行 {results['improved']} 个")


def demo_memory():
    line("3) 内存（2 万个伪造 key，每个一次请求）")

    v1 = GateV1(1, 60.0)
    for i in range(20_000):
        v1.allow(f"forged-{i}")
    print(f"  gate_v1        : 留下 {len(v1.store):>6} 个桶，0 回收，无上界")

    clock = ManualClock(0.0)
    g = Gate(1, 60.0, clock=clock, max_keys=1_000)
    for i in range(20_000):
        g.allow(f"forged-{i}")
    print(f"  improved/gate  : 留下 {len(g):>6} 个桶（max_keys=1000，LRU 淘汰）")


def demo_latency():
    line("4) 单线程耗时（10 万次 allow 调用）")
    n = 100_000

    v1 = GateV1(10_000, 60.0)
    t0 = time.perf_counter()
    for i in range(n):
        v1.allow("k")
    v1_t = time.perf_counter() - t0
    print(f"  gate_v1        : {v1_t * 1000:7.1f} ms  ({n / v1_t / 1000:.0f} 万次/秒)")

    clock = ManualClock(0.0)
    g = Gate(10_000, 60.0, clock=clock)
    t0 = time.perf_counter()
    for i in range(n):
        g.allow("k")
    t = time.perf_counter() - t0
    print(f"  improved/gate  : {t * 1000:7.1f} ms  ({n / t / 1000:.0f} 万次/秒)")
    print(f"  代价           : {t / v1_t:.1f}x —— 换来上面三条正确性")


if __name__ == "__main__":
    demo_boundary_burst()
    demo_concurrency()
    demo_memory()
    demo_latency()
    print()
