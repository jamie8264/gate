# gate

按 key 的**限流闸口**（rate limiter）最小工程，带一份「原始版 vs 改进版」的对照。

这个仓库原本是空的，`src/` 里的 v1 是我按业界最常见的固定窗口写法造的样本，
用来承载 `tests/` 里的缺陷复现；`improved/` 是修好之后的版本，**独立成包，不覆盖原文件**。

```
src/gate_v1/      原始版（固定窗口，有 6 个已知缺陷）—— 只作对照，勿用于生产
improved/gate/    改进版（滑动窗口 + 单调时钟 + 有界内存 + 线程安全）
tests/            两个实现的测试；v1 的缺陷用 xfail(strict) 钉住
examples/demo.py  三种实现方式的实测数字对比
tools/serve.py    把仓库渲染成只读浏览站点（可在线重跑测试）
NOTES.md          缺陷清单、改法、为什么这么改
```

## 在线浏览

```bash
.venv/bin/python tools/serve.py     # → http://0.0.0.0:8000
```

浏览器里能看：

| 地址 | 内容 |
|------|------|
| `/` | 概览：文件树、代码行数、缺陷清单、当前测试状态 |
| `/doc/README` `/doc/NOTES` | 渲染后的文档 |
| `/src?p=...` | 任意源文件，带行号与语法高亮 |
| `/tests` | 在线重跑 `pytest` / `--runxfail` / `demo.py`，输出实时流式返回 |

只读站点，命令走白名单，路径过 `resolve()` + `relative_to()` 防穿越。

## 运行

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

.venv/bin/python -m pytest                  # 全绿：44 passed, 6 xfailed
.venv/bin/python -m pytest --runxfail       # 直接看 v1 的 6 个缺陷怎么挂的
.venv/bin/python examples/demo.py           # 实测数字对比
```

`--runxfail` 会把 xfail 当成普通用例跑，于是 6 个缺陷真实报错 ——
这是证明「这些测试不是摆设」的最快方式。

## 缺陷一览

| # | 缺陷 | v1 的表现 | 改进版的做法 |
|---|------|-----------|--------------|
| 1 | 固定窗口边界突发 | `limit=5/秒`，0.2 秒内放行 10 个 | 精确滑动窗口（时间戳队列） |
| 2 | 内存无界 | 2 万个伪造 key → 2 万个桶，永不释放 | LRU 上界 + 主动 sweep |
| 3 | 拒绝路径也分配 | 被拒请求同样占内存 | 拒绝不建桶 |
| 4 | key 不校验类型 | `None`/`1`/`True` 静默串号 | 强校验，构造/调用即报错 |
| 5 | check-then-act 无锁 | 8 线程抢 1 个额度，放行 8 个 | 临界区加锁，精确不超发 |
| 6 | 依赖墙钟 | 时间回拨后重新发额度 | 单调时钟 + 回拨冻结 |

细节和取舍见 [NOTES.md](NOTES.md)。

## 用法

```python
from gate import Gate

gate = Gate(limit=100, window=60.0, max_keys=50_000)

if gate.allow(user_id):            # 布尔接口，和 v1 兼容
    handle()

d = gate.check(user_id)            # 需要上报头时用 Decision
if not d:
    headers["Retry-After"] =         str(d.retry_after_ms // 1000)
    headers["X-RateLimit-Remaining"] = str(d.remaining)
    headers["X-RateLimit-Reset"] =   str(int(d.reset_at))
```

## 目前**没有**解决的事

 knowingly 留在这里，别当成已支持：

- **只有进程内状态**。多进程 / 多实例部署必须换成 Redis 等共享后端，
  滑动窗口用 `ZADD`+`ZREMRANGEBYSCORE` 或 Lua 脚本保证原子性。
- **限流维度只有 key**。真实网关还需要按 IP / 用户 / 路由 / 全局并发做分层限流。
- **没有对外的 HTTP 中间件**。只有限流核心，接 ASGI 适配层是下一步。
- **没有性能基准**。滑动窗口比固定窗口多 O(limit) 的时间戳存储，高 limit 下要换令牌桶。
