#!/usr/bin/env python3
"""离线重放 SC-6 面板的走廊几何，回答"起落架/刹车条件当时到底成不成立"。

为什么必须做：本机起落架+刹车的自动条件都含 `SD < 3000`。若 SD 从未选上走廊（哨兵 9999999），
那"什么都没动"是**测试空转**而不是"平台不执行表达式"——不问这一句就下结论=冤案。
坐标系：FT 的 Latitude/Longitude = 世界 z/x（米），跑道表 lat/lon 同系（SC-3b 源码实锤）。
"""
import io, os, re, sys, math, json, collections

LOG = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.expandvars(r"%USERPROFILE%\AppData\LocalLow\Jundroo\SimplePlanes 2\Player.log")
TBL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "runway-locations.json")

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

rwy = []
for r in json.load(io.open(TBL, encoding="utf-8")):
    nm = r["name"]
    if "Helipad" in nm or "Catapult" in nm:
        continue                      # 与 ft_ta2_patch.load_runways() 逐字同规
    lon, elev, lat = [float(v) for v in r["pos"].split(",")]     # pos = x,y,z = lon,elev,lat
    hdg = float(r["rot"].split(",")[1])
    rwy.append((nm.replace(" Airport", "").strip(), lat, lon, hdg, elev))
print("跑道表 %d 条" % len(rwy))

pos, tel = [], []
for ln in io.open(LOG, encoding="utf-8", errors="replace"):
    f = ln.rstrip("\n").split(",")
    if f[0] == "POS" and len(f) >= 6:
        try:
            pos.append((int(f[1]), float(f[2]), float(f[3]), float(f[4]), float(f[5])))
        except ValueError:
            pass
    elif f[0] == "TEL" and len(f) >= 21:
        try:
            tel.append((int(f[1]), float(f[2]), float(f[3]), float(f[4]),   # cid t alt agl
                        float(f[5]), float(f[6]), float(f[12]), float(f[11])))  # ias gs roll rturn? -> ias,gs,roll
        except ValueError:
            pass
print("POS %d  TEL %d" % (len(pos), len(tel)))

by = collections.defaultdict(list)
for cid, t, lat, lon, alt in pos:
    by[cid].append((t, lat, lon, alt))
telby = collections.defaultdict(list)
for cid, t, alt, agl, ias, gs, roll, _x in tel:
    telby[cid].append((t, alt, agl, ias, gs, roll))

def segs(rows):   # 时钟回退=新局
    out, cur = [], []
    for r in rows:
        if cur and r[0] < cur[-1][0] - 1.0:
            out.append(cur); cur = []
        cur.append(r)
    if cur:
        out.append(cur)
    return out

for cid in sorted(by):
    for k, sg in enumerate(segs(sorted(by[cid]))):
        if len(sg) < 30:
            continue
        print("\n=== cid=%d 段%d  POS %d 点  t=%.0f..%.0f ===" % (cid, k, len(sg), sg[0][0], sg[-1][0]))
        tgs = dict((round(r[0], 1), r) for r in telby[cid])
        hits = collections.Counter()
        best = None
        for t, lat, lon, alt in sg:
            r = None
            for dt in (0.0, 0.1, -0.1, 0.2, -0.2):
                r = tgs.get(round(t + dt, 1))
                if r:
                    break
            agl = r[2] if r else 0.0
            ias = r[3] if r else 0.0
            rcap = max(900.0, 2 * ias * ias / 13.5)
            cand = []
            for i, (nm, la, lo, hd, el) in enumerate(rwy):
                h = math.radians(hd); c, s = math.cos(h), math.sin(h)
                sd = (la - lat) * c + (lo - lon) * s
                lt = (lat - la) * s - (lon - lo) * c
                if sd > -50 and abs(lt) < rcap and sd < 15000:
                    cand.append((sd, lt, nm))
            if cand:
                sd, lt, nm = min(cand)
                hits["gated"] += 1
                if sd < 3000:
                    hits["sd<3000"] += 1
                    if agl > 5:
                        hits["GEAR cond"] += 1
                    if agl < 8:
                        hits["BRAKE cond"] += 1
                if best is None or sd < best[0]:
                    best = (sd, lt, nm, agl)
        print("  命中走廊 %d 帧 / 共 %d 帧" % (hits["gated"], len(sg)))
        for k2 in ("sd<3000", "GEAR cond", "BRAKE cond"):
            print("    %-11s : %d 帧" % (k2, hits[k2]))
        if best:
            print("    最近走廊样本: SD=%.0f LT=%.0f  %s  agl=%.0f" % best)
        else:
            print("    **全程从未命中走廊** ⇒ SD 恒为哨兵，两个自动条件都不可能成立（测试空转）")
