#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""代理字段安全检查器（**扫全文件**，不只扫镜像块）。

存在理由（2026-09-27，三个架次的代价）：
  CraftProxy / CraftControlsProxy 是 MoonSharp **userdata**，访问不存在的字段
  **抛异常**（不是返回 nil）：
      cannot access field VTOL of userdata<...CraftControlsProxy>
  异常穿透 update() ⇒ 整个 update() 中断 ⇒ **TEL/APPR 双双零数据**。

  上一版闸只扫"我生成的镜像块"⇒ 绿着放行，可 **:805 那处裸读根本不在镜像里**
  （它是既有的 FT8 复算代码，长期被 FT_ONLY 门挡着没执行；我把 _appr_log 挂进
  update() 后改变了执行路径，把它踩响了）。**窄闸 = 闸绿机毁**，故本器扫全文件。

用法：
  python check_proxy_fields.py <lua文件> [...]     # 人读清单
  python check_proxy_fields.py --strict <文件>     # 有裸读即非零退出（供生成期调用）
"""
import io
import re
import sys

# ── 已实测/长期无事的可读字段（可裸读或用 pcall 皆可）──────────────────────
# 证据来源都写在注释里；**没有证据的一律进不了白名单**。
SAFE_FIELDS = {
    "LandingGearDown",   # §30 实测可读（telemetry-addon 原句 tostring(...LandingGearDown) 长期在用）
    "Throttle",          # TEL 行长期在用（telemetry-addon.lua:107-114 的 c.Throttle）
    "Trim",              # 同上
    "Pitch",             # 同上
    "Roll",              # 同上
    "Yaw",               # 同上
    # Flaps：**故意不列入**——它在 addon:778/1168 历来包着 pcall 用，说明作者当年也不确定。
    # VTOL / Vtol：**已证不可读**（本轮事故），绝不可列。
}

# 已知不可读（明确记录，供报错文案更准确）
KNOWN_BAD = {"VTOL", "Vtol"}

# 只读方法（非字段访问，安全）
METHOD_OK = {"OverrideInput", "ReleaseInput", "GetActivationState", "NextTarget",
             "PreviousTarget"}


def scan_text(src):
    """扫一段 Lua 源码文本，返回 [(行号, 字段名, 行内容, 是否已保护)]。

    跳过 Lua 长注释 `--[[ ... ]]` 与行注释 —— 注释里正当地记着事故原文，
    闸不该把文档当代码判死（本器第一版就踩过这个坑）。
    """
    lines = src.split("\n")
    hits = []
    pat = re.compile(r"(?:craft\s*\.\s*Controls|ctl)\s*\.\s*(\w+)")
    in_block = False
    for n, line in enumerate(lines, 1):
        s = line.strip()
        if in_block:
            if "]]" in s:
                in_block = False
            continue
        if s.startswith("--[["):
            if "]]" not in s:
                in_block = True
            continue
        if s.startswith("--"):
            continue
        for m in pat.finditer(line):
            f = m.group(1)
            if f in METHOD_OK:
                continue
            # 该行是否已被 pcall 包住（保守判定：行内有 pcall( 且字段在 pcall 之后）
            guarded = ("pcall(" in line and line.index("pcall(") < m.start())
            hits.append((n, f, s[:100], guarded))
    return hits


def scan(path):
    """扫一个文件。"""
    return scan_text(io.open(path, encoding="utf-8").read())


def main():
    strict = "--strict" in sys.argv
    files = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not files:
        sys.exit("用法: check_proxy_fields.py [--strict] <lua文件> [...]")

    bad_total = 0
    for path in files:
        hits = scan(path)
        unsafe = [h for h in hits if not h[3] and h[1] not in SAFE_FIELDS]
        print("=== %s ===" % path)
        print("代理字段访问 %d 处；其中**未保护且不在白名单** %d 处"
              % (len(hits), len(unsafe)))
        for n, f, s, g in hits:
            tag = "OK(pcall)" if g else ("OK(白名单)" if f in SAFE_FIELDS
                                         else ("★危险" if f not in KNOWN_BAD else "★已知不可读"))
            print("  %5d  %-18s %-12s | %s" % (n, f, tag, s[:80]))
        if unsafe:
            bad_total += len(unsafe)
            print("  ⚠ 必须处理：")
            for n, f, s, g in unsafe:
                why = "该字段已知不可读" if f in KNOWN_BAD else "无实测可读证据"
                print("    行 %d：%s（%s）" % (n, f, why))
        print()

    if strict and bad_total:
        print("拒绝：仍有 %d 处未保护的代理字段读取（会打死整条 update）" % bad_total)
        return 1
    if bad_total:
        print("提示：%d 处未保护（未加 --strict，仅报告）" % bad_total)
    else:
        print("全部代理字段访问均已保护或在白名单内 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
