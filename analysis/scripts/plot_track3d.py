# SC-3b 3D 航迹图：进近/下滑/滑跑分段着色 + 跑道实体 + 关键事件标注
# 用法: python plot_track3d.py [日志文件]
import io, os, sys, re
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

_S = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_S, '..', 'data')
FIGS = os.path.join(_S, '..', 'figures')
CAND = [sys.argv[1]] if len(sys.argv) > 1 else [
    os.path.join(DATA, 'Player.sc3b-app6.log'),
    os.path.expanduser(r"~\AppData\LocalLow\Jundroo\SimplePlanes 2\Player.log")]
LOG = next((p for p in CAND if os.path.isfile(p)), None)
assert LOG, "找不到日志"

pos, app, land = [], [], []
rwy_sel_name = None
tel_t = []
with io.open(LOG, encoding='utf-8', errors='ignore') as f:
    for ln in f:
        ln = ln.strip()
        if ln.startswith('POS,'):
            p = ln.split(',')
            try:
                pos.append((float(p[2]), float(p[3]), float(p[4]), float(p[5])))  # t,lat,lon,alt
            except (ValueError, IndexError):
                continue
        elif ln.startswith('APP,'):
            p = ln.split(',')
            try:
                app.append(float(p[1]))
            except (ValueError, IndexError):
                continue
        elif ln.startswith('LAND,'):
            p = ln.split(',')
            try:
                land.append((float(p[1]), int(float(p[2]))))
            except (ValueError, IndexError):
                continue
        elif ln.startswith('RWY SEL '):
            mm = re.match(r'RWY SEL (.+?) hdg=', ln)
            if mm:
                rwy_sel_name = mm.group(1).strip()  # 取最后一次 SEL=落地那条跑道
assert pos and land, "缺 POS/LAND 流"
pos.sort(key=lambda r: r[0])
t_sel = app[0] if app else land[0][0]
t_cap = next(t for t, s in land if s == 2)
t_td  = next((t for t, s in land if s == 4), land[-1][0])
t_end = land[-1][0]

# 跑道表（恒等映射 lat=z lon=x，源=runway-locations.json）；按日志 RWY SEL 选道，对头=同机场差180°
RWYS = {
    'Cochran 04L': (-29883, 12873, 45, 3),  'Cochran 22L': (-27887, 15064, 225, 3),
    'Cochran 18':  (-26945, 14477, 180, 3), 'Shepard 34':  (-2330,  4381,  345, 11),
    'Shepard 22':  (-2556,  4340,  225, 11),'Bannock 05':  (-38878, 6533,  50,  5),
    'Bannock 23':  (-37451, 8234,  230, 5), 'Bannock 08':  (-38872, 6204,  80,  5),
    'Bannock 26':  (-38681, 7288,  260, 5), 'Kunimitsu 1': (-5540,  12797, 10,  10),
    'Kunimitsu 19':(-4500,  12980, 190, 10),'Kunimitsu 4': (-6180,  12122, 40,  10),
    'Kunimitsu 22':(-5160,  12978, 220, 10),
}
name = rwy_sel_name or 'Cochran 22L'
lat0, lon0, hdg0, gnd = RWYS[name]
THR = (lon0, lat0)                      # lon, lat
field = name.rsplit(' ', 1)[0]
END = None
for n2, (la2, lo2, h2, _) in RWYS.items():
    if n2 != name and n2.rsplit(' ', 1)[0] == field:
        d = (h2 - hdg0 + 180) % 360 - 180          # 与 180° 对头差<20 即配对
        if abs(abs(d) - 180) < 20:
            END = (lo2, la2); break
if END is None:                          # 无对头：按 2.6 km 投影造一头
    r = np.radians(hdg0)
    END = (THR[0] + np.sin(r) * 2600 * -1, THR[1] + np.cos(r) * 2600 * -1)
GND = float(gnd)
print('runway=%s THR=%s END=%s' % (name, THR, END))
def rwy_rect(wid=150.0):
    dx, dy = END[0] - THR[0], END[1] - THR[1]
    L = np.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    vx, vy = -uy * wid / 2, ux * wid / 2
    c = [[THR[0] + vx, THR[1] + vy], [THR[0] - vx, THR[1] - vy],
         [END[0] - vx, END[1] - vy], [END[0] + vx, END[1] + vy]]
    poly = [[x, y, GND + 0.5] for x, y in c]
    return poly, L, (ux, uy)
poly, RL, (ux, uy) = rwy_rect()

fig = plt.figure(figsize=(12.5, 8.6), dpi=150)
ax = fig.add_subplot(111, projection='3d')

def seg(t0, t1, color, lw, label=None):
    pts = [(lon, lat, al) for (t, lat, lon, al) in pos if t0 <= t <= t1]
    if len(pts) > 1:
        xs, ys, zs = zip(*pts)
        ax.plot(xs, ys, zs, color=color, lw=lw, label=label)

seg(pos[0][0], t_sel, '#999999', 1.2, '地面滑跑/起飞')
seg(t_sel, t_cap, '#1f6fb4', 2.6, '进近段（截获+等高）')
seg(t_cap, t_td, '#e07b39', 2.6, '下滑+拉平')
seg(t_td, t_end, '#b03a48', 2.6, '滑跑减速')

# 跑道面 + 中线延长线
ax.add_collection3d(Poly3DCollection([poly], facecolor='#4a5568', alpha=0.95, edgecolor='k', lw=0.6))
ex0 = [THR[0] + ux * 120, THR[1] + uy * 120]
ex1 = [THR[0] - ux * 13500, THR[1] - uy * 13500]
ax.plot([ex0[0], ex1[0]], [ex0[1], ex1[1]], [GND + 0.5, GND + 0.5],
        ls='--', color='#7a9e3f', lw=1.4)
ax.text(THR[0] + 500, THR[1] + 700, GND + 90, '%s (%.0f m)' % (name, RL), fontsize=9, color='#222')

def mark(t, sym, color, txt, dz=0):
    r = min(pos, key=lambda p: abs(p[0] - t))
    ax.scatter([r[2]], [r[1]], [r[3] + 12], marker=sym, s=90, color=color, depthshade=False, edgecolor='k', lw=0.6)
    ax.text(r[2] + 220, r[1] + 220, r[3] + 40 + dz, txt, fontsize=9, color=color, fontweight='bold')

mark(t_sel, 'o', '#1f6fb4', '按9 RWY SEL')
mark(t_cap, '*', '#e07b39', 'APP CAP 截获')
mark(t_td, 'X', '#b03a48', 'TOUCHDOWN')

xs_all = [p[2] for p in pos] + [THR[0], END[0], ex1[0]]
ys_all = [p[1] for p in pos] + [THR[1], END[1], ex1[1]]
zs_all = [p[3] for p in pos]
x0, x1 = min(xs_all), max(xs_all)
y0, y1 = min(ys_all), max(ys_all)
ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_zlim(0, max(zs_all) * 1.15)
ax.set_box_aspect(((x1 - x0), (y1 - y0), (max(zs_all) * 1.15) * 6))  # 高度夸大 6 倍
ax.set_xlabel('东向 (m, Longitude)'); ax.set_ylabel('北向 (m, Latitude)'); ax.set_zlabel('高度 AMSL (m)')
ax.view_init(elev=24, azim=-58)
ax.set_title('SC-3b 全自主进近着陆 3D 航迹 — %s · %s' % (name, os.path.basename(LOG)), fontsize=13, fontweight='bold')
ax.legend(loc='upper left', fontsize=9)
fig.text(0.99, 0.02, '注：高度轴夸大 6×；虚线=跑道中线延长线（13.5 km）', ha='right', fontsize=8, color='#666')
out = os.path.join(FIGS, 'sc3b-track3d-%s.png' % os.path.basename(LOG).replace('Player.','').replace('.log',''))
fig.tight_layout()
fig.savefig(out)
print(out)
