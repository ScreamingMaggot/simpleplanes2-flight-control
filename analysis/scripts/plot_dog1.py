import os, io, re, csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False
_S = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_S, '..', 'data')
FIGS = os.path.join(_S, '..', 'figures')

rows = list(csv.DictReader(open(os.path.join(DATA, 'telemetry22.csv'))))
t = [float(r['t']) for r in rows]
def col(k): return [float(r[k]) for r in rows]
ias, ra, agl, thr, rol = col('ias'), col('ra'), col('agl'), col('thr'), col('rol')

LOG = os.path.expanduser(r"~\AppData\LocalLow\Jundroo\SimplePlanes 2\Player.log")
s = io.open(LOG, encoding='utf-8', errors='ignore').read()
seek = [(float(a), int(b), float(c), float(d), float(e), int(f))
        for a, b, c, d, e, f in re.findall(r'SEEK,([\d.]+),(\d),([\d.]+),([+-][\d.]+),([+-][\d.]+),(\d)', s)]
# 日志含多局（按文件顺序拼接，t 回落=新局）：取第一局（含锁定收距的那次）
cut = len(seek)
for i in range(1, len(seek)):
    if seek[i][0] < seek[i-1][0] - 1:
        cut = i; break
seek = seek[:cut]
st  = [x[0] for x in seek]
lock = [x[1] for x in seek]
D   = [x[2] for x in seek]
Ddot = [x[3] for x in seek]
bankc = [x[4] for x in seek]
dc    = [x[5] for x in seek]

fig, axes = plt.subplots(4, 1, figsize=(14, 10), sharex=True)
fig.suptitle('v7.1 信标首咬（telemetry22，87s，手动接管收距）', fontsize=14)

ax = axes[0]
ax.plot(t, ias, lw=1.0, color='tab:red', label='IAS (m/s)')
ax.plot(t, agl, lw=1.0, color='tab:blue', label='AGL (m)')
ax.set_ylabel('m/s / m'); ax.legend(fontsize=8, loc='upper left'); ax.grid(alpha=0.3)

ax = axes[1]
ax.step(st, D, where='post', lw=1.2, color='green', label='目标距离 D (m)')
ax.fill_between(st, 0, 16000, where=[l == 1 for l in lock], color='green', alpha=0.10, label='锁定区')
ax.fill_between(st, 0, 16000, where=[d == 1 for d in dc], color='orange', alpha=0.10, label='狗斗模式 ON')
ax.set_ylabel('D (m)'); ax.legend(fontsize=8, loc='upper right'); ax.grid(alpha=0.3)

ax = axes[2]
ax.plot(st, Ddot, lw=1.2, color='purple', label='Ddot 收距率 (m/s)')
ax.axhline(0, lw=0.8, color='gray')
ax.set_ylabel('m/s'); ax.legend(fontsize=8); ax.grid(alpha=0.3)

ax = axes[3]
ax.plot(t, ra, lw=1.0, color='tab:purple', label='RollAngle 实测 (deg)')
ax.step(st, bankc, where='post', lw=1.2, color='black', alpha=0.8, label='seek bank 指令 (deg)')
ax.plot(t, rol, lw=0.9, color='tab:pink', alpha=0.8, label='Roll 轴指令(飞行员/AP)')
ax.set_ylabel('deg'); ax.set_xlabel('t (s)'); ax.legend(fontsize=8); ax.grid(alpha=0.3)
ax.set_xlim(0, 88)

plt.tight_layout()
plt.savefig(os.path.join(FIGS, 'v71-dog-report.png'), dpi=110)
print('saved')
