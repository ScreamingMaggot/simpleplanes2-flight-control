#!/usr/bin/env python3
"""遥测首期分析：全局长度图 + 短周期事件自动检测与指标。"""
import csv, io, math, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import os
_S = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_S,"..","data","telemetry.csv")
t, cols = [], {k: [] for k in ["alt","agl","ias","pa","pr","yr","hr","ra","rr","aoa","gf","vg","thr","trim","pit","rol","yaw"]}
with io.open(SRC, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        t.append(float(row["t"]))
        for k in cols: cols[k].append(float(row[k]))
N = len(t)

fig, axes = plt.subplots(5, 1, figsize=(14, 15), sharex=True)
fig.suptitle("TESTaircraft telemetry - first session (MFD Lua -> Player.log)")
axes[0].plot(t, cols["pa"], label="PitchAngle deg"); axes[0].plot(t, cols["ra"], label="RollAngle deg"); axes[0].axhline(0, color="k", lw=.5)
axes[1].plot(t, cols["alt"], label="Altitude m"); axes[1].plot(t, cols["ias"], label="IAS m/s")
axes[2].plot(t, cols["pr"], label="PitchRate deg/s"); axes[2].plot(t, cols["yr"], label="YawRate deg/s")
axes[3].plot(t, cols["pit"], label="Pitch stick"); axes[3].plot(t, cols["rol"], label="Roll stick"); axes[3].plot(t, cols["yaw"], label="Yaw stick")
axes[4].plot(t, cols["thr"], label="Throttle"); axes[4].plot(t, cols["trim"], label="Trim"); axes[4].plot(t, cols["aoa"], label="AoA deg")
for a in axes: a.legend(loc="upper right", fontsize=8); a.grid(alpha=.3)
plt.tight_layout(); plt.savefig(os.path.join(_S,"..","figures","session-overview.png"), dpi=110); plt.close()

# 短周期事件检测：pitch 杆离开中位>0.3 后回中，看 pa 响应
events = []
i = 0
while i < N - 80:
    if abs(cols["pit"][i]) > 0.3:
        j = i
        while j < N and abs(cols["pit"][j]) > 0.3: j += 1
        k = j
        while k < N and abs(cols["pit"][k]) <= 0.3 and k - j < 60: k += 1
        if k - j >= 40 and i > 10:
            seg_pa = cols["pa"][j:k+1]; base = cols["pa"][j]
            peak = max(seg_pa, key=abs) if False else (max(seg_pa) if base >= 0 else min(seg_pa))
            # 发散/收敛判据：末段幅值 vs 峰值过冲
            settle = seg_pa[-10:]
            amp_peak = abs(peak - base); amp_end = abs(sum(settle)/len(settle) - base)
            events.append((t[i], t[j], round(amp_peak, 2), round(amp_end, 2), "CONV" if amp_end < 0.6*amp_peak else "DIVERG?"))
        i = j + 60
    else:
        i += 1
print(f"samples={N} span={t[-1]-t[0]:.0f}s")
print("pitch-step events (t_start, t_release, overshoot_deg, residual_deg, verdict):")
for e in events[:12]: print("  ", e)
print("saved session-overview.png")
