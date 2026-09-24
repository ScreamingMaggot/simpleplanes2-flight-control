# SC-3b 交互式 3D 航迹（可旋转/缩放，每局独立局部坐标系）
# 用法: python make_track_html.py <sortieA.log> <sortieB.log> <out.html>
import io, re, sys, json
import numpy as np

RWYS = {
    'Cochran 04L': (-29883, 12873, 45, 3),  'Cochran 22L': (-27887, 15064, 225, 3),
    'Cochran 18':  (-26945, 14477, 180, 3), 'Shepard 34':  (-2330,  4381,  345, 11),
    'Shepard 22':  (-2556,  4340,  225, 11),'Bannock 05':  (-38878, 6533, 50,  5),
    'Bannock 23':  (-37451, 8234, 230, 5),  'Bannock 08':  (-38872, 6204, 80,  5),
    'Bannock 26':  (-38681, 7288, 260, 5),  'Kunimitsu 1': (-5540,  12797, 10,  10),
    'Kunimitsu 19':(-4500,  12980, 190, 10),'Kunimitsu 4': (-6180,  12122, 40,  10),
    'Kunimitsu 22':(-5160,  12978, 220, 10),
}
PHASES = {
    'ground':   ('#9aa0a6', '地面滑跑/起飞'),
    'approach': ('#1f6fb4', '进近段（截获+等高）'),
    'orbit':    ('#39b9c9', '切线圆消高'),
    'glide':    ('#e07b39', '下滑+拉平'),
    'goaround': ('#c0304a', '复飞爬升'),
    'rollout':  ('#7a1f2b', '滑跑减速'),
}

def parse(fn):
    pos, ev = [], []
    tel_t = None
    with io.open(fn, encoding='utf-8', errors='ignore') as f:
        for ln in f:
            ln = ln.strip()
            if ln.startswith('POS,'):
                p = ln.split(',')
                try: pos.append((float(p[2]), float(p[3]), float(p[4]), float(p[5])))
                except (ValueError, IndexError): pass
            elif ln.startswith('TEL,'):
                p = ln.split(',')
                try: tel_t = float(p[2])
                except (ValueError, IndexError): pass
            else:
                t = tel_t if tel_t is not None else (pos[-1][0] if pos else 0)
                for k, name in [('RWY SEL ','rwy_sel'),('APP CAP ','cap'),('GLIDE ABORT','abort'),
                                ('GA REJOIN','rejoin'),('PATTERN COMPLETE','complete'),
                                ('ORBIT ENTER','orbit'),('ORBIT RELEASE','release'),
                                ('TOUCHDOWN','td'),('ROLLOUT COMPLETE','end')]:
                    if ln.startswith(k):
                        detail = ln[:90]
                        ev.append((name, t, detail)); break
                mm = re.match(r'RWY SEL (.+?) hdg=', ln)
                if mm: ev_rwy = mm.group(1).strip()
    pos.sort(key=lambda r: r[0])
    rwy = next((d for n,t,d in ev if n=='rwy_sel'), 'Cochran 22L')
    rwy = re.search(r'RWY SEL (.+?) hdg=', rwy).group(1).strip() if ' hdg=' in rwy else rwy
    return pos, ev, rwy

def flight(fn):
    pos, ev, rwy = parse(fn)
    lat0, lon0, hdg0, gnd = RWYS[rwy]
    field = rwy.rsplit(' ',1)[0]
    END = None
    for n2,(la2,lo2,h2,_) in RWYS.items():
        if n2 != rwy and n2.rsplit(' ',1)[0]==field:
            d=(h2-hdg0+180)%360-180
            if abs(abs(d)-180)<20: END=(lo2,la2); break
    if END is None:
        r=np.radians(hdg0); END=(lon0-np.sin(r)*2600, lat0-np.cos(r)*2600)
    e = {}
    for n,t,d in ev:
        e.setdefault(n,[]).append((t,d))
    t_end0 = e.get('end',[(1e9,'')])[0][0]
    pos = [p for p in pos if p[0] <= t_end0+3]   # 截尾调试段（停稳 3 s 后即切场，留大余量会把别的机场点卷进来）
    X=[p[2]-lon0 for p in pos]; Y=[p[1]-lat0 for p in pos]; Z=[p[3] for p in pos]
    T=[p[0] for p in pos]
    caps = [t for t,_ in e.get('cap',[])]
    segs=[]
    def add(t0,t1,ph):
        if t1>t0: segs.append((t0,t1,ph))
    t_sel=e['rwy_sel'][0][0]
    t_td=e['td'][0][0]; t_end=e.get('end',[(pos[-1][0],'')])[0][0]
    t_abort=e.get('abort',[None])[0][0] if 'abort' in e else None
    t_rej=e.get('rejoin',[None])[0][0] if 'rejoin' in e else None
    t_orb=e.get('orbit',[None])[0][0] if 'orbit' in e else None
    t_rel=e.get('release',[None])[0][0] if 'release' in e else None
    add(pos[0][0],t_sel,'ground')
    if t_abort is None:
        add(t_sel,t_orb if t_orb is not None else caps[0],'approach')
        if t_orb is not None: add(t_orb,t_rel,'orbit'); add(t_rel,caps[0],'approach')
        add(caps[0],t_td,'glide')
    else:
        add(t_sel,t_orb if t_orb is not None else caps[0],'approach')
        if t_orb is not None: add(t_orb,t_rel,'orbit'); add(t_rel,caps[0],'approach')
        add(caps[0],t_abort,'glide')
        add(t_abort,(t_rej or caps[1]),'goaround')
        add((t_rej or caps[1]),caps[1],'approach'); add(caps[1],t_td,'glide')
    add(t_td,t_end,'rollout')
    traces=[]
    for t0,t1,ph in segs:
        idx=[i for i in range(len(T)) if t0<=T[i]<=t1]
        if len(idx)<2: continue
        col,lab=PHASES[ph]
        traces.append(dict(x=[X[i] for i in idx],y=[Y[i] for i in idx],z=[Z[i] for i in idx],
            mode='lines',name=lab,hovertemplate='%{customdata}<br>%%{x:.0f}, %%{y:.0f} m<extra>'+lab+'</extra>',
            customdata=['t=%.0f s · 高度 %.0f m'%(T[i],Z[i]) for i in idx],
            line=dict(color=col,width=5 if ph in('glide','goaround') else 4)))
    marks=[]
    for n,t,d in ev:
        if n in ('rwy_sel','end'): continue
        i=min(range(len(T)),key=lambda k:abs(T[k]-t))
        nm={'cap':'APP CAP','abort':'GLIDE ABORT','rejoin':'GA REJOIN','complete':'PATTERN COMPLETE',
            'orbit':'ORBIT ENTER','release':'ORBIT RELEASE','td':'TOUCHDOWN'}[n]
        marks.append(dict(type='scatter3d', x=[X[i]],y=[Y[i]],z=[Z[i]+18],mode='markers+text',name=nm,
            text=[nm],textposition='top center',textfont=dict(size=5,color='#222'),
            marker=dict(size=1.8,symbol='diamond',color='#ffd23f',line=dict(width=1,color='#222')),
            customdata=['t=%.0f s · 高度 %.0f m<br>%s'%(T[i],Z[i],d.replace('%','%%'))],
            hovertemplate='%%{customdata}<extra>%s</extra>'%nm))
    # 真实比例：aspectmode:'auto' 下箱体边长完全由 aspectratio 决定（'data'+range 会让 plotly 归一化失控）
    pad=800.0
    x0,x1=min(X)-pad,max(X)+pad; y0,y1=min(Y)-pad,max(Y)+pad
    z0,z1=min(Z)-pad*0.25,max(Z)+pad
    rx0,ry0,rz0=x1-x0,y1-y0,z1-z0
    # 跑道面(surface) + 中线延长
    dx,dy=END[0]-lon0,END[1]-lat0; L=float(np.hypot(dx,dy)); ux,uy=dx/L,dy/L
    vx,vy=-uy*75,ux*75
    rect=dict(type='surface',
              x=[[u*dx+v*vx for u in (0,0.5,1)] for v in (-1,1)],
              y=[[u*dy+v*vy for u in (0,0.5,1)] for v in (-1,1)],
              z=[[gnd+.5]*3]*2,
              surfacecolor=[[.5]*3]*2, cmin=0, cmax=1, showscale=False,
              colorscale=[[0,'#4a5568'],[1,'#4a5568']], opacity=0.95,
              name='%s 跑道 (%.0f m)'%(rwy,L), hovertemplate='runway %s<extra></extra>'%rwy)
    ex=dict(type='scatter3d', x=[0,-ux*min(13500, max(rx0,ry0)*1.2)], y=[0,-uy*min(13500, max(rx0,ry0)*1.2)], z=[gnd+.5]*2,
            mode='lines', name='中线延长线',
            line=dict(color='#7a9e3f',width=2,dash='dash'), hovertemplate='<extra></extra>')
    for tr in traces: tr.setdefault('type','scatter3d')
    traces += [rect, ex] + marks
    # 高度夸大：直接烘焙进 z 数据（plotly 3D aspect 体系在 auto/data+range 下均不可靠）
    # 每 scatter3d trace 带 zraw，前端滑条改倍数时 restyle z= zraw*ZEX；刻度 tickvals 映射真实高度
    ZEX0=5.0
    for tr in traces:
        if tr.get('type')=='scatter3d' and not np.ndim(tr['z'])>1:
            tr['zraw']=[float(v) for v in tr['z']]
            tr['z']=[v*ZEX0 for v in tr['zraw']]
    import math as _m
    raw=rz0/6.0
    p10=10**_m.floor(_m.log10(raw)); zdt=int(next(s for s in (p10,2*p10,5*p10,10*p10) if s>=raw))
    return dict(title='%s · %s'%(rwy,fn.split('/')[-1].replace('.log','')),traces=traces,
                zdtick=zdt, zmin=min(Z), zmax=max(Z),
                events=[dict(name=n,t=t,d=d) for n,t,d in ev])

data=[flight(p) for p in sys.argv[1:3]]
html = """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>SC-3b 全自主进近着陆 · 3D 航迹回放</title>
<script>__PLOTLY__</script>
<style>
 body{font-family:'Microsoft YaHei',sans-serif;margin:0;background:#f5f6f8}
 header{padding:14px 24px;background:#22303f;color:#fff}
 header h1{font-size:19px;margin:0} header p{font-size:12px;margin:4px 0 0;color:#b9c6d3}
 .tabs{display:flex;gap:8px;padding:12px 24px 0}
 .tabs button{padding:8px 18px;border:1px solid #c5ccd4;border-bottom:none;border-radius:8px 8px 0 0;
   background:#e6eaee;font-size:14px;cursor:pointer}
 .tabs button.on{background:#fff;font-weight:700;color:#1f4e79}
 #plot{height:78vh;margin:0 24px;background:#fff;border:1px solid #c5ccd4}
 .evts{margin:10px 24px;font-size:12px;color:#333;background:#fff;border:1px solid #c5ccd4;padding:8px 14px}
 .evts b{color:#1f4e79}
 .hint{margin:6px 24px 18px;font-size:12px;color:#777}
</style></head><body>
<header><h1>SC-3b 全自主进近着陆 · 交互式 3D 航迹</h1>
<p>每架次独立局部坐标（原点=跑道入口，单位 m，水平真实比例）· 高度轴夸大倍数见下方滑条 · 拖动旋转 / 滚轮缩放 / 双击复位 · 图例可点选隐藏分段</p></header>
<div class="tabs" id="tabs"></div>
<div style="margin:10px 24px 0;display:flex;align-items:center;gap:12px;background:#fff;border:1px solid #c5ccd4;border-bottom:none;padding:10px 14px;font-size:13px">
 高度轴夸大 <input type="range" id="zex" min="1" max="12" step="0.5" value="5" style="width:320px">
 <b id="zexv" style="color:#1f4e79;width:52px">×5.0</b>
 <span style="color:#888">拖动即时生效（1=真实比例）</span></div>
<div id="plot" style="margin-top:0"></div>
<div class="evts" id="evts"></div>
<div class="hint">配色：灰=地面 · 蓝=进近/收线 · 青=切线圆消高 · 橙=下滑拉平 · 红=复飞爬升 · 深红=滑跑 · 黄菱=关键事件</div>
<script>
const DATA = __DATA__;
const tabs=document.getElementById('tabs');
let ZEX=5.0, CUR=0;
function zticks(){const r=DATA[CUR],st=r.zdtick,v=[],t=[];
  for(let k=Math.ceil(r.zmin/st);k*st<=r.zmax*1.0001;k++){v.push(k*st*ZEX);t.push(String(k*st));}
  return {tickmode:'array',tickvals:v,ticktext:t,range:[r.zmin*ZEX-st,r.zmax*ZEX+st*2]};}
function scene(){const zt=zticks();return {xaxis:{title:'东向 (m)',nticks:7},
    yaxis:{title:'北向 (m)',nticks:7},
    zaxis:Object.assign({title:'高度 AMSL (m)'},zt),
    camera:{eye:{x:1.4,y:-1.4,z:0.55}},
    aspectmode:'data',
    bgcolor:'#fff'};}
function show(k){
  CUR=k;
  document.querySelectorAll('.tabs button').forEach((b,i)=>b.classList.toggle('on',i===k));
  Plotly.newPlot('plot',DATA[k].traces,{
    scene:scene(),
    margin:{l:0,r:0,t:34,b:0}, title:{text:DATA[k].title,font:{size:15}},
    legend:{orientation:'h',y:-0.06}, uirevision:1},{responsive:true,displaylogo:false});
  document.getElementById('evts').innerHTML='<b>事件时间线：</b>'+
    DATA[k].events.map(e=>e.name+' @t='+e.t.toFixed(0)+'s'+(e.d?'（'+e.d+'）':'')).join(' → ');
}
document.getElementById('zex').oninput=function(){
  ZEX=parseFloat(this.value);
  document.getElementById('zexv').textContent='×'+ZEX.toFixed(1);
  const gd=document.getElementById('plot'),zs=[],idx=[];
  DATA[CUR].traces.forEach((t,i)=>{if(t.zraw){zs.push(t.zraw.map(v=>v*ZEX));idx.push(i);}});
  const zt=zticks();
  Plotly.restyle(gd,{z:zs},idx).then(()=>Plotly.relayout(gd,
    {'zaxis.tickmode':zt.tickmode,'zaxis.tickvals':zt.tickvals,'zaxis.ticktext':zt.ticktext,'zaxis.range':zt.range}));
};
(function(){const s=document.getElementById('zex');   // 浏览器会记忆表单旧值，加载时强制写回
  s.value=ZEX; document.getElementById('zexv').textContent='×'+ZEX.toFixed(1);})();
DATA.forEach((f,i)=>{const b=document.createElement('button');b.textContent=f.title;
  b.onclick=()=>show(i);tabs.appendChild(b);});
show(0);
</script></body></html>"""
html = html.replace('__DATA__', json.dumps(data, ensure_ascii=False))
import plotly.offline as _po
html = html.replace('__PLOTLY__', _po.get_plotlyjs())   # 内嵌 plotly.js（~4.7 MB），彻底离线可用（Edge/无网/代理环境免疫 CDN 问题）
out = sys.argv[3] if len(sys.argv) > 3 else 'sc3b-track.html'
io.open(out, 'w', encoding='utf-8').write(html)
print("written", out, len(html)//1024, "KB")
