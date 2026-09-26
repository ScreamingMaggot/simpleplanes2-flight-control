import io, os, sys, bisect, collections
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
_args = sys.argv[1:]
LOG = _args.pop(0) if _args and _args[0].lower().endswith(".log") else os.path.expandvars(
    r"%USERPROFILE%\AppData\LocalLow\Jundroo\SimplePlanes 2\Player.log")
CID = _args[0] if _args else "2389"
SEG = int(_args[1]) if len(_args) > 1 else -1   # 取第几段（负数=从后数）

tel, alm = [], []
for ln in io.open(LOG, encoding="utf-8", errors="replace"):
    f = ln.rstrip("\n").split(",")
    try:
        if f[0] == "TEL" and len(f) >= 24 and f[1] == CID:
            tel.append([float(x) for x in f[2:]])
        elif f[0] == "ALARM" and len(f) >= 8 and f[1] == CID:
            alm.append((float(f[2]), f[3], f[4], float(f[6]), float(f[7])))
    except ValueError:
        pass

def split(rows):
    out, cur = [], []
    for r in rows:
        if cur and r[0] < cur[-1][0] - 1.0:
            out.append(cur); cur = []
        cur.append(r)
    if cur:
        out.append(cur)
    return out

segs = split(tel)
sg = segs[SEG]
t0, t1 = sg[0][0], sg[-1][0]
print("cid=%s 段 t=%.0f..%.0f (%d 帧)" % (CID, t0, t1, len(sg)))
al = [a for a in alm if t0 - 1 <= a[0] <= t1 + 1]
ats = [a[0] for a in al]

def alm_at(t):
    if not ats:
        return None
    i = bisect.bisect_left(ats, t)
    if i >= len(ats):
        i = len(ats) - 1
    if i > 0 and abs(ats[i - 1] - t) < abs(ats[i] - t):
        i -= 1
    return al[i]

print("  t    alt   agl   ias   thr    pit     pa     ra   | 最近跑道    SD      LT   手柄")
for i in range(0, len(sg), max(1, len(sg) // 40)):
    r = sg[i]
    a = alm_at(r[0])
    if a:
        nm, sd, lt, gd = a[2], a[3], a[4], a[1]
        ss = "%.0f" % sd if sd > -9999 else "哨兵"
        ls = "%.0f" % lt if lt > -9999 else "-"
    else:
        nm, ss, ls, gd = "-", "-", "-", "-"
    print("%5.0f %6.0f %5.0f %5.1f %5.2f %6.2f %6.1f %6.1f  | %-14s %7s %7s  %s"
          % (r[0], r[1], r[2], r[3], r[16], r[18], r[5], r[9], nm, ss, ls, gd))
