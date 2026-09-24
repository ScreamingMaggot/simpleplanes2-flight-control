import os
_S = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_S, '..', 'data')
FIGS = os.path.join(_S, '..', 'figures')
import csv, bisect
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

rows = list(csv.DictReader(open(os.path.join(DATA,'telemetry16.csv'))))[:-1]  # drop stray row
def col(k): return [float(r[k]) for r in rows]
t, agl, ias, ra, pa, pr = col('t'), col('agl'), col('ias'), col('ra'), col('pa'), col('pr')

fig, axes = plt.subplots(4, 1, figsize=(15, 11), sharex=True)
fig.suptitle('TESTaircraft v5.1 — 370 kph 变向横风压力测试 (telemetry16, 单场次 t=0~938s)', fontsize=14)

ax = axes[0]
ax.plot(t, agl, lw=0.9, color='tab:blue', label='AltitudeAgl (m)')
ax.axhline(381, ls='--', lw=1, color='gray', label='AP 目标 381 m (飞行A)')
ax.axhline(300, ls='--', lw=1, color='green', label='AP 目标 300 m (飞行B)')
ax.axvspan(370, 445, color='red', alpha=0.15)
ax.text(407, 330, '① 螺旋俯冲\n触地坠毁', ha='center', color='red', fontsize=9)
ax.axvspan(580, 840, color='green', alpha=0.10)
ax.text(710, 40, '② 300 m 定高保持段', ha='center', color='green', fontsize=9)
ax.axvspan(843, 880, color='orange', alpha=0.20)
ax.text(861, 190, '③ 二次剧烈\n下冲~59 m', color='darkorange', fontsize=9, ha='center')
ax.set_ylabel('AGL (m)'); ax.legend(loc='upper right', fontsize=8); ax.grid(alpha=0.3)

ax = axes[1]
ax.plot(t, ra, lw=0.9, color='tab:purple', label='RollAngle (deg)')
for y, c in ((33, 'gray'), (-33, 'gray'), (60, 'red'), (-60, 'red')):
    ax.axhline(y, ls=':', lw=1, color=c)
ax.text(500, 34.5, 'AP 补偿包线 33°', fontsize=8, color='gray')
ax.text(500, 61.5, '失控边界 ~60°', fontsize=8, color='red')
ax.axvspan(370, 445, color='red', alpha=0.15)
ax.axvspan(843, 880, color='orange', alpha=0.20)
ax.set_ylabel('坡度 (deg)'); ax.set_ylim(-95, 95); ax.legend(loc='upper right', fontsize=8); ax.grid(alpha=0.3)

ax = axes[2]
ax.plot(t, pa, lw=0.9, color='tab:brown', label='PitchAngle (deg)')
ax.axvspan(370, 445, color='red', alpha=0.15)
ax.axvspan(843, 880, color='orange', alpha=0.20)
ax.set_ylabel('俯仰角 (deg)'); ax.legend(loc='upper right', fontsize=8); ax.grid(alpha=0.3)

ax = axes[3]
ax.plot(t, ias, lw=0.9, color='tab:red', label='IAS (kph)')
ax.axvspan(370, 445, color='red', alpha=0.15)
ax.axvspan(843, 880, color='orange', alpha=0.20)
ax.set_ylabel('空速 (kph)'); ax.set_xlabel('时间 (s)'); ax.legend(loc='upper right', fontsize=8); ax.grid(alpha=0.3)
ax.set_xlim(0, 940)

plt.tight_layout()
plt.savefig(os.path.join(FIGS,'crosswind-stress-report.png'), dpi=110)
print('saved')
