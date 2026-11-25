"""固定窗口（fixed window）限流器 —— 一份「看起来很正常」的典型实现。

思路：
  1. 把时间按 window 切成格子，格子编号 = int(now // window)；
  2. 以 (key, 格子号) 为键，去存储里查「这一格已经用了多少次」；
  3. 没超限就写回 count + 1。

逻辑短、好懂、面试常写，接 Redis/SQL 也方便，所以被大量复制到线上。
它的问题都在 tests/test_defects.py 里逐条钉死了，对照 improved/gate 看。
"""

import time


class MemoryStore:
    """最朴素的进程内存储。真实项目里这里通常是 Redis 或一张计数表。"""

    def __init__(self):
        self._data = {}

    def get(self, slot):
        return self._data.get(slot)

    def set(self, slot, value):
        self._data[slot] = value

    def clear(self):
        self._data.clear()

    def drop_key(self, key):
        for slot in [s for s in self._data if s[0] == key]:
            del self._data[slot]

    def __len__(self):
        return len(self._data)


class Gate:
    """按 key 计数的固定窗口限流闸口。"""

    def __init__(self, limit, window=1.0, store=None):
        self.limit = limit
        self.window = window
        self.store = store if store is not None else MemoryStore()

    def allow(self, key):
        """放行返回 True，拒绝返回 False。

        注意这里的 check-then-act 是两次独立的存储访问，
        中间夹着一次网络往返 —— 并发下并不同步，见缺陷 4。
        """
        slot = (key, int(time.time() // self.window))

        entry = self.store.get(slot)          # 第一次访问
        count = entry[1] if entry else 0
        if count >= self.limit:
            return False

        self.store.set(slot, (time.time(), count + 1))  # 第二次访问
        return True

    def reset(self, key=None):
        """清空某个 key 的计数；key 为 None 时清空全部。"""
        if key is None:
            self.store.clear()
        else:
            self.store.drop_key(key)
