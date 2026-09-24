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

rows = list(csv.DictReader(open(os.path.join(DATA,'telemetry18.csv'))))
t = [float(r['t']) for r in rows]
def col(k): return [float(r[k]) for r in rows]
alt, agl, ias, pa, gs, thr = col('alt'), col('agl'), col('ias'), col('pa'), col('gs'), col('thr')
terr = [a - b for a, b in zip(alt, agl)]
vv, alf, vvf = [0.0]*len(t), [0.0]*len(t), [0.0]*len(t)
trate = [0.0]*len(t)
for i in range(1, len(t)):
    dt = t[i] - t[i-1]
    if 0.005 < dt < 0.5:
        va = (alt[i]-alt[i-1])/dt; vg = (agl[i]-agl[i-1])/dt
        va = alf[i-1] if abs(va) > 60 else va
        vg = vvf[i-1] if abs(vg) > 60 else vg
        k = min(1, dt*2*3.14159*0.5)
        alf[i] = alf[i-1] + (va-alf[i-1])*k
        vvf[i] = vvf[i-1] + (vg-vvf[i-1])*k
        vv[i] = alf[i]
    else:
        alf[i], vvf[i], vv[i] = alf[i-1], vvf[i-1], alf[i-1]
    trate[i] = trate[i-1] + ((alf[i]-vvf[i]) - trate[i-1]) * min(1, dt*2*3.14159*0.25)
floor = [60 + max(0, tr) * (200 / max(g, 10)) for tr, g in zip(trate, gs)]
tgt_amsl = [max(202, f) + te for f, te in zip(floor, terr)]

fig, axes = plt.subplots(3, 1, figsize=(15, 9.5), sharex=True)
fig.suptitle('TESTaircraft v6.1 — AP-only 局：山脊遭遇，GUARD 首弹 (telemetry18, 22Hz)', fontsize=14)

ax = axes[0]
ax.plot(t, alt, lw=1.2, color='tab:blue', label='Altitude AMSL')
ax.plot(t, tgt_amsl, lw=1.6, color='red', ls='--', label='AP 实际目标 (max(202,floor)+地形)')
ax.plot(t, terr, lw=1.0, color='saddlebrown', label='地形 alt−agl')
ax.axvline(214.4, color='red', lw=1)
ax.text(200, 480, 'GUARD ON\nfloor=263 (rise 203m/200m)', fontsize=8, color='red')
ax.text(215.5, 480, '撞脊', fontsize=9, color='red')
ax.set_ylabel('m'); ax.legend(loc='upper left', fontsize=8); ax.grid(alpha=0.3)
ax.set_ylim(-30, 620)

ax = axes[1]
ax.plot(t, vv, lw=1.1, color='tab:orange', label='V/S d(AMSL)/dt (m/s)')
ax.plot(t, floor, lw=1.0, color='red', alpha=0.6, label='地形下限 floor (m AGL)')
ax.plot(t, agl, lw=0.9, color='tab:cyan', alpha=0.6, label='AGL (m)')
ax.axvline(214.4, color='red', lw=1)
ax.set_ylabel('m / m·s⁻¹'); ax.legend(loc='upper left', fontsize=8); ax.grid(alpha=0.3)

ax = axes[2]
ax.plot(t, ias, lw=1.1, color='tab:red', label='IAS (m/s)')
ax.plot(t, pa, lw=0.9, color='tab:brown', alpha=0.7, label='PitchAngle (deg)')
ax.plot(t, thr, lw=0.9, color='green', alpha=0.7, label='Throttle')
ax.axhline(75, ls=':', color='purple', lw=1)
ax.axvline(214.4, color='red', lw=1)
ax.set_ylabel('IAS / deg'); ax.set_xlabel('t (s)'); ax.legend(loc='lower left', fontsize=8); ax.grid(alpha=0.3)
ax.set_xlim(0, 219)

plt.tight_layout()
plt.savefig(os.path.join(FIGS,'v61-guard-report.png'), dpi=110)
print('saved')
