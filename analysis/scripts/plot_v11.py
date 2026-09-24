import os, io, re, csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False
_S = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_S, '..', 'data')
FIGS = os.path.join(_S, '..', 'figures')

rows = list(csv.DictReader(open(os.path.join(DATA, 'telemetry35.csv'))))
t = [float(r['t']) for r in rows]
def col(k): return [float(r[k]) for r in rows]
ias, ra, thr, agl, alt = col('ias'), col('ra'), col('thr'), col('agl'), col('alt')
LOG = os.path.expanduser(r"~\AppData\LocalLow\Jundroo\SimplePlanes 2\Player.log")
s = io.open(LOG, encoding='utf-8', errors='ignore').read()
hdr = s.rindex('TELHDR')
seek = [(float(a), int(b), float(c)) for a, b, c in re.findall(r'SEEK,([\d.]+),(\d),([\d.]+),', s[hdr:])]
st = [x[0] for x in seek]
lk = [x[1] for x in seek]
dd = [x[2] / 1000 for x in seek]

fig, axes = plt.subplots(4, 1, figsize=(15, 11), sharex=True)
fig.suptitle('v11 验收局（telemetry35, 28.5Hz）：狗斗减速带首验 + PN 追踪 Phoenix', fontsize=14)

ax = axes[0]
ax.plot(t, agl, lw=1.1, color='tab:cyan', label='AGL (m)')
ax2 = ax.twinx()
ax2.plot(st, dd, lw=1.2, color='green', label='目标距离 (km)')
ax2.fill_between(st, 0, 18, where=[l == 1 for l in lk], color='green', alpha=0.10)
ax.set_ylabel('AGL (m)'); ax2.set_ylabel('D (km)')
ax.text(110, 2350, '锁定 Phoenix\n16.7 km 起咬', fontsize=9, color='green')
ax.legend(loc='upper left', fontsize=8); ax2.legend(loc='upper right', fontsize=8); ax.grid(alpha=0.3)

ax = axes[1]
ax.plot(t, ra, lw=1.0, color='tab:purple', label='RollAngle (deg)')
ax.fill_between(st, -90, 90, where=[l == 1 for l in lk], color='green', alpha=0.08, label='锁定区')
ax.axhline(85, ls=':', color='red', lw=1); ax.axhline(-85, ls=':', color='red', lw=1)
ax.text(63, 84, '坡度限 ±85', fontsize=8, color='red')
ax.set_ylabel('坡度 (deg)'); ax.legend(loc='upper right', fontsize=8); ax.grid(alpha=0.3)

ax = axes[2]
ax.plot(t, ias, lw=1.1, color='tab:red', label='IAS (m/s)')
ax.axhspan(140, 170, color='orange', alpha=0.15)
ax.text(5, 174, '狗斗机动速度带 140~170', fontsize=9, color='darkorange')
ax.set_ylabel('IAS (m/s)'); ax.legend(loc='upper right', fontsize=8); ax.grid(alpha=0.3)

ax = axes[3]
ax.plot(t, thr, lw=1.1, color='green', label='Throttle')
ax.fill_between(st, 0, 1.1, where=[l == 1 for l in lk], color='green', alpha=0.08)
ax.set_ylabel('油门'); ax.set_xlabel('t (s)'); ax.legend(loc='upper right', fontsize=8); ax.grid(alpha=0.3)
ax.set_xlim(0, 158)

plt.tight_layout()
plt.savefig(os.path.join(FIGS, 'v11-dogfight-report.png'), dpi=110)
print('saved')
