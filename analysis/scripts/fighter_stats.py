# TESTfighter 参数档案 v2：极值统计法（舵量权限/能量/失速）+ 闭环自洽校验
import os, csv, math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False
_S = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_S, '..', 'data')
FIGS = os.path.join(_S, '..', 'figures')

def load(name):
    rows = list(csv.DictReader(open(os.path.join(DATA, name))))
    def col(k): return np.array([float(r[k]) for r in rows])
    return {k: col(k) for k in ('t','alt','agl','ias','gs','pa','pr','yr','hr','ra','rr','aoa','aos','gf','vg','fuel','thr','trim','pit','rol','yaw')}

d = load('telemetry20.csv')
ok = (d['agl'] > 30) & (d['ias'] > 20) & (np.abs(d['pr']) < 300) & (np.abs(d['rr']) < 600)
V, PA, RR, RA, IAS, THR, AOA, VG, AGL = (d['ias'][ok], d['pa'][ok], d['rr'][ok], d['ra'][ok],
                                          d['ias'][ok], d['thr'][ok], d['aoa'][ok], d['vg'][ok], d['agl'][ok])

print('== 权限统计（telemetry20, 34min）==')
bins = np.arange(60, 340, 40)
print('IAS箱(m/s)  n     |pa|p99   |p|p99   |G|p95')
for lo in bins:
    s = (V >= lo) & (V < lo+40) & (np.abs(PA) < 70)
    if s.sum() > 150:
        print(' %3d-%3d  %5d   %6.1f   %6.0f   %5.1f' % (lo, lo+40, s.sum(),
              np.percentile(np.abs(PA[s]), 99), np.percentile(np.abs(RR[s]), 99),
              np.percentile(np.abs(d['gf'][ok][s]), 95)))

# 稳态滚转率：|p| 在 bin 内的 p90（近稳态判据：|rr变化|小 用持续高值近似）
print('\n== 稳态滚转能力（|p|>0.8*p99 的持续样本均值）==')
for lo in bins:
    s = (V >= lo) & (V < lo+40)
    if s.sum() > 150:
        p99 = np.percentile(np.abs(RR[s]), 99)
        sus = s & (np.abs(RR) > 0.8*p99)
        if sus.sum() > 30:
            print(' %3d-%3d m/s: 持续|p| ~ %.0f deg/s (n=%d)' % (lo, lo+40, np.mean(np.abs(RR[sus])), sus.sum()))

# 失速：最低平飞速度（sink>-2 且 pa>0 的最低 IAS 与对应 AoA）
level = (VG > -2) & (PA > 5) & (AGL > 60)
if level.sum():
    i = np.argmin(np.where(level, IAS, 1e9))
    print('\n== 失速边界 ==\n最低平飞 IAS ~ %.0f m/s (pa=%.0f aoa=%.0f)' % (IAS[level].min(), PA[level][IAS[level]==IAS[level].min()][0], AOA[level][IAS[level]==IAS[level].min()][0]))
print('AoA p99=%.0f max=%.0f（>该值即失去升力）' % (np.percentile(AOA[np.abs(AOA)<30], 99), np.abs(AOA[np.abs(AOA)<30]).max()))

# 能量爬升：thr>0.9 时的爬升率分布
climb = (THR > 0.9) & (np.abs(VG) < 120)
print('\n== 能量（thr>0.9）==')
print('爬升率 VG p90=%.1f p99=%.1f m/s | 对应 IAS 中位=%.0f' % (
    np.percentile(VG[climb], 90), np.percentile(VG[climb], 99), np.median(IAS[climb])))
# 加速能力：近水平直飞 (|pa|<8, VG±10) 的 dIAS/dt
t_, v_ = d['t'][ok], IAS
acc = []
for i in range(1, len(t_)):
    dt = t_[i]-t_[i-1]
    if 0.01 < dt < 0.3 and abs(PA[i]) < 8 and abs(VG[i]) < 12:
        acc.append(((v_[i]-v_[i-1])/dt, v_[i], THR[i]))
a_hi = [a for a in acc if a[2] > 0.9]
if a_hi:
    arr = np.array(a_hi)
    print('全油门加速度按速度箱:')
    for lo in bins:
        s = (arr[:,1] >= lo) & (arr[:,1] < lo+40)
        if s.sum() > 40:
            print('  %3d-%3d m/s: %.2f m/s2 (n=%d)' % (lo, lo+40, arr[s,0].mean(), s.sum()))

# ---- 闭环自洽校验：v6.1 内环 + 识别权限，模拟阶跃响应 ----
# 俯仰简化模型：速率限幅 = 实测 (|p|权限同理推俯仰角速率)；用 |pr| p99 权限
PR = d['pr'][ok]
print('\n== 俯仰角速率权限 ==')
for lo in bins:
    s = (V >= lo) & (V < lo+40) & (np.abs(PR) < 400)
    if s.sum() > 150:
        print(' %3d-%3d m/s: |q|p99=%.0f deg/s' % (lo, lo+40, np.percentile(np.abs(PR[s]), 99)))
