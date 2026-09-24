# TESTfighter 数字孪生辨识（telemetry20 手动飞行段，输入=重构舵偏度，输出误差仿真拟合）
import os, csv, math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.optimize import least_squares
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False
_S = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_S, '..', 'data')
FIGS = os.path.join(_S, '..', 'figures')

rows = list(csv.DictReader(open(os.path.join(DATA, 'telemetry20.csv'))))
def col(k): return np.array([float(r[k]) for r in rows])
t, alt, agl, ias, pa, pr, ra, rr, thr, trim, pit, rol, yr = (
    col('t'), col('alt'), col('agl'), col('ias'), col('pa'), col('pr'),
    col('ra'), col('rr'), col('thr'), col('trim'), col('pit'), col('rol'), col('yr'))

# 舵面偏度重构（内环表达式已知）
de = np.clip(trim + 0.5*pit + 0.05*pa, -1, 1)   # 升降舵 = trim + (-0.05)*(-10*pit - pa)
da = np.clip(rol, -1, 1)                        # 副翼直通

m = (agl > 30) & (ias > 40) & (np.abs(pr) < 300) & (np.abs(rr) < 600) & (np.abs(yr) < 300)
tg = np.arange(t[m][0], t[m][-1], 0.1)
pa_g = np.interp(tg, t[m], pa[m]); de_g = np.interp(tg, t[m], de[m])
ra_g = np.interp(tg, t[m], ra[m]); da_g = np.interp(tg, t[m], da[m])
p_g  = np.interp(tg, t[m], rr[m]); v_g  = np.interp(tg, t[m], ias[m])
th_g = np.interp(tg, t[m], thr[m]); ag_g = np.interp(tg, t[m], agl[m])

def smooth(x, w=5):
    k = np.ones(w)/w
    return np.convolve(x, k, mode='same')
pa_s, ra_s, p_s, v_s, de_s, da_s, th_s, ag_s = map(smooth, (pa_g, ra_g, p_g, v_g, de_g, da_g, th_g, ag_g))
edge = np.r_[np.arange(3), np.arange(len(tg)-3, len(tg))]
keep = np.ones(len(tg), bool); keep[edge] = False
mask = keep & (ag_s > 25)
H = 0.1

# ---- 俯仰：θ̈ = -2ζωn·θ̇ - ωn²(θ-θ0) + K·δe ----
def sim_pitch(p):
    wn, z, K, th0 = p
    th, v = float(pa_s[0]), 0.0
    out = np.empty(len(pa_s))
    for i in range(len(pa_s)):
        v += (-2*z*wn*v - wn*wn*(th - th0) + K*de_s[i])*H
        th += v*H
        out[i] = th
    return out
def res_pitch(p): return (sim_pitch(p) - pa_s)[mask]
best = None
for g in ((3,0.5,-80),(6,0.7,-200),(1.5,0.4,-30),(4.5,1.2,-150)):
    try:
        r = least_squares(res_pitch, [g[0],g[1],g[2],float(pa_s[mask].mean())],
                          bounds=([0.3,0.05,-800,-30],[15,3,800,30]))
        if best is None or r.cost < best.cost: best = r
    except Exception: pass
wn, z, K_pitch, th0 = best.x
print('俯仰: wn=%.2f rad/s (%.2f Hz)  zeta=%.2f  K=%.0f deg/s2/unit  th0=%.1f  RMSE=%.2f deg' % (
    wn, wn/2/math.pi, z, K_pitch, th0, math.sqrt(np.mean(res_pitch(best.x)**2))))

# ---- 滚转：ṗ = (Kp·δa - p)/Tr ----
def sim_roll(p):
    Tr, Kp = p
    q = 0.0
    out = np.empty(len(p_s))
    for i in range(len(p_s)):
        q += ((Kp*da_s[i] - q)/max(Tr, 0.01))*H
        out[i] = q
    return out
def res_roll(p): return (sim_roll(p) - p_s)[mask]
r = least_squares(res_roll, [0.25, 400], bounds=([0.02, 20], [3, 2000]))
Tr, Kp_roll = r.x
print('滚转: Tr=%.3f s  Kp=%.0f deg/s/unit  RMSE=%.0f deg/s  |p|p99=%.0f max=%.0f' % (
    Tr, Kp_roll, math.sqrt(np.mean(res_roll(r.x)**2)),
    np.percentile(np.abs(p_s[mask]), 99), np.max(np.abs(p_s[mask]))))

# ---- 能量：V̇ = c0 + c1·thr + c2·V + c3·V² ----
def sim_energy(cc):
    V = float(v_s[0])
    out = np.empty(len(v_s))
    for i in range(len(v_s)):
        V = max(5.0, V + (cc[0] + cc[1]*th_s[i] + cc[2]*V + cc[3]*V*V)*H)
        out[i] = V
    return out
def res_energy(cc): return (sim_energy(cc) - v_s)[mask]
ce = least_squares(res_energy, [0.0, 4.0, -0.01, -1e-5],
                   bounds=([-5, 0.5, -0.2, -0.002], [5, 15, 0.2, 1e-4])).x
print('能量: Vdot = %.2f + %.2f*thr %+.4f*V %+.6f*V2  RMSE=%.1f m/s' % (
    ce[0], ce[1], ce[2], ce[3], math.sqrt(np.mean(res_energy(ce)**2))))
disc = ce[2]**2 - 4*ce[3]*(ce[0]+ce[1])
if disc > 0 and ce[3] < 0:
    roots = sorted([(-ce[2] + math.sqrt(disc))/(2*ce[3]), (-ce[2] - math.sqrt(disc))/(2*ce[3])])
    print('  预测平飞极速(thr=1): %.0f m/s' % roots[1])

# ---- 舵量权限曲线 ----
bins = np.arange(40, 340, 30)
ias_r, pa_r, p_r = ias[m], pa[m], rr[m]
print('IAS箱 | |pa|p95 | |rollrate|p95')
for lo in bins:
    sel = (ias_r >= lo) & (ias_r < lo+30) & (np.abs(pa_r) < 60)
    if sel.sum() > 200:
        print(' %3d+ | %5.1f | %6.0f' % (lo, np.percentile(np.abs(pa_r[sel]), 95),
                                         np.percentile(np.abs(p_r[sel]), 95)))

# ---- 图 ----
fig, axes = plt.subplots(2, 2, figsize=(14, 8.5))
fig.suptitle('TESTfighter 数字孪生辨识（telemetry20, 34 min 手动机动, 输出误差法）', fontsize=13)
ax = axes[0][0]
sim = sim_pitch(best.x)
ax.plot(tg[mask], pa_s[mask], lw=0.5, label='theta 实测')
ax.plot(tg[mask], sim[mask], lw=0.6, alpha=0.7, label='模型仿真')
ax.set_xlim(0, 200); ax.legend(fontsize=8); ax.set_title('俯仰双通道对比（前 200 s）'); ax.grid(alpha=0.3)
ax = axes[0][1]
sr = sim_roll(r.x)
ax.plot(tg[mask], p_s[mask], lw=0.5, alpha=0.6, label='RollRate 实测')
ax.plot(tg[mask], sr[mask], lw=0.7, alpha=0.8, label='一阶模型')
ax.set_xlim(0, 200); ax.legend(fontsize=8); ax.set_title('滚转响应（前 200 s）'); ax.grid(alpha=0.3)
ax = axes[1][0]
ax.scatter(v_s[mask], np.abs(p_s[mask]), s=1, alpha=0.15, c='purple', label='|p|')
ax.scatter(v_s[mask], np.abs(pa_s[mask])*10, s=1, alpha=0.15, c='brown', label='|theta|x10')
ax.set_xlabel('IAS (m/s)'); ax.set_ylabel('deg/s | deg x10')
ax.set_title('权限 vs 空速'); ax.legend(fontsize=8); ax.grid(alpha=0.3)
ax = axes[1][1]
se = sim_energy(ce)
ax.plot(tg[mask], v_s[mask], lw=0.8, label='IAS 实测')
ax.plot(tg[mask], se[mask], lw=0.8, alpha=0.7, color='red', label='能量模型')
ax.set_xlim(0, 600); ax.set_xlabel('t (s)'); ax.set_ylabel('IAS (m/s)')
ax.set_title('能量模型跟踪（前 600 s）'); ax.legend(fontsize=8); ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(FIGS, 'fighter-id.png'), dpi=110)
print('saved fighter-id.png')
