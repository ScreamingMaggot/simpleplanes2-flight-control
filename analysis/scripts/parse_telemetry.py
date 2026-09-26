#!/usr/bin/env python3
"""Player.log → 遥测 CSV（多流版）。用法: python parse_telemetry.py [输出.csv]

v2: TEL 行带 cid 身份列；同一日志多架带 MFD 的飞机按 cid 分流各自成 csv。
v3 (2026-09-27, SC-6 v2.36): **新增 APPR 流**——FT 进近面板的 Lua 复算镜像
    （见 platform-facts §37）。两流的采样率**不同**（TEL 2 分频、APPR 6 分频）
    ⇒ **各自成 csv，绝不合并**（合并会造出假等间隔，任何按 dt 的分析都会错）。

输出（并列，互不干扰）：
    <out>.cid<NN>[.run<k>].csv         TEL 流（原有格式不变）
    <out>.appr.cid<NN>[.run<k>].csv    APPR 流（38 列进近内部量）

⚠ 读 APPR 的两条硬约束（与生成物文件头一致，分析侧必须照办）：
  ① `SLK` 列**恒 −1、不是真相**——镜像里 Activate1..8 恒置 0（setter 面板读不到，
     platform-facts §28/29）⇒ 凡用它的量（SLK 的进 7 门）与真面板必然不同。
  ② 有状态量（vsCmd/altTgt/vsErr/thrCmd/spdBrk 等含 sum/smooth/rate 的）从
     **镜像启用那一帧**起算，面板状态可能更早建立 ⇒ 头几秒可能不同，**只看稳态段**。
"""
import io, os, sys, csv
from collections import OrderedDict

LOG = os.path.expanduser(r"~\AppData\LocalLow\Jundroo\SimplePlanes 2\Player.log")

# ── 流定义：每条 = (日志前缀, 列名表)。列名必须与 Lua 侧 print 的表头**逐字一致** ──
TEL_COLS = ["cid", "t", "alt", "agl", "ias", "gs", "pa", "pr", "yr", "hr", "ra", "rr",
            "aoa", "aos", "gf", "vg", "fuel", "thr", "trim", "pit", "rol", "yaw", "flp"]
APPR_COLS = ["cid", "t", "SD", "LT", "TLA", "HDG", "BRG", "rwyOk", "rwyPri", "xtrk",
             "trkEr", "trkUse", "trkGd", "LEAD", "bankTrk", "phiCmd", "cmdPhi",
             "htExcess", "altTgt", "vsCmd", "vsErr", "tanG", "fldE", "vsLine",
             "thrCmd", "thrPI", "thrErr", "spdBrk", "airFly", "gndIdle", "revOn",
             "SLK", "appr", "gearCmd", "brkCmd", "brkLvl", "RCAP", "boot", "airb", "hold"]

# 前缀顺序有讲究：**APPR 必须排在 TEL 之前判定**吗？不需要——"TEL," 不会出现在 APPR 行里
# （APPR 行以 "APPR," 开头），"APPR," 也不会出现在 TEL 行里。两者互不包含，顺序无关。
STREAMS = [
    ("TEL,", "TEL", TEL_COLS),
    ("APPR,", "APPR", APPR_COLS),
]


def parse(log_path):
    """返回 {stream_name: {cid: [run, ...]}}，run = [[vals...], ...]。"""
    out = OrderedDict((name, OrderedDict()) for _, name, _ in STREAMS)
    last_t = {name: {} for _, name, _ in STREAMS}
    with io.open(log_path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            for prefix, name, cols in STREAMS:
                i = line.find(prefix)
                if i < 0:
                    continue
                parts = line[i:].strip().split(",")[1:]
                # 列数必须严格等于表头（防截断行/错位行悄悄混进来）
                if len(parts) != len(cols):
                    continue
                try:
                    cid = int(parts[0])
                    vals = [float(cid)] + [float(p) for p in parts[1:]]
                except ValueError:
                    continue
                runs = out[name].setdefault(cid, [])
                # 时间戳回退 = 重载/重新起飞 ⇒ 新架次（两流各自独立判定：
                # MFD 的 RoundRobin 调度会让某条流先停后启，不能共用 last_t）
                if cid in last_t[name] and vals[1] < last_t[name][cid]:
                    runs.append([])
                if not runs:
                    runs.append([])
                runs[-1].append(vals)
                last_t[name][cid] = vals[1]
                break          # 一行只属于一条流
    return out


def suffix_for(cid, k, n_runs, n_cids):
    if n_cids > 1 or n_runs > 1:
        return f".cid{cid}" + (f".run{k+1}" if n_runs > 1 else "")
    return ""


def write_stream(streams, cols, out, tag):
    """写一条流的全部 csv。返回 (文件数, 样本数)。"""
    files = samples = 0
    for cid, runs in streams.items():
        for k, run in enumerate(runs):
            if not run:
                continue
            sfx = suffix_for(cid, k, len(runs), len(streams))
            if tag:
                name = out.replace(".csv", f".{tag}" + sfx + ".csv")
            else:
                name = out.replace(".csv", sfx + ".csv")
            with io.open(name, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                w.writerows(run)
            t0, t1 = run[0][1], run[-1][1]
            print(f"{os.path.basename(name)}: {len(run)} 样本, {t0:.1f}s→{t1:.1f}s, "
                  f"平均 {len(run)/max(t1-t0,1e-6):.1f} Hz")
            files += 1
            samples += len(run)
    return files, samples


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "telemetry.csv"
    if not os.path.isabs(out):
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", out)
    if not os.path.exists(LOG):
        sys.exit(f"日志不存在：{LOG}")

    streams = parse(LOG)
    tel, appr = streams["TEL"], streams["APPR"]

    if not tel and not appr:
        sys.exit("Player.log 里既没有 TEL 也没有 APPR 行——先确认 MFD 补丁已 apply "
                 "且飞机装了 MFD-1 零件（APPR 还要求 addon 已用 build_mirror_addon.py "
                 "--inplace 带镜像）")
    if tel:
        write_stream(tel, TEL_COLS, out, "")
    else:
        print("（无 TEL 行）")
    if appr:
        write_stream(appr, APPR_COLS, out, "appr")
        print()
        print("⚠ APPR 读数约束：① `SLK` 列恒 −1、不是真相（镜像 ActivateN 恒 0）；"
              "② 含 sum/smooth/rate 的量头几秒可能与真面板不同 ⇒ 只看稳态段。")
    else:
        print("（无 APPR 行）——若期望有：addon 未带镜像，需 "
              "`python build_mirror_addon.py --inplace` 后重跑 `build_patch.py --apply` 并冷启动。")


if __name__ == "__main__":
    main()
