# SC-3 首次全自主着陆 报告图：下滑剖面 / 速度-油门 / 横向跟踪 / 拉平窗口 α 取证
# 用法: python plot_landing.py [日志文件]   （默认读归档的着陆局 Player.log）
import io, os, sys, re
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

_S = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_S, '..', 'data')
FIGS = os.path.join(_S, '..', 'figures')
CAND = [sys.argv[1]] if len(sys.argv) > 1 else [
    os.path.join(DATA, 'Player.landing-sc3.log'),
    os.path.expanduser(r"~\AppData\LocalLow\Jundroo\SimplePlanes 2\Player.log")]
LOG = next((p for p in CAND if os.path.isfile(p)), None)
assert LOG, "找不到日志"

GND = 1.0  # RWY CAPTURED groundalt=1
# LAND,t,stage,dist,eps_h,tgt,alt,thr,ias,l[,aoa]；APP,t,s,eps_h,tgtA,alt,thr,ias,l（SC-3b 进近段）
land, app, tel = [], [], {}
with io.open(LOG, encoding='utf-8', errors='ignore') as f:
    for ln in f:
        ln = ln.strip()
        if ln.startswith('LAND,'):
            p = ln.split(',')
            try:
                r = [float(p[1]), int(float(p[2]))] + [float(x) for x in p[3:10]]
                r.append(float(p[10]) if len(p) > 10 else None)
            except (ValueError, IndexError):
                continue
            land.append(r)
        elif ln.startswith('APP,'):
            p = ln.split(',')
            try:
                r = [float(x) for x in p[1:9]]   # 0t 1s 2eps 3tgtA 4alt 5thr 6ias 7l
            except (ValueError, IndexError):
                continue
            app.append(r)
        elif ln.startswith('TEL,'):
            p = ln.split(',')
            try:
                v = [float(x) for x in p[1:23]]
            except ValueError:
                continue
            tel.setdefault(int(v[0]), []).append(v[1:])
assert land, "没有 LAND 行"
land.sort(key=lambda r: r[0])
# 多局切分：时间断流 >8 s 视为另一架次，取下滑行数最多的一局
segs, cur = [], [land[0]]
for r in land[1:]:
    if r[0] - cur[-1][0] > 8:
        segs.append(cur); cur = []
    cur.append(r)
segs.append(cur)
land = max(segs, key=lambda s: sum(1 for r in s if r[1] == 2))
# 同架次的 APP 行：从首条 LAND 行向前连续回溯（断流 >10 s 截断）
app.sort(key=lambda r: r[0])
app_sel, buf = [], []
for r in app:
    if r[0] < land[0][0] - 0.5:
        if buf and r[0] - buf[-1][0] > 10:
            buf = []
        buf.append(r)
    else:
        break
if buf and land[0][0] - buf[-1][0] < 60:
    app_sel = buf
# RWY SEL 跑道名（标题用）
sel_name = None
with io.open(LOG, encoding='utf-8', errors='ignore') as f:
    for ln in f:
        m = re.match(r'RWY SEL ([A-Za-z0-9 ]+) hdg', ln.strip())
        if m:
            sel_name = m.group(1).strip()
# land 行: 0t 1stage 2dist 3eps_h 4tgt 5alt 6thr 7ias 8l 9aoa

def cover(rows, t0, t1):
    return [r for r in rows if t0 <= r[0] <= t1]
t0, t1 = land[0][0] - 2, land[-1][0] + 2
cid = max(tel, key=lambda c: len(cover(tel[c], t0, t1)))
T = cover(sorted(tel[cid]), t0, t1)  # TEL 列: 0t 3ias 5pa 11aoa 14vg 16thr
glide = [r for r in land if r[1] == 2]
roll  = [r for r in land if r[1] == 4]
td_t, td_d = (roll[0][0], roll[0][2]) if roll else (glide[-1][0], glide[-1][2])
end_t, end_d = (roll[-1][0], roll[-1][2]) if roll else (glide[-1][0], glide[-1][2])

fig = plt.figure(figsize=(13.6, 12.6) if app_sel else (13.6, 9.2), dpi=150)
gs = fig.add_gridspec(3 if app_sel else 2, 2, height_ratios=[1, 1, 0.9] if app_sel else [1, 1], hspace=0.34)
ax = [[fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])],
      [fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])],
      [fig.add_subplot(gs[2, :]), None] if app_sel else [None, None]]
fig.suptitle("SC-3/3b 全自主进近与着陆实测记录 — TESTaircraft · cid %d%s" % (cid, " · %s" % sel_name if sel_name else ""),
             fontsize=15, fontweight='bold', y=0.99)

# (a) 下滑剖面
a = ax[0][0]
d_g = [r[2] for r in glide]
a.plot(d_g, [r[5] - GND for r in glide], lw=2.2, color='#1f6fb4', label='实际高度 AGL')
a.plot(d_g, [r[4] - GND for r in glide], '--', lw=1.4, color='#e07b39', label='下滑道目标 (3.5°)')
a.axvspan(td_d, max(end_d, td_d) + 30, color='#7a9e3f', alpha=0.15)
a.plot([r[2] for r in roll], [r[5] - GND for r in roll], lw=2, color='#7a9e3f', label='滑跑段')
a.annotate('TOUCHDOWN\n距捕获点 %.0f m' % td_d, xy=(td_d, 3), xytext=(td_d - 260, 50),
           arrowprops=dict(arrowstyle='->', color='k'), fontsize=9)
a.set_xlim(0, max(max(d_g), end_d, td_d) + 120); a.set_ylim(0, max(r[5] - GND for r in glide) * 1.15)
a.set_xlabel('沿跑道距捕获点 (m)'); a.set_ylabel('AGL (m)')
a.set_title('(a) 进近剖面：%.0f m 高度进入 · %.0f m 处接地 · 滑跑 %.0f m 停稳'
            % (glide[0][5] - GND, td_d, end_d - td_d), fontsize=11)
a.legend(fontsize=8); a.grid(alpha=0.3)

# (b) 速度与油门/刹车
b = ax[0][1]
b.plot([r[0] for r in land], [r[7] for r in land], lw=2, color='#1f6fb4', label='IAS')
b.axhspan(51, 59, color='#1f6fb4', alpha=0.10, label='进近带 55±4 m/s')
b2 = b.twinx()
b2.fill_between([r[0] for r in land], [r[6] * 100 for r in land], color='#e07b39', alpha=0.35, label='油门 %')
b2.axvspan(td_t, end_t, color='#7a9e3f', alpha=0.25)
b2.text((td_t + end_t) / 2, 62, '油门 0\n满刹车', ha='center', fontsize=8.5, color='#3d5220')
b.axvline(td_t, color='k', ls=':', lw=1)
b.set_xlabel('t (s)'); b.set_ylabel('IAS (m/s)'); b2.set_ylabel('油门 (%)'); b2.set_ylim(0, 105)
b.set_title('(b) 能量管理：触地 %.0f m/s · 刹车 %.1f s 停稳 (IAS<5)'
            % (glide[-1][7], end_t - td_t), fontsize=11)
b.legend(fontsize=8, loc='center right'); b.grid(alpha=0.3)

# (c) 横向跟踪
c = ax[1][0]
c.plot(d_g, [r[3] for r in glide], lw=1.6, color='#b03a48', label='航向偏差 εh (°)')
c.set_xlabel('沿跑道距捕获点 (m)'); c.set_ylabel('εh (°)')
cl = c.twinx()
cl.plot(d_g, [r[8] for r in glide], lw=2, color='#1f6fb4', label='右偏距 l (m)')
cl.set_ylabel('l (m)'); cl.set_ylim(-40, 40)
cl.axhspan(-2, 2, color='#1f6fb4', alpha=0.15)
c.set_title('(c) 横向跟踪：全场 |l| ≤ %.0f m · |εh| ≤ %.1f°（蓝带=±2 m）'
            % (max(abs(r[8]) for r in glide), max(abs(r[3]) for r in glide)), fontsize=11)
c.legend(fontsize=8, loc='upper left'); cl.legend(fontsize=8, loc='upper right'); c.grid(alpha=0.3)

# (d) 拉平窗口 α 取证（真 α = −craft.AngleOfAttack，platform-facts §25 符号反）
d = ax[1][1]
w = [r for r in T if td_t - 6 <= r[0] <= td_t + 4]
d.plot([r[0] for r in w], [r[5] for r in w], lw=2, color='#1f6fb4', label='俯仰角 θ')
d.plot([r[0] for r in w], [-r[11] for r in w], lw=2, color='#b03a48', label='真迎角 α')
d.axhline(8, ls='--', color='#7a9e3f', lw=1.4, label='目标 α=8° (LG_ALPHA)')
d.axvline(td_t, color='k', ls=':', lw=1.2)
atd = min(w, key=lambda r: abs(r[0] - td_t))
d.set_ylim(-9, 11)
d.annotate('接地瞬间：θ = %+.1f°、真 α = %.1f°\n（判读尺=接地前：滑跑 pa 被刹车低头力矩接管）' % (atd[5], -atd[11]),
           xy=(td_t, atd[5]), xytext=(w[0][0] + 0.3, -8.3), fontsize=9,
           arrowprops=dict(arrowstyle='->', color='k'))
d.set_xlabel('t (s)'); d.set_ylabel('角度 (°)')
d.set_title('(d) 触地前后 6+4 s：姿态/真迎角通道', fontsize=11)
d.legend(fontsize=8, loc='upper right'); d.grid(alpha=0.3)

# (e) SC-3b 进近段：延长线汇入 + FAF 闸门（无 APP 行则整面板隐藏）
if app_sel:
    e = ax[2][0]
    ss = [r[1] for r in app_sel]
    e.plot(ss, [r[7] for r in app_sel], lw=2, color='#1f6fb4', label='中线偏距 l (m)')
    e.axhspan(-250, 250, color='#1f6fb4', alpha=0.10, label='旧截获带 ±250 m')
    e.axvline(4500, ls='--', color='#7a9e3f', lw=1.4, label='FAF 下滑起始点 s=4.5 km')
    e.axvline(0, color='k', lw=0.8)
    e.invert_xaxis()
    e2 = e.twinx()
    e2.plot(ss, [r[4] - GND for r in app_sel], lw=2, color='#e07b39', label='高度 AGL (m)')
    e2.axhline(app_sel[0][3] - GND, ls=':', color='#e07b39', lw=1.2)
    cap = [r for r in app_sel if r[1] <= 4500]
    if cap:
        e.plot(cap[0][1], cap[0][7], 'k*', ms=13, label='APP CAP 转下滑')
    e.set_xlabel('沿最终航道至触地点距离 s (m)  ←进近方向')
    e.set_ylabel('l (m)'); e2.set_ylabel('AGL (m)')
    e.set_title('(e) SC-3b 进近段：延长线汇入·等高平飞·FAF 转下滑', fontsize=11)
    h1, l1 = e.get_legend_handles_labels(); h2, l2 = e2.get_legend_handles_labels()
    e.legend(h1 + h2, l1 + l2, fontsize=8, loc='upper right'); e.grid(alpha=0.3)

fig.text(0.99, 0.005, '数据源: %s' % os.path.basename(LOG), ha='right', fontsize=7, color='#888')
out = os.path.join(FIGS, 'sc3-landing-report.png')
fig.tight_layout(rect=(0, 0.012, 1, 0.955))
fig.savefig(out)
print(out)
