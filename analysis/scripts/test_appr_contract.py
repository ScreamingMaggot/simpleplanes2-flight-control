#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端闸：**生成物 → parser** 的契约一致性（不依赖游戏、不依赖真日志）。

为什么需要：本轮已两次栽在"生成的东西 parser 读不到"——
  ① 数据行漏了 `APPR,` 前缀（parser 靠行首标记分流 ⇒ 整条流静默消失）；
  ② 表头列数/取数列数错位（CSV 列错位 = 数据看着有、结论全错）。
两者都**不是 Lua 语法错**，luaparser 查不出。本测试用**真实生成物**捏一条 APPR 行，
喂给 parse_telemetry 的分流逻辑，逐列核对回来 —— 契约破了就红。

用法：python test_appr_contract.py
"""
import importlib.util
import io
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MFD = os.path.join(HERE, "..", "mfd-lua")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    gen = load("ft_mirror_gen", os.path.join(HERE, "ft_mirror_gen.py"))
    pt = load("pt", os.path.join(HERE, "parse_telemetry.py"))

    patch = gen.load_patch()
    keys = set(gen.MIRROR_KEYS) - gen.MIRROR_BAN
    lua, sel = gen.render(patch.PANEL, keys, False)

    probs = []

    # ── 1. 生成物里的数据行格式串必须以 APPR, 开头 ──
    # 找 _appr_log 里的 print(string.format("...") —— 镜像本身不含它（那是 addon 侧），
    # 所以直接取 addon 生成器的模板产物。
    bma = load("bma", os.path.join(MFD, "build_mirror_addon.py"))
    block = bma.emit_appr_block(bma.APPR_COLS)
    fm = re.search(r'print\(string\.format\("([^"]*)"', block)
    hm = re.search(r'print\("(APPRHDR[^"]*)"\)', block)
    if not fm or not hm:
        print("FAIL: 模板里找不到格式串或表头")
        return 1
    if not fm.group(1).startswith("APPR,"):
        probs.append("数据行格式串不以 `APPR,` 开头：%r" % fm.group(1)[:30])

    # ── 2. 表头列 == parser 的 APPR_COLS ──
    hcols_full = hm.group(1).split(",")
    hdr_tag, hdr_cid, hdr_t = hcols_full[0], hcols_full[1], hcols_full[2]
    hcols = hcols_full[3:]
    if [hdr_tag, hdr_cid, hdr_t] != ["APPRHDR", "cid", "t"]:
        probs.append("表头前缀异常：%s" % hcols_full[:3])
    if hcols != pt.APPR_COLS[2:]:
        probs.append("表头列与 parser.APPR_COLS 不符\n  生成: %s\n  parser: %s"
                     % (hcols[:6], pt.APPR_COLS[2:8]))
    # parser 的 APPR_COLS 必须以 cid,t 开头
    if pt.APPR_COLS[:2] != ["cid", "t"]:
        probs.append("parser.APPR_COLS 前缀不是 cid,t：%s" % pt.APPR_COLS[:3])

    # ── 3. 格式符个数 == 2(固定) + 列数；取数个数 == 列数 ──
    specs = re.findall(r"%[-+ #0-9.]*[dfsxX]", fm.group(1))
    args = re.findall(r'_num\(V\["(\w+)"\]\)', block)
    if len(specs) != 2 + len(hcols):
        probs.append("格式符 %d ≠ 2 + 表头列 %d" % (len(specs), len(hcols)))
    if len(args) != len(hcols):
        probs.append("取数 %d ≠ 表头列 %d" % (len(args), len(hcols)))
    if args != hcols:
        probs.append("取数名与表头名不一致")

    # ── 4. 端到端：按生成物的格式捏一条行，喂 parser，逐列核对 ──
    # 用确定值：第 i 列 = 100 + i，便于反查列序是否错位
    cid, tval = 777, 123.456
    vals = [100.0 + i for i in range(len(hcols))]
    # 按格式串的类型（%d/%.2f/%.3f）渲染，模拟 Lua string.format
    rendered = []
    spec_i = 0
    for ch_spec in specs:
        v = [cid, tval] + vals
        val = v[spec_i]
        spec_i += 1
        if ch_spec.endswith("d"):
            rendered.append(str(int(val)))
        elif ch_spec.endswith("3f"):
            rendered.append("%.3f" % val)
        else:
            rendered.append("%.2f" % val)
    row = "APPR," + ",".join(rendered)

    tmp = tempfile.mkdtemp(prefix="appr_contract_")
    try:
        log = os.path.join(tmp, "Player.log")
        io.open(log, "w", encoding="utf-8").write("junk\n" + hm.group(1).replace("APPRHDR", "APPR", 1)
                                                  + "\n" + row + "\n")
        streams = pt.parse(log)
        appr = streams["APPR"]
        if 777 not in appr:
            probs.append("端到端：parser 没认出行（行首前 40 字符 = %r）" % row[:40])
        else:
            got = appr[777][0][0]
            if len(got) != len(pt.APPR_COLS):
                probs.append("端到端：解析出 %d 列，期望 %d" % (len(got), len(pt.APPR_COLS)))
            else:
                if int(got[0]) != cid or abs(got[1] - tval) > 1e-6:
                    probs.append("端到端：cid/t 错位 got=%r" % got[:2])
                for i, want in enumerate(vals):
                    if abs(got[2 + i] - want) > 1e-6:
                        probs.append("端到端：第 %d 列（%s）期望 %.2f 得到 %.2f"
                                     % (i, pt.APPR_COLS[2 + i], want, got[2 + i]))
                        break
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    if probs:
        print("APPR 契约闸 不过：")
        for p in probs:
            print("  ✗", p)
        return 1
    print("APPR 契约闸 过：数据行前缀/表头列/格式符/取数/端到端逐列 全部一致")
    print("  列数 %d，示例行前 60 字符：%s" % (len(hcols), row[:60]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
