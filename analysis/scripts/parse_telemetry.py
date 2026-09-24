#!/usr/bin/env python3
"""Player.log → 遥测 CSV。用法: python parse_telemetry.py [输出.csv]
v2: TEL 行带 cid 身份列；同一日志多架带 MFD 的飞机按 cid 分流各自成 csv。"""
import io, os, sys, csv
from collections import OrderedDict

LOG = os.path.expanduser(r"~\AppData\LocalLow\Jundroo\SimplePlanes 2\Player.log")
HDR = ["cid","t","alt","agl","ias","gs","pa","pr","yr","hr","ra","rr","aoa","aos","gf","vg","fuel","thr","trim","pit","rol","yaw","flp"]

def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "telemetry.csv"
    if not os.path.isabs(out): out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", out)
    streams = OrderedDict()   # cid -> [run1, run2...]，run=[[vals...]...]
    last_t = {}
    with io.open(LOG, encoding="utf-8", errors="ignore") as f:
        for line in f:
            i = line.find("TEL,")
            if i < 0:
                continue
            parts = line[i:].strip().split(",")[1:]
            if len(parts) != len(HDR):
                continue
            try:
                cid = int(parts[0])
                vals = [float(cid)] + [float(p) for p in parts[1:]]
            except ValueError:
                continue
            runs = streams.setdefault(cid, [])
            if cid in last_t and vals[1] < last_t[cid]:
                runs.append([])   # 时间戳回退 = 重载/重新起飞
            if not runs:
                runs.append([])
            runs[-1].append(vals)
            last_t[cid] = vals[1]
    if not streams:
        sys.exit("Player.log 里没有 TEL 行——先确认 MFD 补丁已 apply 且飞机装了 MFD-1 零件")
    for cid, runs in streams.items():
        for k, run in enumerate(runs):
            if not run: continue
            suffix = f".cid{cid}" + (f".run{k+1}" if len(runs) > 1 else "") if len(streams) > 1 or len(runs) > 1 else ""
            name = out.replace(".csv", suffix + ".csv")
            with io.open(name, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f); w.writerow(HDR); w.writerows(run)
            t0, t1 = run[0][1], run[-1][1]
            print(f"{name}: {len(run)} 样本, {t0:.1f}s→{t1:.1f}s, 平均 {len(run)/max(t1-t0,1e-6):.1f} Hz")

if __name__ == "__main__":
    main()
