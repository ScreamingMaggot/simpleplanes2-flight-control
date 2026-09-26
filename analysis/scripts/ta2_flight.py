# -*- coding: utf-8 -*-
"""一局 SC-6 试飞的案卷：从 Player.log 里挑最新那局，重建走廊选择/道线跟踪/拉平/接地/滑跑。

为什么要有这个文件：同一套问题（选了几条跑道？道线跟得住吗？拉平有没有收光？刹车出力没有？）
每次事故我都手写一遍内联脚本，写三遍就该成工具。判据口径固定，才谈得上跨局对比。

用法：
    python ta2_flight.py                # 自动挑"文件里最后出现的那局"
    python ta2_flight.py --cid 2389     # 指定机体
    python ta2_flight.py --list         # 只列最近几局
坐标口径与 ft_ta2_patch.py 逐字同规（SD=入口−本机 在跑道轴向的投影，正=入口在前；LT=正=本机偏中线左）。
"""
import io, os, sys, json, math, argparse

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.expandvars(r"%USERPROFILE%\AppData\LocalLow\Jundroo\SimplePlanes 2\Player.log")
TBL = os.path.join(HERE, "..", "data", "runway-locations.json")
K = "t alt agl ias gs pa pr yr hr ra rr aoa aos gf vg fuel thr trim pit rol yaw flp".split()
H = {n: i for i, n in enumerate(K)}


def runways():
    out = []
    for r in json.load(io.open(TBL, encoding="utf-8")):
        nm = r["name"]
        if "Helipad" in nm or "Catapult" in nm:
            continue                      # 与 load_runways() 同规
        lon, elev, lat = [float(v) for v in r["pos"].split(",")]
        out.append((nm.replace(" Airport", "").strip(), lat, lon,
                    float(r["rot"].split(",")[1]), elev))
    return out


def load():
    # POS 与 TEL 一样**按文件顺序切成"局"**再段内排序：同一 cid 跨架次时按 t 全局排序会把
    # 两局的位置交错在一起（我踩过一次：SD 在 2268/3694 之间乱跳，看着像律在抖，其实是案卷读错）。
    tel, pos, alarm = {}, {}, {}
    order = []
    for ln in io.open(LOG, encoding="utf-8", errors="replace"):
        if ln.startswith("TEL,"):
            f = ln.rstrip("\n").split(",")
            if len(f) - 2 != len(K):
                continue
            try:
                v = [float(x) for x in f[2:]]
            except ValueError:
                continue
            tel.setdefault(f[1], []).append(v)
            if not order or order[-1] != f[1]:
                order.append(f[1])
        elif ln.startswith("POS,"):
            f = ln.rstrip("\n").split(",")
            try:
                pos.setdefault(f[1], []).append((float(f[2]), float(f[3]), float(f[4]), float(f[5])))
            except (ValueError, IndexError):
                pass
        elif ln.startswith("ALARM,"):
            f = ln.rstrip("\n").split(",")
            try:
                alarm.setdefault(f[1], []).append((float(f[2]), f[3]))
            except (ValueError, IndexError):
                pass
    # **不按 t 全局排序**：同一 cid 在一个 Player.log 里会跨多个架次（时基重置），
    # 排序会把两局数据交错成假单调序列（踩过）。按文件顺序切段、段内才排序。
    return tel, pos, alarm, order


def split_runs(rows, key=0):
    """按文件顺序切段：时基回退=重新出击。段内按 t 排序。"""
    out, cur = [], []
    for r in rows:
        if cur and r[key] < cur[-1][key] - 1.0:
            out.append(cur); cur = []
        cur.append(r)
    if cur:
        out.append(cur)
    return [sorted(c, key=lambda x: x[key]) for c in out if c]


def geo(rwy, lat, lon, agl, ias, hdg):
    """逐条跑道算面板量，返回按 (真距离 DS) 排序的候选（只留 G 门内的）。"""
    rcap = max(900.0, 2 * ias * ias / 13.5)
    cands = []
    for nm, rlat, rlon, hd, el in rwy:
        h = math.radians(hd); c, s = math.cos(h), math.sin(h)
        SD = (rlat - lat) * c + (rlon - lon) * s
        LT = (lat - rlat) * s - (lon - rlon) * c
        G = ((SD > -50) or ((SD > -3500) and agl < 100)) and abs(LT) < rcap and SD < 15000
        if not G:
            continue
        BG = hd + math.degrees(math.atan2(-LT, SD))
        DS = math.hypot(SD, LT)
        cone = (SD < 0) or abs(((BG - hdg + 180) % 360) - 180) < 60
        cands.append(dict(nm=nm, SD=SD, LT=LT, DS=DS, el=el, hd=hd,
                          TLA=el + 0.0524 * max(SD, 0), cone=cone,
                          # v2.7.1 收紧后的豁免：过阈值那条要同轴（|LT|<300）才免检锥门
                          k272=(SD < 0 and abs(LT) < 300) or cone))
    return cands


def report(cid, tel, pos, runs_of_cid):
    rwy = runways()
    # POS 按同一口径切局，取与 TEL 同序号的那一段
    Pruns = split_runs(pos.get(cid, []), key=0)
    P = Pruns[min(len(runs_of_cid), len(Pruns)) - 1] if Pruns else []
    g = lambda r, k: r[H[k]]
    print("=== cid=%s  段数=%d  本局 t=%.1f..%.1f 帧=%d ===" % (
        cid, len(runs_of_cid), runs_of_cid[-1][0][0], runs_of_cid[-1][-1][0], len(runs_of_cid[-1])))
    R = runs_of_cid[-1]
    def near(t, rows, col=None):
        best = None
        for rr in rows:
            if abs(rr[0 if col is None else col] - t) < 0.9:
                return rr
        return None
    # 1) 全程概览：每 15 s 一行 + 走廊
    print("    t     agl    alt    ias     gs     pa     ra   | 选中(v2.7.2)      TLA   误差   候选数  最近入口")
    nxt = 0.0
    _sdhist = {}
    sel_hist = []
    for r in R:
        if g(r, "t") < nxt:
            continue
        nxt += 15
        p = near(g(r, "t"), P)
        if not p:
            print("%7.1f %6.1f %6.1f %6.1f %6.1f %6.1f %6.1f   | (无 POS)" % (
                g(r, "t"), g(r, "agl"), g(r, "alt"), g(r, "ias"), g(r, "gs"), g(r, "pa"), g(r, "ra")))
            continue
        cd = geo(rwy, p[1], p[2], g(r, "agl"), g(r, "ias"), g(r, "hr"))
        pool = [c for c in cd if c["k272"]] or [c for c in cd if c["SD"] < 0]
        b = min(pool, key=lambda c: c["DS"]) if pool else None
        sel_hist.append((g(r, "t"), b["nm"] if b else None))
        print("%7.1f %6.1f %6.1f %6.1f %6.1f %6.1f %6.1f   | %-16s %6.0f %+6.0f  %2d      %6.0f" % (
            g(r, "t"), g(r, "agl"), g(r, "alt"), g(r, "ias"), g(r, "gs"), g(r, "pa"), g(r, "ra"),
            b["nm"] if b else "(无走廊)", b["TLA"] if b else 0,
            (b["TLA"] - g(r, "alt")) if b else 0, len(cd),
            min([c["DS"] for c in cd]) if cd else -1))
    flips = [(a[0], a[1], b[1]) for a, b in zip(sel_hist, sel_hist[1:]) if a[1] != b[1]]
    print("  走廊切换事件：%s" % (["%.0f s: %s→%s" % f for f in flips] or "无"))
    # 2) 接地与拉平：找 alt 锁死点
    a0 = R[0][H["alt"]]
    lock = None
    for i in range(len(R) - 20):
        w = R[i:i + 20]
        if max(x[H["alt"]] for x in w) - min(x[H["alt"]] for x in w) < 0.6 and g(w[0], "agl") < 3:
            lock = w[0]; break
    print("\n--- 最后 40 s（拉平账：下沉率应随高度收光）---")
    print("    t     agl    ias     gs   |  vs实   vsLine  vsCmd(新律)  预测拉平项")
    for r in R:
        t = g(r, "t")
        if t < (lock[0] - 40 if lock else R[-1][0] - 40):
            continue
        p = near(t, P)
        cd = geo(rwy, p[1], p[2], g(r, "agl"), g(r, "ias"), g(r, "hr")) if p else []
        pool = [c for c in cd if c["k272"]] or [c for c in cd if c["SD"] < 0]
        b = min(pool, key=lambda c: c["DS"]) if pool else None
        vs = None
        for q in R:
            if abs(q[0] - t) > 1.2:
                continue
        agl = g(r, "agl")
        # vsLine 必须含前馈项，否则案卷会把"道线要求的下沉"读成 0（我差点被它骗过一次）
        ff = 0.0
        if b is not None:
            key = b["nm"]
            if key in _sdhist and t - _sdhist[key][0] > 0.3:
                ff = 0.0524 * max(-160.0, min(160.0, (b["SD"] - _sdhist[key][1]) / (t - _sdhist[key][0])))
            _sdhist[key] = (t, b["SD"])
        line = (0.25 * (min(500.0, b["TLA"]) - g(r, "alt")) + (b and ff or 0)) if b else None
        fl = -agl * min(90.0, max(20.0, g(r, "gs"))) / 300.0
        prev = [x for x in R if abs(x[0] - t) < 1.6 and x is not r]
        vsv = ((g(r, "alt") - g(prev[-1], "alt")) / (t - g(prev[-1], "t"))) if prev else 0.0
        print("%7.1f %6.1f %6.1f %6.1f   | %5.1f  %6s   %6s     %6.1f" % (
            t, agl, g(r, "ias"), g(r, "gs"), vsv,
            ("%6.1f" % line) if line is not None else "  --  ",
            ("%6.1f" % max(line, fl)) if line is not None else "  --  ", fl))
    # 3) 滑跑
    if lock:
        seg = [r for r in R if r[0] >= lock[0]]
        d = sum((seg[i][H["gs"]] + seg[i - 1][H["gs"]]) / 2 * (seg[i][0] - seg[i - 1][0])
                for i in range(1, len(seg)))
        print("\n--- 接地后（t=%.1f 起，%.0f s）---" % (lock[0], seg[-1][0] - lock[0]))
        print("  GS %.1f→%.1f m/s、位移 %.0f m、平均减速度 %.2f m/s²" % (
            seg[0][H["gs"]], seg[-1][H["gs"]], d,
            (seg[-1][H["gs"]] - seg[0][H["gs"]]) / max(seg[-1][0] - seg[0][0], 1e-6)))
        print("  杆量集合 thr=%s pit=%s rol=%s yaw=%s（全 0 = 纯律在管）" % (
            sorted({round(g(x, "thr"), 2) for x in seg}), sorted({round(g(x, "pit"), 2) for x in seg}),
            sorted({round(g(x, "rol"), 2) for x in seg}), sorted({round(g(x, "yaw"), 2) for x in seg})))
        print("  姿态/航向：pa %s→%s，ra 摆幅 ±%.1f°，rr 峰值 %.1f°/s" % (
            round(g(seg[0], "pa"), 1), round(g(seg[-1], "pa"), 1),
            max(abs(g(x, "ra")) for x in seg), max(abs(g(x, "rr")) for x in seg)))
    al = [a for a in alarm.get(cid, []) if abs(a[0] - (lock[0] if lock else 0)) < 400]
    if al:
        c = {}
        for t, s in al:
            c[s] = c.get(s, 0) + 1
        print("  ALARM 的 LandingGearDown 态计数：%s" % c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cid")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    tel, pos, alarm, order = load()
    if a.list or not a.cid:
        print("=== 最近出现的机体（按文件末尾顺序）===")
        for cid in order[-8:]:
            rs = split_runs(tel.get(cid, []))
            big = [r for r in rs if len(r) > 60]
            print("  cid=%-7s 段=%2d 末帧 t=%7.1f 帧=%6d" % (
                cid, len(big), big[-1][-1][0] if big else -1, len(tel.get(cid, []))))
        if a.list:
            return
        a.cid = order[-1]
    rs = [r for r in split_runs(tel[a.cid]) if len(r) > 60]
    if not rs:
        sys.exit("cid=%s 没有足够帧" % a.cid)
    report(a.cid, tel, pos, rs)


if __name__ == "__main__":
    main()
