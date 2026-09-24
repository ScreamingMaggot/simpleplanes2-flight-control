# v15 接敌局离线重建：POS 流配对目标 → 复刻 EPS/VPS/CHI/ECX/BANK/TRV → 对照实际姿态
import io, os, math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False
_S = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(_S, '..', 'figures')
LOG = os.path.expanduser(r"~\AppData\LocalLow\Jundroo\SimplePlanes 2\Player.log")
import sys
UCID = int(sys.argv[1]) if len(sys.argv) > 1 else 97519
TCID_FIX = int(sys.argv[2]) if len(sys.argv) > 2 else None

tel, pos, seek = {}, {}, []
with io.open(LOG, encoding='utf-8', errors='ignore') as f:
    for ln in f:
        ln = ln.strip()
        if ln.startswith('TEL,'):
            p = ln.split(',')
            try:
                v = [float(x) for x in p[1:23]]
            except ValueError:
                continue
            tel.setdefault(int(v[0]), []).append(v[1:])
        elif ln.startswith('POS,'):
            p = ln.split(',')
            try:
                cid, t, lat, lon, alt = int(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5])
            except (ValueError, IndexError):
                continue
            pos.setdefault(cid, []).append((t, lat, lon, alt))
        elif ln.startswith('SEEK,'):
            p = ln.split(',')
            try:
                seek.append((int(p[1]), float(p[2]), int(float(p[3])), float(p[4]), p[8] if len(p) > 8 else '?'))
            except (ValueError, IndexError):
                pass
U_all = sorted(tel[UCID])
# 按时间回退切局（多局共享关卡时钟，同 cid 会跨局混流）；取锁定行最多的局
runs, cur = [], [U_all[0]]
for r in U_all[1:]:
    if r[0] - cur[-1][0] > 30:
        runs.append(cur); cur = [r]
    else:
        cur.append(r)
runs.append(cur)
locks_all = [x for x in seek if x[0] == UCID and x[2] == 1]
def score(run):
    a, b = run[0][0], run[-1][0]
    return (sum(1 for x in locks_all if a - 1 <= x[1] <= b + 1), len(run))
U = np.array(max(runs, key=score))
t_run = (U[0, 0] - 1, U[-1, 0] + 1)
t = U[:, 0]
hr, ra, pa, aoa, ias, gf = U[:, 8], U[:, 9], U[:, 5], U[:, 11], U[:, 3], U[:, 13]
print('user TEL %d rows, %.0f..%.0f s' % (len(U), t[0], t[-1]))
SU = np.array(sorted([r for r in pos[UCID] if t_run[0] <= r[0] <= t_run[1]]))
Pu = np.c_[np.interp(t, SU[:, 0], SU[:, 1]), np.interp(t, SU[:, 0], SU[:, 2]), np.interp(t, SU[:, 0], SU[:, 3])]  # N,E,U

# 锁定段 + D + 目标名
sk = [r for r in seek if r[0] == UCID and r[2] == 1]
st = np.array([r[1] for r in sk]); sD = np.array([r[3] for r in sk])
print('lock rows %d, t %.0f..%.0f, D %.0f..%.0f' % (len(sk), st.min(), st.max(), sD.min(), sD.max()) if sk else 'NO LOCK')

# 配对：哪个 cid 是 Guardian——与用户位置的距离≈D 者胜
best = None
for cid, pl in pos.items():
    if cid == UCID: continue
    P = np.array(sorted(pl))
    dN = np.interp(st, P[:, 0], P[:, 1]) - np.interp(st, SU[:, 0], SU[:, 1])
    dE = np.interp(st, P[:, 0], P[:, 2]) - np.interp(st, SU[:, 0], SU[:, 2])
    dU_ = np.interp(st, P[:, 0], P[:, 3]) - np.interp(st, SU[:, 0], SU[:, 3])
    dd = np.sqrt(dN**2 + dE**2 + dU_**2)
    err = np.median(np.abs(dd - sD))
    if best is None or err < best[1]:
        best = (cid, err)
TCID = TCID_FIX if TCID_FIX else best[0]
print('target cid=%d (median |dist-D|=%.0f m)' % (TCID, best[1]))
P = np.array(sorted(pos[TCID]))
dN = np.interp(t, P[:, 0], P[:, 1]) - Pu[:, 0]
dE = np.interp(t, P[:, 0], P[:, 2]) - Pu[:, 1]
dU_ = np.interp(t, P[:, 0], P[:, 3]) - Pu[:, 2]
horiz = np.sqrt(dN**2 + dE**2)
D3 = np.sqrt(horiz**2 + dU_**2)
brg = (np.degrees(np.arctan2(dE, dN))) % 360
EPS = (brg - hr + 180) % 360 - 180          # 目标在右=+
ELEV = np.degrees(np.arctan2(dU_, horiz))   # 目标高=+
VPS = ELEV + aoa - pa
LOS_R = EPS * 0  # 数值微分近似
eps_rate = np.gradient(EPS, t); eps_rate = (eps_rate + 180) % 360 - 180
hdg_rate = np.gradient(hr, t); hdg_rate = (hdg_rate + 180) % 360 - 180
LOS_R = np.clip(eps_rate + np.clip(hdg_rate, -30, 30), -25, 25)
CHI = np.degrees(np.arctan2(EPS, VPS))
ECX = np.where(VPS >= 0, CHI, np.where(CHI > 0, CHI - 180, CHI + 180))
TURN = (np.abs(EPS) > 20) & (D3 > 5000)
BANK = np.where(TURN, np.clip(2.4*EPS + 10*LOS_R, -85, 85), np.clip(ECX + 1.5*LOS_R, -85, 85))
TRV = (np.abs(EPS) < 2) & (D3 < 2500)
FIREW = TRV & (D3 < 2000) & (np.abs(VPS) < 0.5)

lk = np.zeros(len(t), bool)
if len(sk):
    lk = (np.abs(t[:, None] - st[None, :]) < 0.4).any(axis=1)
def q(x): return 'p95=%.1f med=%.1f' % (np.percentile(np.abs(x[lk]), 95), np.median(x[lk])) if lk.any() else 'n/a'
print('锁定段（Lua lock ±0.4s，共 %.0f s）: EPS %s  VPS %s  |ra+BANK| med=%.1f°' % (
    np.sum(lk)*np.median(np.diff(t)), q(EPS), q(VPS), np.median(np.abs((ra + BANK)[lk]))))
print('VPS 过零: %d 次;  TRV真 %.1fs;  开火窗 %.1fs;  最近 %.0f m @t=%.0f' % (
    int(np.sum(np.diff(np.sign(VPS[lk])) != 0)), np.sum(TRV & lk)*np.median(np.diff(t)),
    np.sum(FIREW & lk)*np.median(np.diff(t)),
    D3[lk].min() if lk.any() else -1, t[lk][np.argmin(D3[lk])] if lk.any() else -1))

fig, ax = plt.subplots(5, 1, figsize=(14, 14), sharex=True)
fig.suptitle('v15 中轴线索敌重建（cid=%d 追 %d，全程离线由 POS/TEL 复算）' % (UCID, TCID), fontsize=13)
ax[0].plot(t, EPS, lw=.7, label='EPS 方位差'); ax[0].plot(t, np.where(TRV, EPS, np.nan), 'r.', ms=2, label='TRV内')
ax[0].plot(t, np.where(TURN, EPS, np.nan), 'g.', ms=2, label='TURN内'); ax[0].axhline(0, lw=.5, c='k'); ax[0].legend(fontsize=8); ax[0].grid(alpha=.3); ax[0].set_ylabel('EPS(deg)')
ax[1].plot(t, VPS, lw=.7, c='brown'); ax[1].plot(t, np.where(FIREW, VPS, np.nan), 'go', ms=3, label='开火窗 VPS 过零')
ax[1].axhline(0, lw=.5, c='k'); ax[1].axhline(1, lw=.5, ls='--', c='gray', label='挂点1°'); ax[1].legend(fontsize=8); ax[1].grid(alpha=.3); ax[1].set_ylabel('VPS(deg)')
ax[2].plot(t, BANK, lw=.8, c='blue', label='BANK 指令(RollAngle 取负)'); ax[2].plot(t, ra, lw=.8, c='orange', label='实际 RollAngle')
ax[2].grid(alpha=.3); ax[2].legend(fontsize=8); ax[2].set_ylabel('滚转(deg)')
ax[3].plot(t, pa, lw=.8, c='green', label='PitchAngle'); ax[3].plot(t, ELEV + aoa, lw=.6, c='red', label='目标仰角+AoA'); ax[3].legend(fontsize=8); ax[3].grid(alpha=.3); ax[3].set_ylabel('俯仰(deg)')
ax[4].plot(t, D3/1000, lw=.8, c='purple'); ax[4].plot(t, ias, lw=.6, c='gray'); ax[4].plot(t, gf, lw=.6, c='teal', label='G')
ax[4].legend(fontsize=8, labels=['距离km','IAS','G']); ax[4].grid(alpha=.3); ax[4].set_xlabel('t(s)'); ax[4].set_ylabel('km / m·s⁻¹ / G')
plt.tight_layout(); fn = os.path.join(FIGS, 'v15-axial-report.png'); plt.savefig(fn, dpi=110)
print('saved', fn)
