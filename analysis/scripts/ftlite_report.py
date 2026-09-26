#!/usr/bin/env python3
"""FT-Lite 架次判卷器（SC-5）。用法: python ftlite_report.py [日志路径]
默认读游戏 Player.log。按 cid 分流出每架机的每一局，与 Lua 探杆 ALARM 行（v0.11 同镜）
对齐，输出 T2~T4 判据表 + 手动/自动归因（轴列活动率）。"""
import io, os, sys, math, bisect, collections

LOG = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    r"~\AppData\LocalLow\Jundroo\SimplePlanes 2\Player.log")
H = ["cid","t","alt","agl","ias","gs","pa","pr","yr","hr","ra","rr","aoa","aos","gf","vg",
     "fuel","thr","trim","pit","rol","yaw","flp"]
RWY_ELEV = {"Cochran": 3, "Shepard": 11, "Bannock": 5, "Kunimitsu": 10}
SLOPE = 0.0564                      # 3.23° 道线


def read(log):
    rows, alarm, lgear = [], collections.defaultdict(list), []
    for line in io.open(log, encoding="utf-8", errors="ignore"):
        i = line.find("TEL,")
        if i >= 0:
            p = line[i:].strip().split(",")[1:]
            if len(p) == len(H):
                rows.append(dict(zip(H, [float(x) for x in p])))
            continue
        j = line.find("ALARM,")
        if j >= 0:
            p = line[j:].strip().split(",")[1:]
            # cid,t,gear,corridor,g,SD,LT
            alarm[int(float(p[0]))].append((float(p[1]), float(p[2]), p[3], float(p[5]), float(p[6])))
            continue
        if line.startswith("LGEAR"):
            lgear.append(line.strip()[:70])
    return rows, alarm, lgear


def runs_of(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[int(r["cid"])].append(r)
    out = {}
    for cid, v in sorted(by.items()):
        rs = [[]]
        for x in v:
            if rs[-1] and x["t"] < rs[-1][-1]["t"]:
                rs.append([])
            rs[-1].append(x)
        out[cid] = rs
    return out


def report(cid, r, A):
    ts = [a[0] for a in A]
    def near(t):
        k = min(len(A) - 1, max(0, bisect.bisect_left(ts, t)))
        return A[k]
    fly = [x for x in r if x["agl"] > 5]
    if not fly:
        return
    ax = lambda c: sum(1 for x in r if abs(x[c]) > 0.02) / max(len(r), 1)
    hands = 100 * max(ax("rol"), ax("pit"))          # 横滚/俯仰任一活动=手动段占比
    # 走廊质量：SD 有效段内的 LT 包络
    seg = [(x, near(x["t"])) for x in fly]
    est = [e for e in seg if e[1][3] > -1e5]
    lt = [abs(a[4]) for _, a in est if 300 < a[3] <= 4000]   # 终段（截获后）才作判据
    # 纵向：高线误差能不能自己吃掉（道线锚=场高+斜率·SD）
    err0 = err_end = None
    for x, a in est:
        el = RWY_ELEV.get(a[2].split()[0], 5)
        e = x["alt"] - (el + SLOPE * max(a[3], 0))
        if err0 is None:
            err0 = e
        if 1500 < a[3] < 3000:
            err_end = e
    ias_min = min(x["ias"] for x in fly)
    td = [x for x in r if x["agl"] <= 2]
    print(" cid %d  局时长 %.0f s  起降=%s  末 agl %.0f" % (
        cid, r[-1]["t"], "接地" if td else "未接地", r[-1]["agl"]))
    print("   归因：横滚/俯仰轴活动率 %.0f%%（≈0%% = 全程松杆，律独立飞）" % hands)
    # 按离头距离分桶看收敛（全飞行段的 |LT| 极值来自截获前，不能当判据）
    BUCK = [(8000, 15000), (4000, 8000), (2000, 4000), (1000, 2000), (300, 1000), (-200, 300)]
    print("     SD 区间      n   |LT|中位  |LT|最大   高线误差(均值)  IAS")
    for lo, hi in BUCK:
        s = [(abs(a[4]), x["alt"] - (RWY_ELEV.get(a[2].split()[0], 5) + SLOPE * max(a[3], 0)), x["ias"])
             for x, a in est if lo < a[3] <= hi]
        if not s:
            continue
        m = sorted(v[0] for v in s)[len(s) // 2]
        print("   %6d~%-6d %4d  %7.0f  %8.0f   %+9.0f   %4.0f" % (
            lo, hi, len(s), m, max(v[0] for v in s), sum(v[1] for v in s) / len(s),
            sum(v[2] for v in s) / len(s)))
    if lt:
        print("   横向：|LT| 中位 %.0f m · p95 %.0f m · 最大 %.0f m  → 判据 ±100 m：%s" % (
            sorted(lt)[len(lt)//2], sorted(lt)[int(len(lt)*.95)], max(lt),
            "PASS" if max(lt) < 100 else ("接近" if max(lt) < 200 else "FAIL")))
    if err0 is not None:
        print("   纵向：高线误差 %.0f m → %.0f m（SD 1.5~3 km 处）  IAS 最低 %.0f m/s  → 能量：%s" % (
            err0, err_end if err_end is not None else float("nan"), ias_min,
            "PASS" if ias_min > 76 else "偏慢"))
    if td:
        k = r.index(td[0])
        w = [x for x in r[k:] if x["t"] <= td[0]["t"] + 5.0]
        if len(w) > 2:
            a = (w[0]["ias"] - w[-1]["ias"]) / (w[-1]["t"] - w[0]["t"])
            print("   接地 t=%.0f IAS=%.0f → 5 s 内平均减速 %.1f m/s²（轮上+刹车≈2~4，机腹摩擦≈8~10）"
                  % (td[0]["t"], w[0]["ias"], a / 9.81))


if __name__ == "__main__":
    rows, alarm, lgear = read(LOG)
    outs = runs_of(rows)
    print("== FT-Lite 判卷：%s" % os.path.basename(LOG))
    for cid, rs in outs.items():
        A = sorted(alarm.get(cid, []))
        for r in rs:
            report(cid, r, A)
    if lgear:
        print(" 起落架诊断行：")
        for l in lgear[:6]:
            print("   ", l)
