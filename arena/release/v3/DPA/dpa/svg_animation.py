"""Generate a self-contained animated SVG (no external JS/CSS/assets)."""
from __future__ import annotations

import csv
import json
from pathlib import Path


def _read_truth(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [
            {k: (float(v) if k not in ("hook_id", "in_sensor_fov", "in_robot_zone") else int(v))
             for k, v in row.items()}
            for row in csv.DictReader(fh)
        ]


def build_animation(out_dir: Path, cfg: dict) -> dict:
    """Create svg/animation.svg and svg/preview.svg from tip_truth.csv."""
    rows = _read_truth(out_dir / "truth" / "tip_truth.csv")
    if not rows:
        raise RuntimeError("no truth rows for SVG")
    n_hooks = int(cfg["svg"]["n_hooks"])
    fps = int(cfg["svg"]["fps"])
    window = float(cfg["svg"]["window_s"])
    by_hook: dict[int, list[dict]] = {}
    for r in rows:
        by_hook.setdefault(r["hook_id"], []).append(r)
    chosen = sorted(by_hook, key=lambda h: by_hook[h][0]["t_s"])[:n_hooks]
    # Pick a window in which as many chosen hooks as possible are visible.
    candidates = [r["t_s"] for h in chosen for r in by_hook[h] if r["in_sensor_fov"]]
    if not candidates:
        candidates = [rows[0]["t_s"]]
    t0 = min(candidates) + max(0.0, (min(candidates) + window * 0.5) - min(candidates)) * 0.0
    best = None
    for start in candidates[:: max(1, len(candidates) // 80)]:
        score = sum(1 for h in chosen if any(start <= r["t_s"] <= start + window and r["in_sensor_fov"] for r in by_hook[h]))
        if best is None or score > best[0]:
            best = (score, start)
    if best and best[0] > 0:
        t0 = best[1]

    series = []
    for h in chosen:
        data = []
        last_i = -1
        for step in range(int(window * fps) + 1):
            t = t0 + step / fps
            target_i = int(round((t - rows[0]["t_s"]) / float(cfg["dt_s"])))
            target_i = max(0, min(target_i, len(rows) - 1))
            # Each hook has its own contiguous time block; binary-search by time.
            seq = by_hook[h]
            lo, hi = 0, len(seq) - 1
            while lo < hi:
                mid = (lo + hi) // 2
                if seq[mid]["t_s"] < t:
                    lo = mid + 1
                else:
                    hi = mid
            i = lo
            if i > 0 and abs(seq[i - 1]["t_s"] - t) < abs(seq[i]["t_s"] - t):
                i -= 1
            if i == last_i:
                continue
            last_i = i
            r = seq[i]
            data.append([round(r["t_s"] - t0, 3), round(r["x_mm"], 3), round(r["y_mm"], 3),
                         round(r["z_mm"], 3), round(r["rx_deg"], 3), round(r["ry_deg"], 3),
                         round(r["rz_deg"], 3)])
        series.append({"hook_id": h, "frames": data})

    payload = json.dumps({
        "fps": fps, "window": window, "series": series,
        "geometry": {
            "L": cfg["hook"]["length_mm"], "r": cfg["hook"]["arc_radius_mm"],
            "R": cfg["hook"]["tip_radius_mm"], "amplify": cfg["svg"]["angle_amplify"],
            "trail": int(cfg["svg"]["trail_points"]),
        },
        "fov": cfg["sensor"]["fov_x_mm"],
    }, separators=(",", ":"))

    svg_dir = out_dir / "svg"
    svg_dir.mkdir(parents=True, exist_ok=True)
    (svg_dir / "animation_data.json").write_text(payload, encoding="utf-8")
    (svg_dir / "animation.svg").write_text(_svg_document(payload), encoding="utf-8")
    (svg_dir / "preview.svg").write_text(_static_preview(series, cfg), encoding="utf-8")
    return {"n_series": len(series), "frames": sum(len(s["frames"]) for s in series),
            "t0": t0, "window_s": window}


def _svg_document(payload: str) -> str:
    return r'''<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="680" viewBox="0 0 1100 680">
<defs>
  <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#8aa"/></marker>
  <style><![CDATA[
    .bg{fill:#0d1117}.panel{fill:#111827;stroke:#334155;stroke-width:1.5}.grid{stroke:#243244;stroke-width:1}
    .lab{fill:#93a4b8;font:12px monospace}.title{fill:#e6edf3;font:bold 15px sans-serif}
    .val{fill:#7ee787;font:bold 15px monospace}.btn{fill:#1f2937;stroke:#475569;rx:5;cursor:pointer}.btntext{fill:#e6edf3;font:13px sans-serif;text-anchor:middle}
  ]]></style>
</defs>
<rect class="bg" width="1100" height="680"/>
<text class="title" x="24" y="28">电泳链挂钩尖端扰动 · 实时六维坐标（DPA / schema_v1）</text>
<text class="lab" id="clock" x="880" y="28">t = 0.00 s</text>

<rect class="panel" x="20" y="42" width="620" height="300" rx="8"/>
<text class="lab" x="36" y="62">俯视 XY（X 链条方向 →，Y 指向机械臂 ↑）</text>
<g id="gridTop"></g>
<line x1="40" y1="286" x2="620" y2="286" stroke="#475569" stroke-width="2" marker-end="url(#arrow)"/>
<line x1="330" y1="312" x2="330" y2="90" stroke="#475569" stroke-width="2" marker-end="url(#arrow)"/>
<text class="lab" x="600" y="302">x</text><text class="lab" x="338" y="98">y</text>
<g id="topHooks"></g><g id="topTrail"></g>

<rect class="panel" x="20" y="352" width="620" height="286" rx="8"/>
<text class="lab" x="36" y="372">侧视 YZ（真实钩形：直杆 + 半圆 + 半球尖端，角度已放大）</text>
<g id="gridSide"></g>
<line x1="55" y1="590" x2="620" y2="590" stroke="#475569" stroke-width="2" marker-end="url(#arrow)"/>
<line x1="55" y1="590" x2="55" y2="385" stroke="#475569" stroke-width="2" marker-end="url(#arrow)"/>
<text class="lab" x="600" y="605">y</text><text class="lab" x="63" y="395">z</text>
<g id="sideHooks"></g><g id="sideTrail"></g>

<rect class="panel" x="652" y="42" width="428" height="282" rx="8"/>
<text class="lab" x="670" y="66">尖端六维坐标（真值，单位 mm / deg）</text>
<g id="readout"></g>

<rect class="panel" x="652" y="334" width="428" height="150" rx="8"/>
<text class="lab" x="670" y="356">链速 v(t) 与速度事件</text>
<polyline id="speedLine" fill="none" stroke="#58a6ff" stroke-width="2"/>
<rect id="eventBand" fill="#f85149" opacity="0.18" x="670" y="365" width="0" height="105"/>
<text class="lab" id="speedVal" x="900" y="356">v = 50.0 mm/s</text>

<rect class="panel" x="652" y="494" width="428" height="144" rx="8"/>
<text class="lab" x="670" y="518">控制：播放 / 暂停 / 倍速 / 拖动时间</text>
<g id="controls">
  <rect class="btn" id="playBtn" x="670" y="532" width="90" height="34"/>
  <text class="btntext" id="playTxt" x="715" y="554">暂停</text>
  <rect class="btn" id="slowBtn" x="772" y="532" width="60" height="34"/><text class="btntext" x="802" y="554">0.5×</text>
  <rect class="btn" id="fastBtn" x="842" y="532" width="60" height="34"/><text class="btntext" x="872" y="554">2×</text>
  <rect class="btn" id="resetBtn" x="912" y="532" width="60" height="34"/><text class="btntext" x="942" y="554">重置</text>
  <rect id="seekTrack" x="670" y="585" width="392" height="14" fill="#334155" rx="4" style="cursor:pointer"/>
  <rect id="seekFill" x="670" y="585" width="0" height="14" fill="#58a6ff" rx="4"/>
  <circle id="seekThumb" cx="670" cy="592" r="7" fill="#e6edf3" style="cursor:pointer"/>
</g>
<script type="text/javascript"><![CDATA[
(function(){
  const D = __PAYLOAD__;
  const colors = ['#58a6ff','#f778ba','#7ee787','#ffd166','#ff7b72'];
  const $ = id => document.getElementById(id);
  const svgNS = 'http://www.w3.org/2000/svg';
  const X0=40, X1=620, Y0=290, Y1=85;
  const f0=D.fov[0], f1=D.fov[1];
  const sx = x => X0 + (x-f0)/(f1-f0)*(X1-X0);
  const sy = y => Y0 - (y-0)/150*(Y0-Y1);
  const sz = z => 590 - z/90*190;
  function el(tag, attrs, parent){const e=document.createElementNS(svgNS,tag);for(const k in attrs)e.setAttribute(k,attrs[k]);parent.appendChild(e);return e;}
  for(let x=-700;x<=100;x+=100){el('line',{x1:sx(x),y1:80,x2:sx(x),y2:292,class:'grid'},$('gridTop'));
    const t=el('text',{x:sx(x)-12,y:305,class:'lab'},$('gridTop'));t.textContent=x;}
  for(let y=0;y<=150;y+=30){el('line',{x1:40,y1:sy(y),x2:620,y2:sy(y),class:'grid'},$('gridTop'));}
  for(let z=0;z<=90;z+=15){el('line',{x1:55,y1:sz(z),x2:620,y2:sz(z),class:'grid'},$('gridSide'));}
  const labels=['x_mm','y_mm','z_mm','rx_deg','ry_deg','rz_deg'];
  const vals={};
  for(let i=0;i<6;i++){
    const y=88+i*36;
    const lab=el('text',{x:670,y:y,class:'lab'},$('readout'));
    lab.textContent=labels[i].replace('_',' ')+' = ';
    vals[labels[i]]=el('text',{x:810,y:y,class:'val'},$('readout'));
  }
  const hid=el('text',{x:670,y:313,class:'val'},$('readout'));
  const speedCurve=[];
  for(let k=0;k<=200;k++){
    const v=50+9*Math.sin(k/19)+6*Math.sin(k/53);
    speedCurve.push([k,Math.max(20,Math.min(80,v))]);
  }
  $('speedLine').setAttribute('points',speedCurve.map(p=>(670+p[0]*1.94)+','+(465-(p[1]-20)/60*95)).join(' '));
  let playing=true, rate=1, cursor=0, last=performance.now();
  const total=D.window;
  function frameAt(h,t){
    const a=h.frames;
    if(!a.length)return null;
    let lo=0,hi=a.length-1;
    if(t<=a[0][0])return a[0];
    if(t>=a[hi][0])return a[hi];
    while(hi-lo>1){const m=(lo+hi)>>1;if(a[m][0]<=t)lo=m;else hi=m;}
    return a[lo];
  }
  function draw(){
    const t=cursor;
    $('clock').textContent='t = '+t.toFixed(2)+' s';
    const seen=[];
    D.series.forEach((h,idx)=>{
      const f=frameAt(h,t); if(!f)return;
      const col=colors[idx%colors.length];
      seen.push(f);
      const px=sx(f[1]), py=sy(f[2]);
      el('circle',{cx:px,cy:py,r:5,fill:col,id:'dot'+idx},$('topHooks'));
      const L=D.geometry.L, r=D.geometry.r, R=D.geometry.R;
      const ps=[[0,0],[0,L],[r,L],[r,L+2*r],[0,L+2*r],[0,L+2*r-R]];
      const ang=f[6]*Math.PI/180*D.geometry.amplify;
      const rot=(p)=>[f[1]+p[0]*Math.cos(ang)-p[1]*Math.sin(ang), f[2]+p[0]*Math.sin(ang)+p[1]*Math.cos(ang)];
      const pts=ps.map(rot).map(p=>(sx(p[0])+','+sy(p[1]))).join(' ');
      el('polyline',{points:pts,fill:'none',stroke:col,'stroke-width':2,id:'hook'+idx},$('topHooks'));
      const syz=[[0,0],[0,L],[r,L],[r,L+2*r],[0,L+2*r],[0,L+2*r-R]];
      const pitch=f[4]*Math.PI/180*D.geometry.amplify;
      const rotz=(p)=>[f[2]+p[0]*Math.cos(pitch)-p[1]*Math.sin(pitch), f[3]+p[0]*Math.sin(pitch)+p[1]*Math.cos(pitch)];
      el('polyline',{points:rotz(syz).map(p=>(55+p[0]/150*565)+','+sz(p[1])).join(' '),fill:'none',stroke:col,'stroke-width':2,id:'side'+idx},$('sideHooks'));
    });
    const tail=[];
    D.series.forEach((h,idx)=>{
      const col=colors[idx%colors.length];
      const pts=[];
      for(let k=Math.max(0,Math.floor((t-2)*D.fps));k<=Math.floor(t*D.fps);k+=2){
        const f=frameAt(h,k/D.fps); if(f)pts.push(sx(f[1])+','+sy(f[2]));
      }
      if(pts.length>1)el('polyline',{points:pts.join(' '),fill:'none',stroke:col,'stroke-opacity':0.45,id:'trail'+idx},$('topTrail'));
      tail.push(pts[pts.length-1]||'');
    });
    const f=seen[0]||[0,0,0,0,0,0,0];
    for(let i=0;i<6;i++) vals[labels[i]].textContent=f[i+1].toFixed(3);
    hid.textContent='hook_id = H'+String(f[0]>=0?Math.round(f[0]):0).padStart(4,'0')+'  ·  可见 '+seen.length+' 个';
    const v=50+9*Math.sin(t*10.5)+6*Math.sin(t*3.8);
    $('speedVal').textContent='v = '+v.toFixed(2)+' mm/s';
    $('speedLine').setAttribute('transform','translate(0,0)');
    const frac=Math.max(0,Math.min(1,t/total));
    $('seekFill').setAttribute('width',(392*frac).toFixed(1));
    $('seekThumb').setAttribute('cx',(670+392*frac).toFixed(1));
  }
  function clearDynamic(){
    ['topHooks','topTrail','sideHooks','sideTrail'].forEach(id=>{while($(id).firstChild)$(id).removeChild($(id).firstChild);});
  }
  function loop(now){
    const dtms=Math.min(100,now-last); last=now;
    if(playing){cursor+=dtms/1000*rate;if(cursor>total)cursor=0;}
    clearDynamic();draw();requestAnimationFrame(loop);
  }
  $('playBtn').addEventListener('click',()=>{playing=!playing;$('playTxt').textContent=playing?'暂停':'播放';});
  $('slowBtn').addEventListener('click',()=>{rate=0.5;});
  $('fastBtn').addEventListener('click',()=>{rate=2;});
  $('resetBtn').addEventListener('click',()=>{cursor=0;});
  function seekTo(e){
    const box=document.documentElement.getBoundingClientRect();
    const x=(e.clientX-box.left)*1100/box.width;
    cursor=Math.max(0,Math.min(1,(x-670)/392))*total;
  }
  $('seekTrack').addEventListener('pointerdown',e=>{seekTo(e);});
  $('seekTrack').addEventListener('pointermove',e=>{if(e.buttons)seekTo(e);});
  $('seekThumb').addEventListener('pointerdown',e=>{seekTo(e);});
  requestAnimationFrame(loop);
})();
]]></script>
</svg>
'''.replace("__PAYLOAD__", payload)


def _static_preview(series: list[dict], cfg: dict) -> str:
    """Simple deterministic first-frame SVG preview (no JavaScript)."""
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="800" height="420" viewBox="0 0 800 420">',
             '<rect width="800" height="420" fill="#0d1117"/>',
             '<text x="20" y="30" fill="#e6edf3" font-family="sans-serif" font-size="16">DPA 静态预览 · 俯视 XY / 侧视 YZ</text>',
             '<rect x="20" y="45" width="450" height="340" fill="#111827" stroke="#334155"/>',
             '<rect x="485" y="45" width="295" height="340" fill="#111827" stroke="#334155"/>']
    colors = ["#58a6ff", "#f778ba", "#7ee787", "#ffd166"]
    for idx, s in enumerate(series):
        if not s["frames"]:
            continue
        f = s["frames"][len(s["frames"]) // 2]
        x = 30 + (f[1] + 700) / 800 * 430
        y = 360 - f[2] / 150 * 300
        zy = 500 - 0  # placeholder for readability
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{colors[idx % 4]}"/>')
        parts.append(f'<polyline points="{x:.1f},{y:.1f} {x+40:.1f},{y-50:.1f} {x+75:.1f},{y-48:.1f}" fill="none" stroke="{colors[idx % 4]}" stroke-width="2"/>')
        parts.append(f'<text x="500" y="{90 + idx * 50}" fill="{colors[idx % 4]}" font-family="monospace">hook {s["hook_id"]}: x={f[1]:.2f} y={f[2]:.2f} z={f[3]:.2f} rz={f[6]:.2f}</text>')
    parts.append("</svg>")
    return "\n".join(parts)
