# 改造记录

`src/gate_v1` → `improved/gate`。原始版**保持原样不动**，改进版独立成包，
两个包名不同（`gate_v1` / `gate`），可以同时导入、同时测试，随时逐条对照。

```bash
pytest              # 44 passed, 6 xfailed —— 缺陷被测试钉住，不会悄悄回归
pytest --runxfail   # 6 个缺陷全部真实报错，证明这些测试不是摆设
python examples/demo.py
```

---

## 1. 固定窗口 → 滑动窗口

**原始写法**：把时间按 `window` 切成格子，`int(now // window)` 当格子号。

```python
slot = (key, int(time.time() // self.window))
count = store.get(slot, 0)
if count >= limit: return False
store.set(slot, count + 1)
```

**为什么错**：格子的边界是硬切。在 `0.9s` 打满 5 个额度，`1.1s` 进入下一格、
计数清零，又能打 5 个 —— 0.2 秒内实际放行了 10 个，是 `limit` 的两倍。
用在登录爆破防护、短信验证码这类场景上，等于把限流开了个后门。

**改法**：给每个 key 存一个**放行时间戳队列**，每次判定前把滑出窗口的时间戳弹掉。

```python
bucket.evict_before(now - self._window)
if len(bucket.hits) < self._limit:
    bucket.hits.append(now)
```

**取舍**：滑动窗口每个 key 最多存 `limit` 个 float，固定窗口只存 1 个 int。
`limit` 很大（比如按 IP 限 10000/秒）时内存吃不消，那时应该换令牌桶
（只存 `tokens` + `last_refill` 两个数，同样是平滑的）。
本仓库选滑动窗口，是因为它精确、和参考模型能逐位对齐，便于测试。

> 另一种常见做法是「滑动窗口计数」（只存当前格 + 上一格按比例加权）。
> 它把内存降到 O(1)，但只能近似，边界上仍会超发约 0.1%，我没选它。

## 2. 内存有上界

**原始写法**：`self._buckets` 只增不减。键是 `(key, 格子号)`，每换一格就多一条，
**永不回收**。公网服务里攻击者每个请求换一个 UA / 伪造 X-Forwarded-For，
几万个请求就是几万个桶 —— 这是一个不需要并发、不需要权限的远程内存耗尽。

```python
for i in range(20_000):
    gate.allow(f"forged-{i}")
# gate_v1   : 20000 个桶
# improved  : 1000 个桶（max_keys=1000）
```

**改法**，三层防线：

1. **拒绝不分配**：只有确定要放行时才建桶，拒绝风暴不会撑大内存。
2. **LRU 淘汰**：用 `OrderedDict`，新 key 进尾部，命中 `move_to_end`。
   超限时先从头部回收「真正过期」的空桶，不够再淘汰最久未使用的。
3. **主动 `sweep()`**：可以不依赖淘汰，周期性把过期 key 清掉，配合监控 `stats()`。

**取舍**：LRU 淘汰意味着「被挤掉的 key 会重新拿到满额度的配额」。
对一个**限流器**来说，这比 OOM 好得多 —— 最坏情况是少量请求漏过，
而不是整个进程挂掉。真需要严格性，就把状态放到 Redis（见第 7 条）。

## 3. key 类型强校验

**原始写法**：`key` 直接当字典键。`None` 不报错，静默变成一个全局共享的桶；
更隐蔽的是 Python 里 `True == 1 == 1.0`，两个「不同的用户」会共用额度。

**改法**：入口处 `isinstance(key, str)`，否则 `TypeError`，错误信息里写清该怎么改。
`limit` / `window` / `max_keys` 同样处理：`limit=1.5`、`window=inf`、`window=nan`
都在**构造时**就炸，而不是第一次请求时才炸。`bool` 单独排除，
因为 `True` 是 `int` 的子类，`limit=True` 会被当成 1 悄悄放过。

## 4. 并发正确性

**原始写法**：`get` → 判断 → `set`，三次独立操作。进程内的 dict 因为有 GIL
反而压不出来；真实部署里存储是 Redis / 一张计数表，中间夹着网络往返，
两个请求同时读到 `count=0`，都判断没超限，都写回 1 —— 8 个线程抢 1 个额度，
**实测放行 8 个**。这正是这类 bug 能活到线上的原因：本地测试永远复现不了。

测试里用一个 `_NetworkStore`（每次 get/set `sleep(10ms)`）来模拟，
因为 `sleep` 会释放 GIL，竞态就变成必现。

**改法**：读-改-写整体进 `threading.Lock()`。临界区里只做内存运算，没有 I/O，
持锁时间在微秒级。20 线程抢 100 个额度，精确放行 100 个。

## 5. 单调时钟 + 回拨防护

**原始写法**：`time.time()`（墙钟）。NTP 校准、容器迁移、手工改时间都会让它
往回跳。时间一退，固定窗口认为「新的一格开始了」，于是**重新发一遍额度**。

**改法**：

1. 默认用 `time.monotonic`，它只增不减。
2. 仍然防一手：时钟读数若小于历史最高点，内部时钟**冻结**在最高点。
   这样既不凭空多发额度，也不会像「直接拒绝所有请求」那样在回拨窗口期
   把所有人都误封。
3. 时钟可注入（`clock=`），测试用 `ManualClock` 精确控制，没有一个测试靠 `sleep` 抢时间。

> 冻结的代价：回拨的那段时间被「白等」了，额度释放会晚一点。
> 对限流器来说这偏向安全侧（宁可晚放，不可多放）。

## 6. 可观测性

原始版只有 `True/False`，调用方拿不到任何信息，也就写不出正确的响应头。
改后对外给 `Decision`：

| 字段 | 用途 |
|------|------|
| `allowed` | 放行与否 |
| `remaining` | `X-RateLimit-Remaining` |
| `retry_after` / `retry_after_ms` | `Retry-After`，拒绝时告诉客户端等多久 |
| `reset_at` | `X-RateLimit-Reset` |

`Decision.__bool__` 返回 `allowed`，所以 `if gate.allow(...)` 和
`if gate.check(...)` 都能自然书写，老的布尔接口 `allow()` 原样保留。
`stats()` 给监控用，`len(gate)` 给测试/告警用。

## 7. 明确**没有**解决

这些是 knowingly 留下的，别当成已支持：

- **状态在进程内**。多实例部署必须换 Redis：滑动窗口用 `ZADD` + `ZREMRANGEBYSCORE`
  + `ZCARD`，包在 Lua 脚本里保证原子；或直接用 Redis 的令牌桶实现。
- **单维度限流**。真实网关要按 IP / 用户 / 路由 / 全局限流分层组合，
  本仓库只做了 `Gate` 这一层，组合逻辑留给调用方。
- **没有 HTTP 适配层**。核心已在，接 ASGI 中间件是下一步（要注意 `Decision`
  才能写出正确的 `Retry-After`）。
- **没有性能基准**。`examples/demo.py` 里有个粗略数字：10 万次 `allow`，
  v1 约 38ms，改进版约 112ms（2.9x）。这是精确性的价格，
  高吞吐场景应该回到令牌桶，或把状态外移到 Redis。
