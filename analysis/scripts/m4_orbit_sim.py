# -*- coding: utf-8 -*-
"""M4 消高 —— 离线轨迹仿真 v3：**沿中线延长线的下降跑道航线（racetrack）**，两端 180° 切线弧。
先演算后建律。R = 飞行员实飞实测最小转弯半径（≈150–200 m @ ≤64°坡）→ 取 R_MIN。

坐标：数学系。x=到入口沿轴距离(m, 入口 0, 正=入口在前)；y=横偏(m, 正=左)；psi 航向(math CCW, deg)，
  inbound=180°、outbound=0°；右转=psi 减。vel=(gs cosψ, gs sinψ)。
垂直：sinkMax=clamp(gs*0.12,3,7)；3°线=0.0524·x；excess=alt−x·tan(atan(sinkMax/gs))。

航线（右转）：
  IN : 沿 y=0 向 -x 飞(inbound)，压 3°线；到 x≤X_HOLD 时：够低→FINAL；否则→T1。
  T1 : 右转 180°(半径 R) 到 outbound(psi≈0)，同时按 sinkMax 掉高 → OUT。位移到 y≈-2R。
  OUT: 沿 y=-2R 向 +x 飞(outbound)，保高(缓降)；到 x≥X_FAR → T2。
  T2 : 右转 180° 回 inbound → IN。
  FINAL: 沿中线追 3° 线到入口。
"""
import math

FAF    = 256.0 / 0.0524          # ≈4885 m（X_HOLD = FAF）
LEG    = 3000.0                  # outbound 腿长(m)
X_FAR  = FAF + LEG
WIN    = 100.0
DT     = 0.1
R      = 200.0                   # ← 实飞实测最小半径（5%~中位≈145~200）


def wrap(d):
    return (d + 180.0) % 360.0 - 180.0


def hold_y(psi, x, y, ytar, rate, dt):
    """把 y 收到 ytar：目标航向 = inbound/outbound 方向 + 小修正。"""
    base = 180.0 if ytar == 0.0 else 0.0      # IN 腿 ytar=0；OUT 腿用 outbound
    des = base + max(-20, min(20, (y - ytar) * (2.0 if base == 180.0 else -2.0)))
    d = wrap(des - psi)
    return psi + max(-rate * dt, min(rate * dt, d))


def run(name, x0, y0, alt0, psi0, gs, tmax=1200.0):
    x, y, alt, psi = x0, y0, alt0, psi0
    st = "IN"; t = 0.0; laps = 0.0; ground = True; log = []
    rate = gs / R * 180.0 / math.pi
    while t < tmax:
        sinkMax = max(3.0, min(7.0, gs * 0.12))
        line = 0.0524 * max(x, 0.0)
        excess = alt - x * math.tan(math.atan(sinkMax / gs))
        # 状态转移
        if st == "IN":
            if x <= FAF:
                st = "FINAL" if alt <= line + WIN else "T1"
        elif st == "T1":
            if abs(wrap(psi - 0.0)) < 12.0: st = "OUT"
        elif st == "OUT":
            if x >= X_FAR: st = "T2"
        elif st == "T2":
            if abs(wrap(psi - 180.0)) < 12.0: st = "IN"; laps += 1.0
        # 航向指令
        if st == "IN":
            psi = hold_y(psi, x, y, 0.0, rate, DT)
        elif st == "OUT":
            psi = hold_y(psi, x, y, -2 * R, rate, DT)
        elif st in ("T1", "T2"):
            psi -= rate * DT                       # 右转（切线弧）
        else:  # FINAL
            des = math.degrees(math.atan2(0 - y, 0 - x))
            d = wrap(des - psi); psi += max(-rate * dt if False else -60 * DT, min(60 * DT, d))
        x += gs * math.cos(math.radians(psi)) * DT
        y += gs * math.sin(math.radians(psi)) * DT
        # 垂直
        if st == "FINAL":
            vsc = max(-sinkMax, min(sinkMax, 0.25 * (line - alt)))
            alt += vsc * DT
        elif st == "IN":
            vsc = max(-sinkMax, min(sinkMax, 0.25 * (line - alt)))   # 压 3°线
            alt += vsc * DT
        else:                                   # T1/OUT/T2：按 sinkMax 消高，不钻地
            alt = max(alt - sinkMax * DT, line)
        if alt < -1.0: ground = False; break
        if x < 0: break
        t += DT
        if t % 20 < DT:
            log.append((round(t), st, round(x), round(y), round(alt), round(psi)))
    return dict(name=name, st=st, laps=laps, t=t, x=x, y=y, alt=alt, ground=ground, log=log)


def show(r):
    print("== %s == 末态=%s 圈=%.1f 用时=%.0fs  x=%.0f y=%.0f alt=%.0f%s"
          % (r["name"], r["st"], r["laps"], r["t"], r["x"], r["y"], r["alt"],
             "" if r["ground"] else "  **触地**"))
    for row in r["log"][:14]:
        print("   t=%4d %-6s x=%5d y=%5d alt=%5d psi=%4d" % row)


show(run("A 正常(压3°线)", x0=8000, y0=0, alt0=419, psi0=180, gs=60))
print()
show(run("B 过高1500", x0=8000, y0=0, alt0=1500, psi0=180, gs=60))
