"""缺陷复现。

模式：同一个场景写两遍 —— 一遍跑 gate_v1（标 DEFECT，预期失败），
一遍跑 improved/gate（预期通过）。默认 `pytest` 全绿；
`pytest --runxfail` 能看到原始版的真实报错。
"""

import threading
import time

import pytest
from conftest import DEFECT, V1, build, inject_v1_clock


# =====================================================================
# 缺陷 1：固定窗口在格子交界处允许 2x limit 的突发
# =====================================================================


@DEFECT
def test_v1_boundary_burst_exceeds_limit(monkeypatch, clock):
    """limit=5/窗口，任意 1 秒内最多 5 个。v1 在 0.2 秒内放了 10 个。"""
    inject_v1_clock(monkeypatch, clock)
    gate = build(V1, limit=5, window=1.0)

    clock.advance(0.9)  # 卡在第 0 个格子的末尾
    first = [gate.allow("ip") for _ in range(5)]

    clock.advance(0.2)  # t=1.1，进入第 1 个格子，计数清零
    second = [gate.allow("ip") for _ in range(5)]

    total = sum(first) + sum(second)
    assert total <= 5, f"0.2 秒内放行了 {total} 个，limit=5/秒"


def test_improved_boundary_burst_is_rejected(clock, gate_factory):
    """改进版是滑动窗口：同样的时间线，第二个批次一个都进不来。"""
    gate = gate_factory(limit=5, window=1.0)

    clock.advance(0.9)
    assert all(gate.allow("ip") for _ in range(5))

    clock.advance(0.2)  # t=1.1
    assert not any(gate.allow("ip") for _ in range(5))

    clock.advance(0.8)  # t=1.9：最早那批（t=0.9）刚好滑出 1 秒窗口
    assert gate.allow("ip") is True


# =====================================================================
# 缺陷 2：内存无界，且被拒绝的请求也留下垃圾
# =====================================================================


@DEFECT
def test_v1_memory_grows_without_bound(monkeypatch, clock):
    inject_v1_clock(monkeypatch, clock)
    gate = build(V1, limit=1, window=60.0)

    for i in range(20_000):
        gate.allow(f"forged-key-{i}")

    tracked = len(gate.store)
    assert tracked <= 10_000, (
        f"跟踪了 {tracked} 个桶，没有任何上界。"
        "公网服务里攻击者每请求换一个 key 就能把内存打满"
    )


@DEFECT
def test_v1_expired_buckets_are_never_freed(monkeypatch, clock):
    """即使所有窗口都早已过期，v1 也不会释放任何一条记录。"""
    inject_v1_clock(monkeypatch, clock)
    gate = build(V1, limit=5, window=1.0)

    for i in range(1_000):
        gate.allow(f"user-{i}")

    clock.advance(3_600)  # 一小时后，所有窗口都过期了
    gate.allow("user-0")

    assert len(gate.store) < 1_000, "过期桶从不回收，内存只增不减"


def test_improved_memory_is_bounded(clock, gate_factory):
    gate = gate_factory(limit=1, window=60.0, max_keys=1_000)

    for i in range(20_000):
        gate.allow(f"forged-key-{i}")

    assert len(gate) <= 1_000
    assert gate.stats()["tracked_keys"] <= 1_000


def test_improved_rejects_do_not_allocate(clock, gate_factory):
    """被拒绝的请求不建桶：攻击者无法用拒绝风暴撑大内存。"""
    gate = gate_factory(limit=1, window=60.0, max_keys=50)

    assert gate.allow("hot") is True
    for _ in range(2_000):
        assert gate.allow("hot") is False

    assert gate.stats()["tracked_keys"] == 1


def test_improved_sweep_frees_expired_keys(clock, gate_factory):
    gate = gate_factory(limit=5, window=1.0, max_keys=1_000)

    for i in range(500):
        gate.allow(f"user-{i}")
    assert len(gate) == 500

    clock.advance(3_600)
    assert gate.sweep() == 500
    assert len(gate) == 0


# =====================================================================
# 缺陷 3：key 不做类型校验，不同类型的 key 会串号
# =====================================================================


@DEFECT
def test_v1_silently_accepts_bad_keys(monkeypatch, clock):
    inject_v1_clock(monkeypatch, clock)
    gate = build(V1, limit=1, window=60.0)

    # None 当 key 不报错，静默坍缩成一个全局共享的桶；
    # 更隐蔽的是 True == 1、1 == 1.0，两个不同的「用户」共用额度。
    assert gate.allow(None) is True
    raise AssertionError("v1 静默接受非法 key，调用方拿不到任何提示")


def test_improved_rejects_bad_keys(clock, gate_factory):
    gate = gate_factory(limit=1, window=60.0)
    for bad in (None, 1, True, 1.0, b"ip"):
        with pytest.raises(TypeError):
            gate.allow(bad)


# =====================================================================
# 缺陷 4：读-改-写无锁，并发下超发
# =====================================================================


class _NetworkStore:
    """模拟 Redis：每次 get/set 都有一次网络往返，往返期间 GIL 会被释放。

    v1 的读和写是两次独立访问，中间隔着往返，所以在真实部署里必然出现竞态；
    纯进程内、无延迟的 dict 上反而压不出来 —— 这正是这类 bug 能活到线上的原因。
    """

    def __init__(self, latency=0.01):
        from gate_v1.limiter import MemoryStore

        self._inner = MemoryStore()
        self._latency = latency

    def get(self, slot):
        time.sleep(self._latency)
        return self._inner.get(slot)

    def set(self, slot, value):
        time.sleep(self._latency)
        self._inner.set(slot, value)

    def clear(self):
        self._inner.clear()

    def drop_key(self, key):
        self._inner.drop_key(key)

    def __len__(self):
        return len(self._inner)


@DEFECT
def test_v1_races_under_concurrency(monkeypatch, clock):
    """limit=1，8 个线程同时打同一个 key，v1 会放行多个。"""
    from gate_v1 import Gate

    inject_v1_clock(monkeypatch, clock)
    gate = Gate(1, 60.0, store=_NetworkStore())

    barrier = threading.Barrier(8)
    results = []
    lock = threading.Lock()

    def worker():
        barrier.wait()  # 让 8 个线程尽量同时进入临界区
        got = gate.allow("shared")
        with lock:
            results.append(got)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(results) == 1, f"limit=1，实际放行了 {sum(results)} 个"


def test_improved_is_thread_safe(clock, gate_factory):
    gate = gate_factory(limit=1, window=60.0)

    barrier = threading.Barrier(16)
    results = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        got = gate.allow("shared")
        with lock:
            results.append(got)

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(results) == 1


def test_improved_concurrent_throughput_is_accurate(clock, gate_factory):
    """20 个线程抢 100 个额度，必须精确放行 100 个。"""
    gate = gate_factory(limit=100, window=60.0, max_keys=10)

    barrier = threading.Barrier(20)
    counter = {"n": 0}
    lock = threading.Lock()

    def worker():
        barrier.wait()
        local = 0
        for _ in range(200):
            local += gate.allow("shared")
        with lock:
            counter["n"] += local

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert counter["n"] == 100


# =====================================================================
# 缺陷 5：墙钟回拨会让 v1 发放额外额度
# =====================================================================


@DEFECT
def test_v1_clock_rewind_reissues_quota(monkeypatch, clock):
    """系统时间往回拨一秒，固定窗口会认为「新的一格开始了」。"""
    inject_v1_clock(monkeypatch, clock)
    gate = build(V1, limit=1, window=10.0)

    clock.advance(20.0)
    assert gate.allow("k") is True
    assert gate.allow("k") is False

    clock.rewind(10.0)  # NTP 校准 / 容器迁移 / 手工改时间
    assert gate.allow("k") is False, "时间回拨后 v1 又发了一个额度"
