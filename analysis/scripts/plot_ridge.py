import os
_S = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_S, '..', 'data')
FIGS = os.path.join(_S, '..', 'figures')
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

rows = list(csv.DictReader(open(os.path.join(DATA,'telemetry19.csv'))))
t = [float(r['t']) for r in rows]
def col(k): return [float(r[k]) for r in rows]
alt, agl, ias, pa, thr = col('alt'), col('agl'), col('ias'), col('pa'), col('thr')
terr = [a - b for a, b in zip(alt, agl)]
tgt = [302 if x < 281.9 else 202 for x in t]
tgt_amsl = [tg + te for tg, te in zip(tgt, terr)]
vv = [0.0]*len(t)
for i in range(1, len(t)):
    dt = t[i] - t[i-1]
    if 0.005 < dt < 0.5:
        v = (alt[i]-alt[i-1])/dt
        vv[i] = vv[i-1] if abs(v) > 60 else v
    else:
        vv[i] = vv[i-1]

fig, axes = plt.subplots(3, 1, figsize=(15, 10), sharex=True)
fig.suptitle('TESTaircraft v6.2 — 缓坡山脊穿越 (telemetry19, 13.7Hz, AP 132.8s 接通)', fontsize=14)

ax = axes[0]
ax.plot(t, alt, lw=1.2, color='tab:blue', label='Altitude AMSL')
ax.plot(t, tgt_amsl, lw=1.2, ls='--', color='green', label='目标 AMSL = AGL目标+地形')
ax.plot(t, terr, lw=1.0, color='saddlebrown', label='地形 alt−agl')
ax.axhline(698, ls=':', color='red', lw=1)
ax.plot([248], [712], 'r*', ms=14, label='最险时刻 t=248 agl=14m')
ax.axvline(132.8, color='gray', lw=1); ax.text(134, 50, 'AP 接通', fontsize=8, color='gray')
ax.set_ylabel('m'); ax.legend(loc='upper left', fontsize=8); ax.grid(alpha=0.3)

ax = axes[1]
ax.plot(t, agl, lw=1.1, color='tab:cyan', label='AGL (m)')
ax.plot(t, tgt, lw=1.0, ls='--', color='green', label='AGL 目标')
ax.plot(t, vv, lw=1.0, color='tab:orange', label='V/S (m/s)')
ax.axhline(60, ls=':', color='red', lw=1); ax.text(350, 66, '净空下限60', fontsize=8, color='red')
ax.axvline(132.8, color='gray', lw=1)
ax.set_ylabel('m / m·s⁻¹'); ax.legend(loc='upper left', fontsize=8); ax.grid(alpha=0.3)

ax = axes[2]
ax.plot(t, ias, lw=1.1, color='tab:red', label='IAS (m/s)')
ax.plot(t, pa, lw=0.9, color='tab:brown', alpha=0.7, label='PitchAngle (deg)')
ax.plot(t, thr, lw=0.9, color='green', alpha=0.6, label='Throttle')
ax.axvline(132.8, color='gray', lw=1)
ax.set_ylabel('IAS / deg'); ax.set_xlabel('t (s)'); ax.legend(loc='upper left', fontsize=8); ax.grid(alpha=0.3)
ax.set_xlim(0, 391)

plt.tight_layout()
plt.savefig(os.path.join(FIGS,'v62-ridge-report.png'), dpi=110)
print('saved')
