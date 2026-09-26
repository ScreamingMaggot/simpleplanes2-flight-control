# -*- coding: utf-8 -*-
"""Faithful offline recompute of the ACTUAL v2.19 panel runway-selection, per frame.

Why: ta2_flight.py:geo() is a stale/looser model (no axis gate, different rcap cap, no
pointing-priority carry). To answer "why didn't the corridor lock the 2nd-landing airport"
I must reproduce the real PANEL expressions gate-for-gate, not the old tool's approximations.

Gate formulas mirrored verbatim from ft_ta2_patch.py PANEL (see line refs in comments).
Prints ASCII only (Windows GBK console can't print the tool's Chinese lines).
"""
import io, os, sys, math, bisect

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.expandvars(r"%USERPROFILE%\AppData\LocalLow\Jundroo\SimplePlanes 2\Player.log")
sys.path.insert(0, HERE)
from ft_ta2_patch import RWYS  # loader already filtered to 13 runways, same order as PANEL

# PANEL index map (13 kept)
IDX = {nm: i for i, (nm, _, _, _, _) in enumerate(RWYS)}
_prevDS = {}   # per-runway last-sampled distance, for the "closing?" finite-difference
BANNOCK = [i for i, (nm, _, _, _, _) in enumerate(RWYS) if nm.startswith("Bannock")]


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def deltaangle(a, b):
    d = (a - b + 180.0) % 360.0 - 180.0
    return d


def per_runway(rwy, plat, plon, agl, ias, heading, relaxed=False, cap_r=15000.0):
    nm, rlat, rlon, hdg, el = rwy
    h = math.radians(hdg)
    c, s = math.cos(h), math.sin(h)
    # SD/LT (PANEL lines 69-70)
    SD = (rlat - plat) * c + (rlon - plon) * s
    LT = (plat - rlat) * s - (plon - rlon) * c
    rcap = max(900.0, min(2 * (ias * ias / 13.5), 1800.0))
    G = ((SD > -50) or ((SD > -3500) and agl < 100)) and (abs(LT) < rcap) and (SD < 15000)
    BG = hdg + math.degrees(math.atan2(LT, SD))   # world bearing plane->threshold (fixed sign v2.23)
    DS = math.hypot(SD, LT)
    # relaxed terminal-area candidate ZK: in capture radius + nose on threshold
    ZK = (DS < cap_r) and (abs(deltaangle(BG, heading)) < 60)
    return dict(nm=nm, SD=SD, LT=LT, DS=DS, el=el, hdg=hdg, G=G, BG=BG, ZK=ZK,
                cone=(abs(deltaangle(BG, heading)) < 60), axis=(abs(deltaangle(hdg, heading)) < 90),
                K=G, PR=(abs(deltaangle(BG, heading)) < 45))


def select_v223(rows, prevDS, slk, armed, agl):
    """Mirror v2.23 panel: CL=rate(DS)<0, NX=nearest ZK&CL index, SLK latch, then pick where idx==SLK."""
    # CL from finite difference vs prevDS
    for i, r in enumerate(rows):
        r["CL"] = (r["nm"] in prevDS) and (r["DS"] < prevDS[r["nm"]] - 0.5)
        prevDS[r["nm"]] = r["DS"]
    # NX = nearest (ZK & CL) index
    bd, nx = 99999999.0, -1
    for i, r in enumerate(rows):
        if r["ZK"] and r["CL"] and (r["DS"] < bd):
            bd, nx = r["DS"], i
    # SLK latch (self-ref): armed&airborne ? (locked ? keep : NX) : -1
    if armed and agl > 3:
        slk = slk if (slk > -0.5) else nx
    else:
        slk = -1.0
    sel = slk if (0 <= slk < len(rows)) else None
    winner = rows[int(sel)]["nm"] if sel is not None else None
    return winner, slk, nx


def select_m3(rows, prevDS, slk, miss, armed, agl, cap_r, commit, rel_s):
    """M3 redesign: bounded capture + release-on-departing + enroute/final phase.
       cap_r: only recognize airports within this radius (topple v2.23's far-grab).
       commit: within this radius, don't require 'closing' (you're clearly inbound).
       rel_s: release latch after this many consecutive samples that no longer close on target."""
    for r in rows:
        r["CL"] = (r["nm"] in prevDS) and (r["DS"] < prevDS[r["nm"]] - 0.5)
        prevDS[r["nm"]] = r["DS"]
    # NX = nearest valid candidate: ZK & (closing OR inside commit radius)
    bd, nx = 99999999.0, -1
    for i, r in enumerate(rows):
        if r["ZK"] and (r["CL"] or r["DS"] < commit) and (r["DS"] < bd):
            bd, nx = r["DS"], i
    new_slk, new_miss = slk, miss
    if armed and agl > 3:
        if new_slk > -0.5:                      # have a lock
            tgt = rows[int(new_slk)]
            still_ok = tgt["ZK"] or tgt["DS"] < cap_r
            if not tgt["CL"] and still_ok:      # not closing on it anymore
                new_miss += 1
                if new_miss > rel_s:
                    new_slk, new_miss = float(nx), 0   # release -> re-pick now
            else:
                new_miss = 0
            if not still_ok:
                new_slk, new_miss = float(nx), 0
        else:
            new_slk = float(nx)                 # acquire nearest-closing
    else:
        new_slk, new_miss = -1.0, 0
    sel = int(new_slk) if 0 <= new_slk < len(rows) else None
    winner = rows[sel]["nm"] if sel is not None else None
    phase = "-"
    if sel is not None:
        phase = "FINAL" if (rows[sel]["G"] and rows[sel]["SD"] < 4000) else "ENROUTE"
    return winner, new_slk, new_miss, phase, nx


def load_frames(cid):
    """Return list of (t, lat, lon, alt, agl, ias, gs, heading) for the LARGEST segment of cid."""
    tel, pos = {}, {}
    order = []
    for ln in io.open(LOG, encoding="utf-8", errors="replace"):
        if ln.startswith("TEL,"):
            f = ln.rstrip("\n").split(",")
            if len(f) - 2 != 22:
                continue
            try:
                v = [float(x) for x in f[2:]]
            except ValueError:
                continue
            tel.setdefault(f[1], []).append(v)
        elif ln.startswith("POS,"):
            f = ln.rstrip("\n").split(",")
            try:
                pos.setdefault(f[1], []).append((float(f[2]), float(f[3]), float(f[4])))
            except (ValueError, IndexError):
                pass
    return tel.get(cid, []), pos.get(cid, [])


def split_runs(rows, key=0):
    out, cur = [], []
    for r in rows:
        if cur and r[key] < cur[-1][key] - 1.0:
            out.append(cur); cur = []
        cur.append(r)
    if cur:
        out.append(cur)
    return [sorted(c, key=lambda x: x[key]) for c in out if c]


def mk_near(P):
    """Return near(t) using binary search over a time-sorted POS list (avoids O(n^2))."""
    ts = [p[0] for p in P]

    def near(t):
        if not P:
            return None
        i = bisect.bisect_left(ts, t)
        cands = [j for j in (i - 1, i) if 0 <= j < len(P)]
        if not cands:
            return None
        j = min(cands, key=lambda k: abs(ts[k] - t))
        return P[j] if abs(ts[j] - t) < 1.0 else None
    return near


def main():
    cid = sys.argv[1] if len(sys.argv) > 1 else "2389"
    if len(sys.argv) > 3 and sys.argv[2] == "probe":
        tmin = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
        tmax = float(sys.argv[5]) if len(sys.argv) > 5 else 1e9
        step = float(sys.argv[6]) if len(sys.argv) > 6 else 2.0
        mode = sys.argv[7] if len(sys.argv) > 7 else "r"
        if mode == "m3":
            cap_r = float(sys.argv[8]) * 1000.0 if len(sys.argv) > 8 else 8000.0
            commit = float(sys.argv[9]) if len(sys.argv) > 9 else 4000.0
            rel_s = int(sys.argv[10]) if len(sys.argv) > 10 else 3
            probe_leg(cid, int(sys.argv[3]), tmin, tmax, step, True, cap_r, commit, rel_s)
        else:
            probe_leg(cid, int(sys.argv[3]), tmin, tmax, step, armed=(mode != "n"))
        return
    tel, pos = load_frames(cid)
    Truns = split_runs(tel, key=0)
    Pruns = split_runs(pos, key=0)
    print("cid=%s TEL segs=%d sizes=%s" % (cid, len(Truns), [len(r) for r in Truns]))
    print("        POS segs=%d sizes=%s" % (len(Pruns), [len(r) for r in Pruns]))
    print("Bannock idx=%s  IDX map=%s" % (BANNOCK, IDX))

    # pick the segment with a Bannock-ish landing (touchdown near Bannock thresholds)
    for si, T in enumerate(Truns):
        t0, tN = T[0][0], T[-1][0]
        P = Pruns[si] if si < len(Pruns) else []
        near = mk_near(P)
        # find min distance to ANY airport + report the airport reached closest (touched down)
        minb = None
        for r in T[::5]:
            p = near(r[0])
            if not p:
                continue
            for bi, rw in enumerate(RWYS):
                nm, rlat, rlon, hdg, el = rw
                d = math.hypot(rlat - p[1], rlon - p[2])
                if minb is None or d < minb[0]:
                    minb = (d, r[0], nm)
        print("\n[seg %d] t=%.1f..%.1f frames=%d  min-dist-to-anyrwy=%s" % (
            si, t0, tN, len(T), ("%.0fm @t=%.0f (%s)" % minb) if minb else "n/a"))


def probe_leg(cid, si, tmin=0.0, tmax=1e9, step=2.0, armed=True, cap_r=None, commit=4000.0, rel_s=3):
    tel, pos = load_frames(cid)
    T = split_runs(tel, key=0)[si]
    P = split_runs(pos, key=0)[si]

    m3 = cap_r is not None
    near = mk_near(P)
    print("\n=== %s selection, seg %d  window t=[%.0f,%.0f]  armed(7)=%s ===" % (
        (("M3 cap=%dkm commit=%dm rel=%d" % (cap_r / 1000, commit, rel_s)) if m3 else "v2.23 Option-A"),
        si, tmin, tmax, armed))
    print("    t    agl   ias  heading | SLK winner        phase  | SD/DS      | nearest2(DS ZK/CL)")
    nxt = -1.0
    prev_w = None
    slk = -1.0
    miss = 0
    pds = {}
    for r in T:
        t = r[0]
        if t < tmin:
            continue
        if t > tmax:
            break
        if t < nxt:
            continue
        nxt = t + step
        p = near(t)
        if not p:
            continue
        agl, ias, heading = r[2], r[3], r[8]
        rows = [per_runway(rw, p[1], p[2], agl, ias, heading, cap_r=cap_r or 15000.0) for rw in RWYS]
        if m3:
            w, slk, miss, phase, nx = select_m3(rows, pds, slk, miss, armed, agl, cap_r, commit, rel_s)
        else:
            w, slk, nx = select_v223(rows, pds, slk, armed, agl)
            phase = "-"
        wsd = ""
        if w:
            wi = IDX[w]
            wsd = "%6.0f/%6.0f" % (rows[wi]["SD"], rows[wi]["DS"])
        nn = sorted(rows, key=lambda x: x["DS"])[:2]
        detail = "  ".join("%s[%.0fk %d%d]" % (
            x["nm"].replace(" Station", "").replace(" Airport", "")[:12], x["DS"] / 1000.0,
            int(x["ZK"]), int(x["CL"])) for x in nn)
        mark = "" if w == prev_w else "  <== was:" + str(prev_w)
        prev_w = w
        print("%6.1f %5.0f %5.0f %6.0f | %3.0f %-16s %-6s | %-13s | %s%s" % (
            t, agl, ias, heading, slk, (w or "(none)"), phase, wsd, detail, mark))


if __name__ == "__main__":
    main()
