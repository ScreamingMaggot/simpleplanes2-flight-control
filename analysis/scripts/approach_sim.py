# -*- coding: utf-8 -*-
"""M3+M4 合并 · 全流程离线仿真（先把"任意位置按7→靠场→消高→落"跑通，再谈上机）。

与之前 sim 的关键区别：**识别用点目标终端区（最近场在 R_term 内即认），不再要求已在中线走廊里**
——这正是"从远处/斜着按 7 却 O0 飞走"的根。横向分段：
  ENROUTE：缓飞朝 FAF（限转弯率=60°坡），把机头指向场；
  ORBIT  ：太高(excess>WIN)时在场上空跑右向下降跑道航线（IN/T1/OUT/T2，R=实测半径）消高；
  FINAL  ：追 3° 中线到入口。

坐标：跑道在原点，inbound=ψ180（沿 -x 飞向入口）；alt=高于场高；v 由"自动油门"松弛到 VAPP。
仅运动学（不含 FT 姿态/舵闭环）—— 结论=几何/时间线可行，非"飞控已对"。
"""
import math

VAPP   = 55.0
R_TERM = 12000.0      # 终端区识别半径（点目标：到入口距离）
FAF    = 4885.0
LEG    = 3200.0
X_FAR  = FAF + LEG
WIN    = 100.0
R      = 200.0        # 实测最小半径
PHI_MAX= 60.0
DT     = 0.1
G      = 9.81


def wrap(d): return (d + 180.0) % 360.0 - 180.0


def run(name, x0, y0, alt0, psi0, v0, tmax=1800.0):
    x, y, alt, psi, v = x0, y0, alt0, psi0, v0
    st = "ENROUTE"; t = 0.0; laps = 0.0; ground_ok = True; log = []
    a = 0.0
    while t < tmax:
        d = math.hypot(x, y)
        # 识别：d<R_TERM 即认（无走廊要求）
        rcap = G * math.tan(math.radians(PHI_MAX)) / max(v, 10.0)   # 最大转弯角速率(deg/s)
        omega = math.degrees(rcap)
        v = VAPP + (v - VAPP) * math.exp(-DT / 8.0)                  # 自动油门把速度收到 VAPP
        line = 0.0524 * max(x, 0.0)
        sinkMax = max(3.0, min(7.0, v * 0.12))
        gmax = math.atan(sinkMax / v)
        excess = alt - x * math.tan(gmax)
        # 状态
        if st == "ENROUTE":
            if x <= FAF + 200:      # 到 FAF 区
                st = "IN" if excess > WIN else "FINAL"
        elif st == "IN":
            if x <= FAF:
                st = "FINAL" if alt <= line + WIN else "T1"
        elif st == "T1":
            if abs(wrap(psi - 0.0)) < 12: st = "OUT"
        elif st == "OUT":
            if x >= X_FAR: st = "T2"
        elif st == "T2":
            if abs(wrap(psi - 180.0)) < 12: st = "IN"; laps += 1.0
        # 航向
        if st == "ENROUTE":
            des = math.degrees(math.atan2(0 - y, FAF - x)); psi += max(-omega*DT, min(omega*DT, wrap(des - psi)))
        elif st == "IN":
            des = 180 + max(-20, min(20, y * 2)); psi += max(-omega*DT, min(omega*DT, wrap(des - psi)))
        elif st == "OUT":
            des = 0 + max(-20, min(20, (y - (-2*R)) * -2)); psi += max(-omega*DT, min(omega*DT, wrap(des - psi)))
        elif st in ("T1", "T2"):
            psi -= omega * DT
        else:  # FINAL
            des = math.degrees(math.atan2(0 - y, 0 - x)); psi += max(-omega*DT, min(omega*DT, wrap(des - psi)))
        x += v * math.cos(math.radians(psi)) * DT
        y += v * math.sin(math.radians(psi)) * DT
        # 垂直
        if st in ("T1", "OUT", "T2"):
            alt = max(alt - sinkMax * DT, line)
        else:
            tgt = line
            vsc = max(-sinkMax, min(sinkMax, 0.25 * (tgt - alt)))
            alt += vsc * DT
        if alt < -1: ground_ok = False; break
        if x < 0: break
        t += DT
        if t % 20 < DT:
            log.append((round(t), st, round(x), round(y), round(alt), round(psi), round(v)))
    return dict(name=name, st=st, laps=laps, t=t, x=x, y=y, alt=alt, ground=ground_ok, log=log)


def show(r):
    print("== %s == 末态=%s 圈=%.1f 用时=%.0fs  x=%.0f y=%.0f alt=%.0f%s"
          % (r["name"], r["st"], r["laps"], r["t"], r["x"], r["y"], r["alt"],
             "" if r["ground"] else "  **触地**"))
    for row in r["log"][:16]:
        print("   t=%4d %-7s x=%6d y=%5d alt=%5d psi=%5d v=%3d" % row)


# 极端工况：出生 1.8 km 高 / 300 m/s / 离场 ~9 km / 斜 3 km
show(run("极端(1820m/300m/s/9km斜)", x0=9000, y0=3000, alt0=1820, psi0=210, v0=300))
print()
# 正常：压 3° 线
show(run("正常(压3°线)", x0=8000, y0=0, alt0=419, psi0=180, v0=60))
