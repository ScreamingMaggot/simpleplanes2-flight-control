#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键跑完整条观测链的所有闸（离线，零飞行风险）�?
    python run_all_gates.py

顺序 = 真实交付顺序�?  1. 镜像生成 + Lua 语法�?           ft_mirror_gen.py
  2. 双路径逐点交叉验证（镜�?== 面板）verify_mirror.py
  3. 注入 addon（镜�?+ APPR 三闸�?   build_mirror_addon.py
  4. addon→XML 构建（含语法闸）        build_patch.py（dry-run，不写游戏）
  5. parser 双流自测（合成日志）        test_parse_telemetry.py
  6. 生成物↔parser 契约闸（端到端）    test_appr_contract.py

任何一步非零即停（fail-closed）�?"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MFD = os.path.join(HERE, "..", "mfd-lua")
SCRIPTS = HERE


def run(title, args, cwd, must_contain=None):
    print("=" * 74)
    print("�?, title)
    print(" " * 2, "$", " ".join(args))
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    out = (r.stdout or "") + (r.stderr or "")
    for line in out.rstrip().split("\n"):
        print("   ", line)
    if r.returncode != 0:
        print("�?退出码 %d" % r.returncode)
        return False
    if must_contain:
        for token in must_contain:
            if token not in out:
                print("�?输出里缺少期望标�?%r（闸可能没生效）" % token)
                return False
    print("�?�?)
    return True


def main():
    py = sys.executable
    steps = [
        ("1/7 镜像生成 + 语法/布尔/nil 三闸", [py, os.path.join(SCRIPTS, "ft_mirror_gen.py")],
         SCRIPTS, ["nil 安全闸过", "布尔入数值闸�?]),
        ("2/7 双路径逐点交叉验证", [py, os.path.join(SCRIPTS, "verify_mirror.py")],
         SCRIPTS, ["逐点数值相�?]),
        ("3/7 首帧仿真（V 预置 0 / nil 修复的正面证据）",
         [py, os.path.join(SCRIPTS, "test_first_frame.py")],
         SCRIPTS, ["453 条全部求值成�?]),
        ("4/7 注入 addon（镜�?+ APPR 四闸�?,
         [py, os.path.join(MFD, "build_mirror_addon.py"), "--inplace"],
         MFD, ["APPR 行完整性闸�?]),
        ("5/7 addon→XML 构建（dry-run，不写游戏）",
         [py, os.path.join(MFD, "build_patch.py")],
         MFD, ["镜像已带"]),
        ("6/7 parser 双流自测", [py, os.path.join(SCRIPTS, "test_parse_telemetry.py")],
         SCRIPTS, ["SELFTEST: PASS"]),
        ("7/7 生成物↔parser 契约�?, [py, os.path.join(SCRIPTS, "test_appr_contract.py")],
         SCRIPTS, ["APPR 契约�?�?]),
    ]
    for title, args, cwd, mc in steps:
        if not run(title, args, cwd, mc):
            print()
            print("=" * 74)
            print("�?链在�?s」断�?—�?不要 --apply / 不要上机，先修这里�? % title)
            return 1
    print()
    print("=" * 74)
    print("�?六道闸全过。下一步（需你操作）�?)
    print("    python build_patch.py --apply      # 写进游戏本体（自动备�?.orig�?)
    print("    冷启动游�?�?机库出击（不是设计器试飞）→ 一局守卫�?)
    print("    python parse_telemetry.py          # �?telemetry*.csv �?telemetry.appr*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
