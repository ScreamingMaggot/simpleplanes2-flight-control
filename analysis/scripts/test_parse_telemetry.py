"""parse_telemetry.py 的双流解析自测（合成日志，不依赖游戏）。"""
import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "parse_telemetry.py")

TEL_HDR = ("TEL,cid,t,alt,agl,ias,gs,pa,pr,yr,hr,ra,rr,aoa,aos,gf,vg,fuel,"
           "thr,trim,pit,rol,yaw,flp")
APPR_HDR = ("APPR,cid,t,SD,LT,TLA,HDG,BRG,rwyOk,rwyPri,xtrk,trkEr,trkUse,trkGd,LEAD,"
            "bankTrk,phiCmd,cmdPhi,htExcess,altTgt,vsCmd,vsErr,tanG,fldE,vsLine,thrCmd,"
            "thrPI,thrErr,spdBrk,airFly,gndIdle,revOn,SLK,appr,gearCmd,brkCmd,brkLvl,"
            "RCAP,boot,airb,hold")


def tel(cid, t, alt):
    # 23 个字段：cid,t + 21 值
    vals = [cid, t, alt, 100, 70, 75, 1.0, 0.1, 0.2, 190, 5, 0.3, 3.1, 0.4, 1.0, 1.0,
            88, 0.5, 0.1, 0.2, 0.3, 0.4, 0.0]
    return "TEL," + ",".join(str(v) for v in vals)


def appr(cid, t, sd):
    # 41 个字段：cid,t + 38 值
    vals = [cid, t, sd, 10, 20, 190, 45, 1, 1, 5, -1.2, 189, 1, 3, -12, 0.4, -0.2,
            120, 300, -2, 0.1, 0.05, 25, 250, 0.6, 0.5, -3, 0.1, 1, 0, 0, -1, 1, 1,
            0.2, 0.3, 900, 1, 1, 1.0]
    assert len(vals) == 40, len(vals)
    return "APPR," + ",".join(str(v) for v in vals)


def build_log():
    lines = ["Unity Player log junk"]
    lines.append(TEL_HDR)
    lines.append(APPR_HDR)
    # cid 111: one run, TEL 2 Hz + APPR 6 Hz interleaved
    for k in range(20):
        lines.append(tel(111, 100 + k * 0.5, 500 + k))
        if k % 3 == 0:
            lines.append(appr(111, 100 + k * 0.5, 8000 - k * 10))
    # restart (timestamp goes back)
    lines.append(tel(111, 5.0, 700))
    lines.append(appr(111, 5.0, 7000))
    for k in range(5):
        lines.append(tel(111, 5.5 + k * 0.5, 700 + k))
        lines.append(appr(111, 5.5 + k * 0.5, 6900 - k * 10))
    # second aircraft cid 222
    for k in range(6):
        lines.append(tel(222, 50 + k * 0.5, 300))
        lines.append(appr(222, 50 + k * 0.5, 4000))
    # deliberate corruption: short APPR row and a NaN-ish garbage row must be dropped
    lines.append("APPR,111,3.0,1,2,3")
    lines.append("APPR,111,notanumber," + ",".join(["1"] * 38))
    lines.append("TEL,111,4.0,1")
    return "\n".join(lines) + "\n"


def main():
    tmp = tempfile.mkdtemp(prefix="telparse_")
    try:
        log = os.path.join(tmp, "Player.log")
        io.open(log, "w", encoding="utf-8").write(build_log())

        # 用 monkeypatch 方式替换 LOG 路径：直接改模块变量最省事
        sys.path.insert(0, HERE)
        import importlib.util
        spec = importlib.util.spec_from_file_location("pt", SCRIPT)
        pt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pt)

        streams = pt.parse(log)
        tel_s, appr_s = streams["TEL"], streams["APPR"]

        print("TEL cids:", list(tel_s), " runs:", {c: len(r) for c, r in tel_s.items()})
        print("APPR cids:", list(appr_s), " runs:", {c: len(r) for c, r in appr_s.items()})

        ok = True
        # cid 111 should have 2 runs in BOTH streams (restart)
        if len(tel_s.get(111, [])) != 2:
            print("FAIL: TEL cid111 应有 2 架次，得到", len(tel_s.get(111, []))); ok = False
        if len(appr_s.get(111, [])) != 2:
            print("FAIL: APPR cid111 应有 2 架次，得到", len(appr_s.get(111, []))); ok = False
        # cid 222 one run each
        if len(tel_s.get(222, [])) != 1 or len(appr_s.get(222, [])) != 1:
            print("FAIL: cid222 应为 1 架次"); ok = False
        # corrupted rows dropped: run1 TEL has 20；run2 = 回退那拍(t=5.0) + 之后 5 拍 = 6
        r1 = tel_s[111][0]
        if len(r1) != 20:
            print("FAIL: TEL cid111 run1 应 20 样本，得到", len(r1)); ok = False
        if len(tel_s[111][1]) != 6:
            print("FAIL: TEL cid111 run2 应 6 样本，得到", len(tel_s[111][1])); ok = False
        # 截断行必须被丢弃（那条 "TEL,111,4.0,1" 若被计入，run2 会变 7）
        if tel_s[111][1][0][1] != 5.0:
            print("FAIL: run2 首样本应为 t=5.0，得到", tel_s[111][1][0][1]); ok = False
        # APPR run1: k in 0..19 with k%3==0 -> 7 rows
        if len(appr_s[111][0]) != 7:
            print("FAIL: APPR cid111 run1 应 7 样本，得到", len(appr_s[111][0])); ok = False
        # every APPR row must have exactly 38 data cols
        for cid, runs in appr_s.items():
            for run in runs:
                for v in run:
                    if len(v) != 40:
                        print("FAIL: APPR 行列数", len(v)); ok = False
                        break
        # write out and check filenames + header
        out = os.path.join(tmp, "telemetry.csv")
        nf_t, ns_t = pt.write_stream(tel_s, pt.TEL_COLS, out, "")
        nf_a, ns_a = pt.write_stream(appr_s, pt.APPR_COLS, out, "appr")
        print()
        print("TEL files=%d samples=%d ; APPR files=%d samples=%d" % (nf_t, ns_t, nf_a, ns_a))
        names = sorted(os.listdir(tmp))
        print("files:", names)
        appr_files = [n for n in names if ".appr." in n]
        if not appr_files:
            print("FAIL: 没有 appr.csv 产出"); ok = False
        for n in appr_files:
            first = io.open(os.path.join(tmp, n), encoding="utf-8").readline().strip().split(",")
            if first != pt.APPR_COLS:
                print("FAIL: %s 表头不符" % n); ok = False
        # TEL header intact
        for n in [x for x in names if x.endswith(".csv") and ".appr." not in x]:
            first = io.open(os.path.join(tmp, n), encoding="utf-8").readline().strip().split(",")
            if first != pt.TEL_COLS:
                print("FAIL: %s TEL 表头不符" % n); ok = False

        print()
        print("SELFTEST:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
