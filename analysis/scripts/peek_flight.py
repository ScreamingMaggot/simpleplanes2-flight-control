import io, sys, collections, os
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
LOG = os.path.expandvars(r"%USERPROFILE%\AppData\LocalLow\Jundroo\SimplePlanes 2\Player.log")
want = sys.argv[1:] or ["97306"]
rows = collections.defaultdict(list)
for ln in io.open(LOG, encoding="utf-8", errors="replace"):
    f = ln.rstrip("\n").split(",")
    if f[0] == "TEL" and len(f) >= 24 and f[1] in want:
        rows[f[1]].append([float(x) for x in f[2:]])

for cid in want:
    rs = rows[cid]
    print("=== cid=%s  %d 帧  t=%.0f..%.0f ===" % (cid, len(rs), rs[0][0], rs[-1][0]))
    print(" t     agl   ias   thr   pit    rol    pa     ra    rr    flp")
    step = max(1, len(rs) // 34)
    for i in range(0, len(rs), step):
        r = rs[i]
        # r = [t,alt,agl,ias,gs,pa,pr,yr,hdg,ra,rr,aoa,aos,gf,vg,fuel,thr,trim,pit,rol,yaw,flp]
        print("%5.0f %6.0f %6.1f %5.2f %6.2f %6.2f %6.1f %6.1f %6.1f %5.2f" %
              (r[0], r[2], r[3], r[16], r[18], r[19], r[5], r[9], r[10], r[21]))
