import io, sys, collections, os
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
LOG = os.path.expandvars(r"%USERPROFILE%\AppData\LocalLow\Jundroo\SimplePlanes 2\Player.log")

alarm = collections.defaultdict(list)
tel = collections.defaultdict(list)
for ln in io.open(LOG, encoding="utf-8", errors="replace"):
    f = ln.rstrip("\n").split(",")
    if f[0] == "ALARM" and len(f) >= 8:
        try:
            alarm[f[1]].append((float(f[2]), f[3], float(f[6]), float(f[7])))
        except ValueError:
            pass
    elif f[0] == "TEL" and len(f) >= 24:
        try:
            tel[f[1]].append((float(f[2]), float(f[4])))   # t, agl
        except ValueError:
            pass

for cid in sys.argv[1:] or sorted(alarm):
    tl = sorted(tel.get(cid, []))
    if not tl:
        continue
    import bisect
    ts = [x[0] for x in tl]
    def agl_at(t):
        i = bisect.bisect_left(ts, t)
        if i >= len(ts):
            i = len(ts) - 1
        if i > 0 and abs(ts[i - 1] - t) < abs(ts[i] - t):
            i -= 1
        return tl[i][1]
    # 列联表：条件 = (SD<3000)（我的起落架/刹车式都含它）
    tab = collections.Counter()
    for t, gd, sd, lt in alarm[cid]:
        a = agl_at(t)
        cond = sd < 3000
        if cond and a > 5:
            tab[("cond真", gd)] += 1
        elif not cond:
            tab[("cond假", gd)] += 1
    print("=== cid=%s  ALARM %d 帧 ===" % (cid, len(alarm[cid])))
    print("             gd=1(放下)  gd=0(收起)  gd=-")
    for c in ("cond真", "cond假"):
        print("  %-9s %8d %11d %7d" % (c, tab[(c, "1")], tab[(c, "0")], tab[(c, "-")]))
    # 时间线：条件与 gd 一起排，看 gd 有没有跟着条件翻
    print("  时间线（每 ~12 个 ALARM 取一个）：t  SD   agl  cond  gd")
    step = max(1, len(alarm[cid]) // 14)
    for t, gd, sd, lt in alarm[cid][::step]:
        a = agl_at(t)
        cond = (sd < 3000) and a > 5
        print("    %6.0f %8.0f %6.0f  %-5s %s" % (t, sd, a, "T" if cond else ".", gd))
