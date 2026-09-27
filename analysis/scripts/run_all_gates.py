#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键跑齐观测链的全部闸（fail-closed：任一不过即停）。

为什么要有这个：这条链上的每一道闸都是**用真实架次换来的**。单独跑容易漏，
漏一道就可能白飞一局。宁可多跑 30 秒，不可再赔一架次。

八道闸（按数据流顺序，与 build_mirror_addon.py 内的闸互补）：
  1. ft_mirror_gen.py        生成镜像；含布尔入数值 / nil 安全 / Lua 语法 / APPR 行完整性
  2. verify_mirror.py        镜像 vs FT 原式逐点交叉验证
  3. test_first_frame.py     首帧仿真：证明 V 预置 0 后 453 条全部可求值
  4. test_appr_print.py      APPR 打印路径闸：前缀实参受护 / 格式符数 == _num() 数
  5. test_appr_contract.py   生成物<->parser 契约闸：列名与列数逐字对齐
  6. test_parse_telemetry.py parser 自测：多 cid / 架次切分 / 截断行剔除
  7. build_mirror_addon.py   注入 addon（--inplace）；含代理裸读闸 / 幂等闸 / 词法作用域闸
  8. build_patch.py          dry-run：确认能写进 XML，且**镜像已带**（APPR 流可用）

任一失败即返回 1，并提示**不要**继续 --apply。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MFD = os.path.join(HERE, "..", "mfd-lua")
SCRIPTS = HERE

STEPS = [
    ("1/8 mirror generation (bool-into-number / nil safety / lua syntax / APPR row)",
     "ft_mirror_gen.py", SCRIPTS, ["nil 安全闸过", "布尔入数值闸过"]),
    ("2/8 mirror vs FT cross-validation",
     "verify_mirror.py", SCRIPTS, ["一致"]),
    ("3/8 first-frame simulation (V pre-seeded to 0)",
     "test_first_frame.py", SCRIPTS, ["453"]),
    ("4/8 APPR print-path gate (prefix args guarded / specs == _num)",
     "test_appr_print.py", SCRIPTS, ["PASS"]),
    ("5/8 generated<->parser contract gate",
     "test_appr_contract.py", SCRIPTS, ["契约"]),
    ("6/8 parser selftest (multi-cid / run split / truncated rows)",
     "test_parse_telemetry.py", SCRIPTS, ["SELFTEST: PASS"]),
]


def run(title, args, cwd, must_contain=None):
    print("=" * 74)
    print("[*]", title)
    print("  $", " ".join(args))
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    out = (r.stdout or "") + (r.stderr or "")
    for line in out.rstrip().split("\n"):
        print("   ", line)
    if r.returncode != 0:
        print("[FAIL] 退出码 %d" % r.returncode)
        return False
    if must_contain:
        for token in must_contain:
            if token not in out:
                print("[FAIL] 输出中缺少必须出现的标记 %r（闸可能退化成了空转）" % token)
                return False
    print("[OK]")
    return True


def main():
    py = sys.executable
    steps = [(t, [py, os.path.join(d, f)], d, mc) for (t, f, d, mc) in STEPS]
    steps.append(("7/8 inject into addon (--inplace; proxy-read + idempotency gates)",
                  [py, os.path.join(MFD, "build_mirror_addon.py"), "--inplace"],
                  MFD, ["APPR 行完整性闸过"]))
    steps.append(("8/8 addon into XML (dry-run; confirm mirror present)",
                  [py, os.path.join(MFD, "build_patch.py")],
                  MFD, ["镜像已带"]))

    for title, args, cwd, mc in steps:
        if not run(title, args, cwd, mc):
            print()
            print("=" * 74)
            print("[FAIL] 第 %r 道闸未过 —— 不要执行 --apply / 不要飞。" % title)
            return 1
    print()
    print("=" * 74)
    print("[OK] 八道闸全过。发车顺序（缺一不可）：")
    print("    python analysis/mfd-lua/build_patch.py --apply   # 写进游戏本体（自动备份 .orig）")
    print("    冷启动游戏 -> 机库出击（不是设计器试飞）-> 一局带 7 的近场守卫飞")
    print("    python analysis/scripts/parse_telemetry.py       # 出 telemetry*.csv 与 telemetry.appr*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
