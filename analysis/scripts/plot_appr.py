# -*- coding: utf-8 -*-
"""APPR 进近内部量时间线 —— 六版连败时最缺的那个视图。

动机：M3/M4 六版连改失败，根因是"看不见横向律的输入量"。SC-6:1443 的教训是
"垂直环要动之前必须先挂内部读数"；本图是同一纪律在**横向**上的兑现。

读图顺序（*重要，不要反过来）：
  ① 先看 `rwyOk` / `appr` 两列 —— 没锁定、没接管时，下面的横向量都是巡航段噪声，
     把它们当进近数据用就是张冠李戴；
  ② 再看 `SD`（到跑道距离）与 `xtrk`（横向偏离）—— xtrk 该收敛到 0；
  ③ 最后看 `trkEr`（航向误差）与 `bankTrk`（指令坡度）—— 判断"缓飞还是急转"。

读数纪律（platform-facts §47）：
  * `SLK` 列恒 −1、**不是真相**（镜像 Activate1..8 恒 0，setter 面板读不到）-> 不画；
  * 含 `sum/smooth/rate` 的量（vsCmd/altTgt/vsErr/thrCmd/spdBrk）从**镜像启用那帧**起算
    -> 头几秒与真面板可能不同，**只看稳态段**。

用法: python plot_appr.py [aprr-csv ...]      缺省画 data/ 下最新的 appr csv。
"""
import os
import sys
import csv
import glob

_S = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_S, "..", "data")
FIGS = os.path.join(_S, "..", "figures")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

SENT = 1e6          # 哨兵阈值：|x| >= 1e6 视为"无数据"（-9999999 / 9999999 / -10523998）


def load(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    def col(k, default=float("nan")):
        out = []
        for r in rows:
            v = r.get(k, "")
            try:
                f = float(v)
            except (TypeError, ValueError):
                f = default
            # 哨兵一律置 NaN，避免把 9999999 画成真实距离（会是条假直线）
            if f == f and abs(f) >= SENT:
                f = float("nan")
            out.append(f)
        return out
    return rows, col


def main():
    args = sys.argv[1:]
    if not args:
        cand = sorted(glob.glob(os.path.join(DATA, "*.appr*.csv")),
                      key=os.path.getmtime)
        if not cand:
            sys.exit("data/ 下没有 appr csv —— 先跑 parse_telemetry.py")
        args = cand[-2:] if len(cand) >= 2 else cand[-1:]
    os.makedirs(FIGS, exist_ok=True)

    for path in args:
        rows, col = load(path)
        if not rows:
            print("skip (empty):", path); continue
        cid = os.path.basename(path).split("cid")[-1].split(".")[0]
        t = col("t")
        SD, LT, ap, rwyOk = col("SD"), col("LT"), col("appr"), col("rwyOk")
        xtrk, trkEr = col("xtrk"), col("trkEr")
        bankTrk, phiCmd = col("bankTrk"), col("phiCmd")
        altTgt, vsCmd, thrCmd = col("altTgt"), col("vsCmd"), col("thrCmd")
        gearCmd, brkCmd, revOn = col("gearCmd"), col("brkCmd"), col("revOn")
        htExcess = col("htExcess")

        n_locked = sum(1 for x in rwyOk if x == x and x > 0.5)
        n_appr = sum(1 for x in ap if x == x and abs(x) > 1e-9)
        engaged = n_appr > 0

        fig, axes = plt.subplots(5, 1, figsize=(15, 13), sharex=True)
        fig.suptitle(
            "APPR 进近内部量 - cid=%s  (n=%d, rwyOk=1 %d 帧, appr!=0 %d 帧%s)"
            % (cid, len(rows), n_locked, n_appr,
               "" if engaged else "  *本轮 7 层未接管：以下横向量多为巡航段噪声"),
            fontsize=13)

        # --- ① 门控：命令先看这个 ---
        ax = axes[0]
        ax.step(t, rwyOk, where="post", lw=1.6, color="tab:green", label="rwyOk 跑道已识别")
        ax.step(t, ap, where="post", lw=1.6, color="tab:red", label="appr 7层接管")
        ax.step(t, gearCmd, where="post", lw=1.0, color="tab:orange", ls=":", label="gearCmd 放轮")
        ax.set_ylabel("0/1 门控"); ax.set_ylim(-0.15, 1.3)
        ax.legend(loc="upper left", fontsize=9); ax.grid(alpha=.3)
        ax.set_title("① 门控（读图必先看这层：没锁定/没接管 -> 下面都是噪声）", fontsize=10)

        # --- ② 距离 + 横向偏离 ---
        ax = axes[1]
        ax.plot(t, SD, lw=1.3, color="tab:blue", label="SD 到跑道距离 (m)")
        ax.axhline(0, color="k", lw=.6, alpha=.5)
        ax.set_ylabel("SD (m)", color="tab:blue")
        ax.grid(alpha=.3)
        ax2 = ax.twinx()
        ax2.plot(t, xtrk, lw=1.3, color="tab:purple", label="xtrk 横向偏离 (m)")
        ax2.axhline(0, color="tab:purple", lw=.6, alpha=.4)
        ax2.set_ylabel("xtrk (m)", color="tab:purple")
        h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=9)
        ax.set_title("② 距离与横向偏离（xtrk 应收敛到 0）", fontsize=10)

        # --- ③ 横向律：航向误差 vs 指令坡度 ---
        ax = axes[2]
        ax.plot(t, trkEr, lw=1.3, color="tab:red", label="trkEr 航向误差 (deg)")
        ax.plot(t, bankTrk, lw=1.3, color="tab:cyan", label="bankTrk 指令坡度 (deg)")
        ax.plot(t, phiCmd, lw=1.0, color="gray", ls="--", alpha=.8, label="phiCmd")
        ax.axhline(0, color="k", lw=.6, alpha=.5)
        ax.axhline(30, color="orange", lw=.6, ls=":", alpha=.7)
        ax.axhline(-30, color="orange", lw=.6, ls=":", alpha=.7)
        ax.set_ylabel("deg"); ax.legend(loc="upper right", fontsize=9); ax.grid(alpha=.3)
        ax.set_title("③ 横向律输入/输出（这条线一眼看出「缓飞 vs 急转」）", fontsize=10)

        # --- ④ 垂直环 ---
        ax = axes[3]
        ax.plot(t, altTgt, lw=1.3, color="tab:green", label="altTgt 目标高 (m)")
        ax.plot(t, vsCmd, lw=1.3, color="tab:blue", label="vsCmd 升降率指令 (m/s)")
        ax.plot(t, htExcess, lw=1.1, color="tab:brown", label="htExcess 高差 (m)")
        ax.axhline(0, color="k", lw=.6, alpha=.5)
        ax.set_ylabel("m / (m/s)"); ax.legend(loc="upper right", fontsize=9); ax.grid(alpha=.3)
        ax.set_title("④ 垂直环（含 sum/smooth 的量：只看稳态段）", fontsize=10)

        # --- ⑤ 执行通道 ---
        ax = axes[4]
        ax.plot(t, thrCmd, lw=1.3, color="tab:red", label="thrCmd 油门")
        ax.plot(t, brkCmd, lw=1.3, color="tab:purple", label="brkCmd 轮刹")
        ax.plot(t, revOn, lw=1.1, color="tab:olive", ls=":", label="revOn 反推")
        ax.set_ylabel("0..1"); ax.set_xlabel("t (s)")
        ax.legend(loc="upper right", fontsize=9); ax.grid(alpha=.3)
        ax.set_title("⑤ 执行通道（油门/轮刹/反推）", fontsize=10)

        for a in axes:
            # 标出接管窗口，便于直接目测
            for i in range(1, len(t)):
                if ap[i] == ap[i] and ap[i-1] == ap[i-1] and ap[i] > 0.5 and ap[i-1] <= 0.5:
                    a.axvline(t[i], color="red", lw=.8, alpha=.35)
                if ap[i] == ap[i] and ap[i-1] == ap[i-1] and ap[i] <= 0.5 and ap[i-1] > 0.5:
                    a.axvline(t[i], color="gray", lw=.8, alpha=.35)

        fig.tight_layout(rect=[0, 0, 1, 0.97])
        out = os.path.join(FIGS, "appr_cid%s.png" % cid)
        fig.savefig(out, dpi=110)
        plt.close(fig)
        print("wrote %s   (rwyOk=1 %d 帧, appr!=0 %d 帧)" % (out, n_locked, n_appr))


if __name__ == "__main__":
    main()
