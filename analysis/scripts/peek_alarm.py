import io, sys, collections, os
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
LOG = os.path.expandvars(r"%USERPROFILE%\AppData\LocalLow\Jundroo\SimplePlanes 2\Player.log")
rows = collections.defaultdict(list)
for ln in io.open(LOG, encoding="utf-8", errors="replace"):
    f = ln.rstrip("\n").split(",")
    if f[0] == "ALARM" and len(f) >= 8:
        try:
            rows[f[1]].append((float(f[2]), f[3], f[4], float(f[6]), float(f[7])))
        except ValueError:
            pass
for cid, rs in sorted(rows.items()):
    gd = collections.Counter(r[1] for r in rs)
    sds = [r[3] for r in rs if r[3] > -9999]
    print("=== cid=%s  ALARM %d 帧  t=%.0f..%.0f  gd 分布=%s" %
          (cid, len(rs), rs[0][0], rs[-1][0], dict(gd)))
    if sds:
        print("    有走廊 %d/%d 帧；SD min=%.0f max=%.0f；SD<3000 的帧数=%d" %
              (len(sds), len(rs), min(sds), max(sds), sum(1 for s in sds if s < 3000)))
        near = [r for r in rs if -9999 < r[3] < 3000]
        if near:
            print("    SD<3000 区间: t=%.0f..%.0f  近场点例: %s" %
                  (near[0][0], near[-1][0],
                   [(round(r[0]), round(r[3]), round(r[4])) for r in near[::max(1, len(near)//6)]][:7]))
    else:
        print("    **全程无走廊**（bs 恒 -99999）")
