#!/usr/bin/env python3
"""把仓库渲染成一个只读浏览站点。

    python tools/site.py            # http://0.0.0.0:8000

页面：
  /                概览 + 文件树 + 测试状态
  /doc/README      README.md 渲染结果
  /doc/NOTES       NOTES.md 渲染结果
  /src?p=...       源码（带行号、语法高亮）
  /run?t=...       在线重跑 pytest / demo，输出实时流式返回

只用标准库 + markdown + pygments，不引入 Web 框架。
"""

from __future__ import annotations

import html
import mimetypes
import os
import subprocess
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "bin" / "python")

if not Path(PY).exists():  # 没建 venv 就退回当前解释器
    PY = sys.executable

SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}
TEXT_EXT = {".py", ".md", ".txt", ".ini", ".toml", ".cfg", ".json", ".yml", ".yaml"}
DOCS = {"README": "README.md", "NOTES": "NOTES.md"}

# 在线可跑的命令：白名单，不接受任意输入。
COMMANDS = {
    "pytest": [PY, "-m", "pytest"],
    "xfail": [PY, "-m", "pytest", "--runxfail", "-q"],
    "demo": [PY, "examples/demo.py"],
}


# --------------------------------------------------------------------------- 文件


def walk():
    """返回仓库里的文本文件相对路径列表（已忽略 venv / 缓存）。"""
    out = []
    for path in sorted(ROOT.rglob("*")):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.is_file() and path.suffix in TEXT_EXT:
            out.append(path.relative_to(ROOT).as_posix())
    return out


def safe_path(rel: str) -> Path | None:
    """把用户传的路径限制在仓库内，挡住 ../ 穿越。"""
    candidate = (ROOT / rel).resolve()
    try:
        candidate.relative_to(ROOT)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def line_count(rel: str) -> int:
    try:
        return len((ROOT / rel).read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeDecodeError):
        return 0


# ----------------------------------------------------------------------------- 高亮


def highlight(rel: str, text: str) -> str:
    from pygments import highlight as pyg_highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_for_filename

    try:
        lexer = get_lexer_for_filename(rel, text)
    except Exception:  # noqa: BLE001 - 未知后缀就当纯文本
        from pygments.lexers.special import TextLexer

        lexer = TextLexer()

    formatter = HtmlFormatter(
        linenos="table", nowrap=False, cssclass="hl", lineanchors="L"
    )
    return pyg_highlight(text, lexer, formatter)


# ------------------------------------------------------------------------------ 页面

CSS = """
:root{
  --bg:#0d1117; --panel:#161b22; --panel2:#1c2128; --line:#30363d;
  --fg:#e6edf3; --dim:#8b949e; --dim2:#6e7681;
  --accent:#58a6ff; --green:#3fb950; --red:#f85149; --amber:#d29922;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
}
*{box-sizing:border-box}
body{
  margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",
    "Hiragino Sans GB","Microsoft YaHei",sans-serif;
}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
code,kbd,pre{font-family:var(--mono)}
header{
  position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:18px;
  padding:12px 22px;background:rgba(13,17,23,.92);backdrop-filter:blur(8px);
  border-bottom:1px solid var(--line);flex-wrap:wrap;
}
.brand{font-weight:700;font-size:16px;letter-spacing:.3px}
.brand span{color:var(--dim);font-weight:400;margin-left:8px;font-size:13px}
nav{display:flex;gap:6px;flex-wrap:wrap}
nav a{
  padding:5px 11px;border:1px solid var(--line);border-radius:6px;
  color:var(--dim);font-size:13px;background:var(--panel);
}
nav a:hover{color:var(--fg);border-color:var(--dim2);text-decoration:none}
nav a.on{color:#fff;background:#1f6feb;border-color:#1f6feb}
main{max-width:1040px;margin:0 auto;padding:30px 22px 90px}
h1{font-size:26px;margin:.2em 0 .5em;letter-spacing:-.2px}
h2{font-size:19px;margin:1.8em 0 .6em;padding-bottom:.35em;border-bottom:1px solid var(--line)}
h3{font-size:16px;margin:1.4em 0 .4em}
p{color:#c9d1d9}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px 20px;margin:14px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.stat .n{font-size:24px;font-weight:700;font-family:var(--mono)}
.stat .l{color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.6px}
table{border-collapse:collapse;width:100%;font-size:14px;margin:12px 0}
th,td{border:1px solid var(--line);padding:8px 11px;text-align:left;vertical-align:top}
th{background:var(--panel2);color:var(--dim);font-weight:600;font-size:12.5px;
   text-transform:uppercase;letter-spacing:.4px}
tbody tr:nth-child(even){background:rgba(255,255,255,.018)}
code{background:var(--panel2);padding:1.5px 5px;border-radius:4px;font-size:13px;
     border:1px solid var(--line)}
pre{background:var(--panel);border:1px solid var(--line);border-radius:8px;
    padding:14px;overflow:auto;font-size:13px;line-height:1.55}
pre code{background:none;border:0;padding:0}
blockquote{margin:14px 0;padding:2px 16px;border-left:3px solid var(--dim2);color:var(--dim)}
ul,ol{padding-left:26px}
li{margin:.28em 0}
hr{border:0;border-top:1px solid var(--line);margin:26px 0}
.badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:12px;
       font-weight:600;font-family:var(--mono)}
.ok{background:rgba(63,185,80,.16);color:var(--green);border:1px solid rgba(63,185,80,.4)}
.bad{background:rgba(248,81,73,.16);color:var(--red);border:1px solid rgba(248,81,73,.4)}
.warn{background:rgba(210,153,34,.16);color:var(--amber);border:1px solid rgba(210,153,34,.4)}
.tree{font-family:var(--mono);font-size:13.5px;line-height:1.85}
.tree a{color:var(--fg)}
.tree .sz{color:var(--dim2);font-size:12px;margin-left:8px}
.tree .dir{color:var(--accent);font-weight:600}
.hl{background:var(--panel)!important;border:1px solid var(--line);border-radius:8px;
    overflow:auto;font-size:13px}
.hl pre{margin:0;background:none;border:0;padding:12px}
.hl table{border:0;margin:0;width:auto}
.hl td{border:0;padding:0}
.hl ., .codehilite .linenos{border-right:1px solid var(--line)!important;padding-right:12px!important;
             padding-left:12px!important}
.hl ., .codehilite .linenos pre{color:var(--dim2)}
.runbar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.runbar button{
  background:var(--panel);color:var(--fg);border:1px solid var(--line);
  border-radius:6px;padding:7px 14px;cursor:pointer;font-size:13px;font-family:inherit;
}
.runbar button:hover{border-color:var(--accent);color:var(--accent)}
.runbar button.on{background:#1f6feb;border-color:#1f6feb;color:#fff}
#out{background:#0a0d12;border:1px solid var(--line);border-radius:8px;padding:14px;
     font-family:var(--mono);font-size:12.5px;line-height:1.5;white-space:pre-wrap;
     min-height:180px;max-height:64vh;overflow:auto;color:#c9d1d9}
.g{color:var(--green)} .r{color:var(--red)} .d{color:var(--dim2)} .y{color:var(--amber)}
.muted{color:var(--dim);font-size:13.5px}
.path{font-family:var(--mono);font-size:13px;color:var(--dim);margin-bottom:10px}
footer{margin-top:50px;padding-top:18px;border-top:1px solid var(--line);
       color:var(--dim2);font-size:12.5px}
"""

# pygments 的配色（github-dark 风格）
PYGMENTS_CSS = """
/* 源码页（.hl）与 markdown 代码块（.codehilite）共用配色 */
.codehilite{background:var(--panel);border:1px solid var(--line);
  border-radius:8px;overflow:auto;margin:14px 0}
.codehilite pre{margin:0;background:none;border:0;padding:14px}
.hl .hll,.codehilite .hll{background-color:#6e7681}
.hl .c,.hl .ch,.hl .cm,.hl .cp,.hl .cpf,.hl .c1,.hl .cs,
.codehilite .c,.codehilite .ch,.codehilite .cm,.codehilite .cp,
.codehilite .cpf,.codehilite .c1,.codehilite .cs{color:#8b949e;font-style:italic}
.hl .k,.hl .kc,.hl .kd,.hl .kn,.hl .kp,.hl .kr,.hl .kt,
.codehilite .k,.codehilite .kc,.codehilite .kd,.codehilite .kn,
.codehilite .kp,.codehilite .kr,.codehilite .kt{color:#ff7b72}
.hl .o,.hl .ow,.codehilite .o,.codehilite .ow{color:#ff7b72}
.hl .s,.hl .sa,.hl .sb,.hl .sc,.hl .dl,.hl .sd,.hl .s2,.hl .se,
.hl .sh,.hl .si,.hl .sx,.hl .sr,.hl .s1,.hl .ss,
.codehilite .s,.codehilite .sa,.codehilite .sb,.codehilite .sc,
.codehilite .dl,.codehilite .sd,.codehilite .s2,.codehilite .se,
.codehilite .sh,.codehilite .si,.codehilite .sx,.codehilite .sr,
.codehilite .s1,.codehilite .ss{color:#a5d6ff}
.hl .m,.hl .mb,.hl .mf,.hl .mh,.hl .mi,.hl .mo,
.codehilite .m,.codehilite .mb,.codehilite .mf,.codehilite .mh,
.codehilite .mi,.codehilite .mo{color:#79c0ff}
.hl .na,.hl .nc,.hl .nf,.hl .nd,.codehilite .na,.codehilite .nc,
.codehilite .nf,.codehilite .nd{color:#d2a8ff}
.hl .nb,.hl .bp,.hl .nn,.hl .ne,.codehilite .nb,.codehilite .bp,
.codehilite .nn,.codehilite .ne{color:#ffa657}
.hl .nv,.hl .vc,.hl .vg,.hl .vi,.hl .vm,
.codehilite .nv,.codehilite .vc,.codehilite .vg,.codehilite .vi,
.codehilite .vm{color:#79c0ff}
.hl .n,.hl .nt,.codehilite .n,.codehilite .nt{color:#e6edf3}
.hl .p,.hl .pm,.codehilite .p,.codehilite .pm{color:#c9d1d9}
.hl .w,.codehilite .w{color:#6e7681}
"""


def page(title: str, body: str, active: str = "") -> bytes:
    def nav_item(href, label, key):
        cls = ' class="on"' if active == key else ""
        return f'<a href="{href}"{cls}>{label}</a>'

    nav = "".join(
        [
            nav_item("/", "概览", "home"),
            nav_item("/doc/README", "README", "readme"),
            nav_item("/doc/NOTES", "改造记录", "notes"),
            nav_item("/src?p=improved/gate/limiter.py", "改进版源码", "src"),
            nav_item("/src?p=src/gate_v1/limiter.py", "原始版源码", "src1"),
            nav_item("/tests", "跑测试", "run"),
        ]
    )
    doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · gate</title>
<style>{CSS}{PYGMENTS_CSS}</style>
</head><body>
<header>
  <div class="brand">gate <span>限流闸口 · 原始版 vs 改进版</span></div>
  <nav>{nav}</nav>
</header>
<main>{body}
<footer>
  只读浏览站点，由 <code>tools/site.py</code> 生成 ·
  <a href="/">刷新概览</a>
</footer>
</main></body></html>"""
    return doc.encode("utf-8")


def md(text: str) -> str:
    import markdown

    return markdown.markdown(
        text,
        extensions=["fenced_code", "tables", "codehilite", "toc", "sane_lists"],
        extension_configs={
            "codehilite": {"linenums": False, "noclasses": False, "pygments_lexer": "text"}
        },
    )


# ------------------------------------------------------------------------------ 首页


TESTS_BODY = r"""
<h1>在线重跑</h1>
<p class="muted">命令白名单，不接受任意输入。输出实时流式返回。</p>
<div class="runbar">
  <button data-t="pytest" class="on">pytest（应全绿）</button>
  <button data-t="xfail">pytest --runxfail（看 6 个缺陷真挂）</button>
  <button data-t="demo">examples/demo.py（实测对比）</button>
</div>
<div id="out" class="d">正在运行…</div>
<script>
(function(){
  var out = document.getElementById('out');
  var btns = Array.prototype.slice.call(document.querySelectorAll('.runbar button'));

  function esc(s){
    return s.replace(/[&<>]/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];
    });
  }
  function paint(line){
    if (/passed/.test(line)) return '<span class="g">' + esc(line) + '</span>';
    if (/failed|Error/.test(line)) return '<span class="r">' + esc(line) + '</span>';
    if (/xfail|XPASS|FAILED/.test(line)) return '<span class="y">' + esc(line) + '</span>';
    if (/^=+/.test(line)) return '<span class="d">' + esc(line) + '</span>';
    return esc(line);
  }

  async function run(t){
    btns.forEach(function(b){ b.classList.toggle('on', b.dataset.t === t); });
    out.textContent = '$ ' + t + '\n';
    var res = await fetch('/run?t=' + encodeURIComponent(t));
    var reader = res.body.getReader();
    var dec = new TextDecoder();
    var buf = '';
    for(;;){
      var step = await reader.read();
      if (step.done) break;
      buf += dec.decode(step.value, {stream:true});
      var lines = buf.split('\n');
      buf = lines.pop();
      for (var i = 0; i < lines.length; i++){
        out.innerHTML += paint(lines[i]) + '\n';
      }
      out.scrollTop = out.scrollHeight;
    }
    if (buf) out.innerHTML += paint(buf);
  }

  btns.forEach(function(b){ b.onclick = function(){ run(b.dataset.t); }; });
  run('pytest');
})();
</script>
"""


TEST_RESULT = {"ran": False, "ok": None, "summary": ""}


def run_test_badge() -> str:
    if not TEST_RESULT["ran"]:
        return '<span class="badge warn">测试未运行</span>'
    if TEST_RESULT["ok"]:
        return f'<span class="badge ok">✓ {html.escape(TEST_RESULT["summary"])}</span>'
    return f'<span class="badge bad">✗ {html.escape(TEST_RESULT["summary"])}</span>'


def git_info() -> dict:
    def g(*args):
        try:
            return subprocess.run(
                ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10
            ).stdout.strip()
        except Exception:  # noqa: BLE001
            return ""

    return {
        "branch": g("rev-parse", "--abbrev-ref", "HEAD"),
        "commit": g("log", "-1", "--format=%h %s"),
        "count": g("rev-list", "--count", "HEAD"),
    }


def home(body_only=False) -> bytes:
    files = walk()
    py_files = [f for f in files if f.endswith(".py")]
    total_lines = sum(line_count(f) for f in py_files)
    info = git_info()

    by_dir: dict[str, list[str]] = {}
    for f in files:
        head = f.split("/")[0] if "/" in f else ""
        by_dir.setdefault(head, []).append(f)

    rows = []
    for f in files:
        depth = f.count("/")
        name = f.split("/")[-1]
        pad = "&nbsp;" * 4 * depth
        icon = "▸" if f.endswith(".py") else "◦"
        rows.append(
            f'<div>{pad}<a href="/src?p={urllib.parse.quote(f)}">{icon} {html.escape(name)}</a>'
            f'<span class="sz">{line_count(f)} 行</span></div>'
        )

    body = f"""
<h1>仓库里有什么</h1>
<p class="muted">
  分支 <code>{html.escape(info["branch"])}</code> ·
  提交 <code>{html.escape(info["commit"])}</code> ·
  共 {info["count"]} 个 commit
</p>

<div class="grid" style="margin:18px 0">
  <div class="stat"><div class="n">{len(files)}</div><div class="l">文本文件</div></div>
  <div class="stat"><div class="n">{len(py_files)}</div><div class="l">Python 文件</div></div>
  <div class="stat"><div class="n">{total_lines:,}</div><div class="l">Python 代码行</div></div>
  <div class="stat"><div class="n">6</div><div class="l">已钉住的缺陷</div></div>
</div>

<div class="card">
  <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
    {run_test_badge()}
    <a href="/tests">→ 在线重跑测试</a>
    <a href="/doc/NOTES">→ 看改造记录</a>
  </div>
</div>

<h2>两个实现</h2>
<table>
  <thead><tr><th>包</th><th>算法</th><th>状态</th><th>入口</th></tr></thead>
  <tbody>
    <tr>
      <td><code>src/gate_v1</code></td>
      <td>固定窗口（按时间取整分桶）</td>
      <td><span class="badge bad">6 个缺陷</span></td>
      <td><a href="/src?p=src/gate_v1/limiter.py">查看源码</a></td>
    </tr>
    <tr>
      <td><code>improved/gate</code></td>
      <td>精确滑动窗口 + 单调时钟 + LRU 上界</td>
      <td><span class="badge ok">全部修复</span></td>
      <td><a href="/src?p=improved/gate/limiter.py">查看源码</a></td>
    </tr>
  </tbody>
</table>

<h2>缺陷清单</h2>
<table>
  <thead><tr><th>#</th><th>缺陷</th><th>原始版实测</th><th>改进版</th></tr></thead>
  <tbody>
    <tr><td>1</td><td>固定窗口边界突发</td><td><span class="badge bad">0.2 秒放行 10 个</span></td><td>精确滑动窗口</td></tr>
    <tr><td>2</td><td>内存无界</td><td><span class="badge bad">2 万 key → 2 万桶</span></td><td>LRU 淘汰 + sweep</td></tr>
    <tr><td>3</td><td>拒绝路径也建桶</td><td><span class="badge bad">拒绝仍占内存</span></td><td>拒绝不分配</td></tr>
    <tr><td>4</td><td>key 不校验类型</td><td><span class="badge bad">None/1/True 串号</span></td><td>强校验 + 报错</td></tr>
    <tr><td>5</td><td>check-then-act 无锁</td><td><span class="badge bad">限 1 放行 8</span></td><td>临界区加锁</td></tr>
    <tr><td>6</td><td>依赖墙钟</td><td><span class="badge bad">回拨后重发额度</span></td><td>单调时钟 + 冻结</td></tr>
  </tbody>
</table>

<h2>文件树</h2>
<div class="tree">{''.join(rows)}</div>
"""
    return page("概览", body, "home")


# ------------------------------------------------------------------------------ 路由


class Handler(BaseHTTPRequestHandler):
    server_version = "gate-site/1.0"

    def log_message(self, fmt, *args):  # 静音访问日志
        pass

    def _send(self, payload: bytes, ctype="text/html; charset=utf-8", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        # 不加 X-Frame-Options：预览是在 iframe 里打开的
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _err(self, code, msg):
        body = page(
            f"{code}",
            f'<h1>{code}</h1><p class="muted">{html.escape(msg)}</p>'
            f'<p><a href="/">← 回概览</a></p>',
        )
        self._send(body, code=code)

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path.rstrip("/") or "/"
        qs = urllib.parse.parse_qs(parsed.query)

        if route == "/":
            return self._send(home())

        if route.startswith("/doc/"):
            name = route.split("/doc/", 1)[1]
            rel = DOCS.get(name)
            if not rel:
                return self._err(404, f"没有这个文档：{name}")
            raw = (ROOT / rel).read_text(encoding="utf-8")
            body = (
                f'<div class="path">/{rel}</div>'
                f'<article class="doc">{md(raw)}</article>'
            )
            return self._send(page(name, body, name.lower()))

        if route == "/src":
            rel = (qs.get("p") or [""])[0]
            target = safe_path(rel)
            if target is None:
                return self._err(404, f"找不到文件：{rel}")
            try:
                text = target.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return self._err(400, "非文本文件")
            active = "src1" if rel.startswith("src/") else "src"
            body = (
                f'<div class="path">{html.escape(rel)} · {len(text.splitlines())} 行</div>'
                + highlight(rel, text)
            )
            return self._send(page(rel, body, active))

        if route == "/tests":
            return self._send(page("跑测试", TESTS_BODY, "run"))

        if route == "/run":
            t = (qs.get("t") or ["pytest"])[0]
            cmd = COMMANDS.get(t)
            if not cmd:
                return self._err(400, "只支持 pytest / xfail / demo")
            return self._stream(cmd)

        if route == "/healthz":
            return self._send(b"ok", "text/plain")

        return self._err(404, "页面不存在")

    def _stream(self, cmd):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        env = {**os.environ, "PYTHONUNBUFFERED": "1", "TERM": "dumb"}
        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            bufsize=0,
        )
        tail = []
        assert proc.stdout is not None
        try:
            while True:
                chunk = proc.stdout.read(1)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
                tail.append(chunk)
                if len(tail) > 4000:
                    del tail[:2000]
        except (BrokenPipeError, ConnectionResetError):
            proc.kill()
            return
        proc.wait()

        text = b"".join(tail).decode("utf-8", "replace")
        if cmd[-1] == "pytest" or "pytest" in cmd:
            ok = proc.returncode == 0
            summary = next(
                (ln.strip() for ln in reversed(text.splitlines()) if "passed" in ln or "failed" in ln),
                "",
            )
            TEST_RESULT.update(ran=True, ok=ok, summary=summary)
        self.wfile.write(b"\n")


def warmup():
    """启动时先跑一次 pytest，让概览页的徽章反映真实状态。"""
    try:
        proc = subprocess.run(
            [PY, "-m", "pytest"],  # 不要再加 -q：pytest.ini 里已有 addopts=-q
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        summary = next(
            (ln.strip() for ln in reversed(proc.stdout.splitlines()) if "passed" in ln or "failed" in ln),
            "",
        )
        TEST_RESULT.update(ran=True, ok=proc.returncode == 0, summary=summary)
        print(f"warmup: {summary}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"warmup failed: {exc}", flush=True)


def main():
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    srv = ThreadingHTTPServer((host, port), Handler)
    warmup()
    print(f"serving http://{host}:{port}  (root={ROOT})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
