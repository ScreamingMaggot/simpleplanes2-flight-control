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

rows = list(csv.DictReader(open(os.path.join(DATA,'telemetry17.csv'))))
t = [float(r['t']) for r in rows]
def col(k): return [float(r[k]) for r in rows]
alt, agl, ias, pa, ra, thr = col('alt'), col('agl'), col('ias'), col('pa'), col('ra'), col('thr')
terr = [a - b for a, b in zip(alt, agl)]
vv = [0.0]
for i in range(1, len(t)):
    dt = t[i] - t[i-1]
    v = (alt[i] - alt[i-1]) / dt if dt > 0.005 else 0.0
    v = vv[-1] if abs(v) > 60 else v
    vv.append(v + (vv[-1] - v) * 0.7)  # 轻度平滑

# 目标阶梯（事件→t，来自 Player.log）
steps = [(8.1, 2), (9.0, 102), (9.3, 202), (9.7, 302), (93.2, 402), (94.6, 502),
         (120.8, 402), (121.4, 302), (181.5, 402), (182.3, 502)]
tgt_t, tgt_v = [0.0], [2]
for x, v in steps:
    tgt_t.append(x); tgt_v.append(v)
    tgt_t.append(x + 0.001); tgt_v.append(v)

fig, axes = plt.subplots(4, 1, figsize=(15, 11.5), sharex=True)
fig.suptitle('TESTaircraft v6.1 — 40 m/s 机动包线验收 (telemetry17, 22.5 Hz)', fontsize=14)

ax = axes[0]
ax.plot(t, alt, lw=1.1, color='tab:blue', label='Altitude AMSL (m)')
ax.plot(t, terr, lw=0.9, color='saddlebrown', label='地形高度 alt−agl (m)')
ax.plot(tgt_t, tgt_v, ls='--', lw=1, color='green', label='AGL 目标阶梯')
tgt_series = []
si = 0
for i, x in enumerate(t):
    while si < len(steps) and x >= steps[si][0]:
        si += 1
    tgt_series.append((steps[si-1][1] if si else 2) + terr[i])
ax.plot(t, tgt_series, ls=':', lw=1, color='gray', label='目标换算 AMSL')
ax.set_ylabel('AMSL (m)'); ax.legend(loc='upper right', fontsize=8); ax.grid(alpha=0.3)

ax = axes[1]
ax.plot(t, agl, lw=1.1, color='tab:cyan', label='AltitudeAgl (m)')
ax.axvspan(92, 121, color='green', alpha=0.08); ax.axvspan(181, 215, color='green', alpha=0.08)
ax.axvspan(120, 160, color='red', alpha=0.06)
ax.text(106, 620, '200m 上台阶①', fontsize=8, ha='center', color='green')
ax.text(140, 620, '200m 下台阶②', fontsize=8, ha='center', color='red')
ax.text(197, 620, '200m 上台阶③', fontsize=8, ha='center', color='green')
ax.set_ylabel('AGL (m)'); ax.legend(loc='upper right', fontsize=8); ax.grid(alpha=0.3)

ax = axes[2]
ax.plot(t, vv, lw=1.0, color='tab:orange', label='垂直速率 d(AMSL)/dt (m/s)')
ax.axhline(40, ls=':', color='red', lw=1); ax.axhline(-40, ls=':', color='red', lw=1)
ax.axhline(10, ls=':', color='gray', lw=1); ax.text(330, 10.6, 'v5.1 旧上限 ~+10', fontsize=8, color='gray')
ax.text(330, 40.8, 'VV_MAX=40', fontsize=8, color='red')
ax.set_ylabel('V/S (m/s)'); ax.legend(loc='upper right', fontsize=8); ax.grid(alpha=0.3)

ax = axes[3]
ax.plot(t, ias, lw=1.0, color='tab:red', label='IAS (m/s)')
ax.plot(t, pa, lw=0.9, color='tab:brown', alpha=0.7, label='PitchAngle (deg)')
ax.axhline(75, ls=':', color='purple', lw=1); ax.text(330, 76, '失速保护 V_MIN=75', fontsize=8, color='purple')
ax.set_ylabel('IAS / 俯仰'); ax.set_xlabel('t (s)'); ax.legend(loc='upper right', fontsize=8); ax.grid(alpha=0.3)
ax.set_xlim(0, 347)

plt.tight_layout()
plt.savefig(os.path.join(FIGS,'v61-envelope-report.png'), dpi=110)
print('saved')
