"""v1.6 新闸门的离线验证：拿用户上一局的 POS 航迹，逐点对比"旧闸门 vs 新闸门"选中的走廊。

验三件事：① 过阈值后走廊还活着（不再掉到哨兵）；② 选中的跑道不翻面（04L↔22L 反向端头）；
③ 选中的 |SD| 在滑跑段仍然合理（几百米量级，不是整条跑道长度）。
"""
import io, os, sys, json, math, bisect
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

LOG = os.path.expandvars(r"%USERPROFILE%\AppData\LocalLow\Jundroo\SimplePlanes 2\Player.log")
TBL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "runway-locations.json")
CID = sys.argv[1] if len(sys.argv) > 1 else "2389"

rwy = []
for r in json.load(io.open(TBL, encoding="utf-8")):
    if "Helipad" in r["name"] or "Catapult" in r["name"]:
        continue
    lon, elev, lat = [float(v) for v in r["pos"].split(",")]
    rwy.append((r["name"].replace(" Airport", "").strip(), lat, lon, float(r["rot"].split(",")[1]), elev))

pos, tel = [], []
for ln in io.open(LOG, encoding="utf-8", errors="replace"):
    f = ln.rstrip("\n").split(",")
    try:
        if f[0] == "POS" and f[1] == CID and len(f) >= 6:
            pos.append((float(f[2]), float(f[3]), float(f[4])))
        elif f[0] == "TEL" and f[1] == CID and len(f) >= 24:
            tel.append((float(f[2]), float(f[4])))       # t, agl
    except ValueError:
        pass
# 只取最后一段（时间回退切局）
segs, cur = [], []
for r in pos:
    if cur and r[0] < cur[-1][0] - 1.0:
        segs.append(cur); cur = []
    cur.append(r)
if cur:
    segs.append(cur)
seg = segs[-1]
ts = [r[0] for r in tel]
import bisect as bs
def agl_at(t):
    i = bs.bisect_left(ts, t)
    i = min(max(i, 0), len(ts) - 1)
    if i > 0 and abs(ts[i-1]-t) < abs(ts[i]-t):
        i -= 1
    return tel[i][1]

def shots(lat, lon, agl, new):
    out = []
    # 横向窗按**真式**地板取 900（本局进近 IAS 45~68 ⇒ 2·IAS²/13.5 ≤ 685 < 900 ⇒ 地板即真值）
    for nm, la, lo, hd, el in rwy:
        h = math.radians(hd); c, s = math.cos(h), math.sin(h)
        sd = (la - lat) * c + (lo - lon) * s
        lt = (lat - la) * s - (lon - lo) * c
        if abs(lt) >= 900:
            continue
        if new:
            g = ((sd > -50) or ((sd > -3500) and (agl < 100))) and (sd < 15000)
        else:
            g = (sd > -50) and (sd < 15000)
        if g:
            out.append((nm, sd, lt))
    if not out:
        return ("哨兵", 9999999.0, 0.0)
    if new:
        return min(out, key=lambda x: abs(x[1]))       # |SD| 最小
    return min(out, key=lambda x: x[1])                # 最小 SD（旧）

print("cid=%s 末段 %d 点  t=%.0f..%.0f" % (CID, len(seg), seg[0][0], seg[-1][0]))
print(" t     agl   旧: 跑道/SD/LT          新: 跑道/SD/LT")
for i in range(0, len(seg), max(1, len(seg) // 30)):
    t, lat, lon = seg[i]
    agl = agl_at(t)
    o = shots(lat, lon, agl, False)
    n = shots(lat, lon, agl, True)
    print("%5.0f %6.0f   %-12s %8.0f %7.0f   %-12s %8.0f %7.0f" %
          (t, agl, o[0], o[1] if o[1] < 99999 else -1, o[2], n[0], n[1] if n[1] < 99999 else -1, n[2]))
