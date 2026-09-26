#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 FT 面板镜像拼进 telemetry-addon.lua（产出可 build_patch 的整份 addon）。

背景（用户 2026-09-27 的核心痛点）：
  setter 值**没有任何落盘通道**——FT 无 print、CraftProxy 无变量袋、Label 只能人眼读。
  唯一可行的自动化观测 = **在 Lua 里按同一条式子复算**（telemetry-addon 的 FT8 已有先例），
  而"手抄式子"必然错位 ⇒ 本工具从 ft_ta2_patch.PANEL **机械生成**镜像，
  再拼进 addon，并每帧打一行 `APPR` 把 M3/M4 的进近内部量全部落盘。

用法：
  python build_mirror_addon.py            # 生成 telemetry-addon.mirrored.lua（不动原文件）
  python build_mirror_addon.py --inplace  # 直接覆盖 telemetry-addon.lua（先备份 .premirror）
"""
import argparse
import importlib.util
import io
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)


def load(mod_name, path):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# APPR 行要落盘的列（顺序即列序）。全部来自镜像 V 表。
APPR_COLS = [
    "SD", "LT", "TLA", "HDG", "BRG",          # 选中/锁定跑道的几何
    "rwyOk", "rwyPri",                         # 选择链状态
    "xtrk", "trkEr", "trkUse", "trkGd",        # 横偏与航迹
    "LEAD", "bankTrk", "phiCmd", "cmdPhi",     # 横向律
    "htExcess", "altTgt", "vsCmd", "vsErr",    # 纵向/能量
    "tanG", "fldE", "vsLine",
    "thrCmd", "thrPI", "thrErr", "spdBrk",     # 能量环
    "airFly", "gndIdle", "revOn",              # 门
    "SLK",                                     # 跑道锁（注意：镜像里 Activate7=0 ⇒ 恒 −1，见文件头注释）
    "appr", "gearCmd", "brkCmd", "brkLvl",     # 构型
    "RCAP", "boot", "airb", "hold",            # 门控
]


def emit_appr_block(cols):
    """生成 APPR 行的 Lua 代码块（含表头与取数）。"""
    fmt = ",".join(["%d", "%.3f"] + ["%.2f"] * len(cols))
    args = ",\n\t\t\t".join('_num(V["%s"])' % c for c in cols)
    hdr = "APPRHDR,cid,t," + ",".join(cols)
    return """
-- ==== APPR：FT 进近面板内部量落盘（由 ft_mirror_gen.py 机械生成，勿手改）====
-- setter 无日志通道 ⇒ 在 Lua 里按**同一条式子**复算并打印（同 FT8 复算的先例）。
-- 与面板的同步**由构造保证**（同一份 PANEL 翻译而来）；漂移只可能来自 sum/smooth/rate
-- 的初值（镜像从启用那帧起算，面板可能更早）⇒ 看数据时以稳态段为准。
local _apfr = 0
local function _num(x)
	if x == nil then return -99999 end
	if type(x) ~= "number" then return x and 1 or 0 end
	if x ~= x then return -99999 end            -- NaN 哨兵
	return x
end
local function _appr_hdr() print("%s") end
local function _appr_log()
	_apfr = _apfr + 1
	if math.fmod(_apfr, 6) ~= 0 then return end   -- 6 分频（约 10~20 Hz，与 TEL 同量级）
	local V = _ftmirror.step()
	print(string.format("APPR,%s",
		_cidn, craft.Time,
		%s))
end
""" % (hdr, fmt, args)


def check_definition_order(src):
    """**词法作用域闸**：`local` 只对其后的代码可见。

    第一版把镜像插在 `update()` 之后 ⇒ update 里调用的 `_appr_log`/`_ftmirror` 是 nil，
    每帧 `attempt to call a nil value`——**语法闸查不出这种错**（luaparser 只看语法）。
    此处显式核对：定义行号必须早于使用行号。
    """
    lines = src.split("\n")
    def first(pred):
        for i, l in enumerate(lines):
            if pred(l):
                return i + 1
        return None
    d_mirror = first(lambda l: l.startswith("local _ftmirror"))
    d_appr = first(lambda l: l.startswith("local function _appr_log"))
    u_appr = None
    for i, l in enumerate(lines):
        if "_appr_log()" in l and "function" not in l:
            u_appr = i + 1
            break
    d_update = first(lambda l: l.startswith("function update()"))
    problems = []
    if None in (d_mirror, d_appr, u_appr, d_update):
        problems.append("定位失败 mirror=%s appr=%s use=%s update=%s"
                        % (d_mirror, d_appr, u_appr, d_update))
    else:
        if d_mirror > u_appr:
            problems.append("_ftmirror 定义(%d) 晚于使用(%d)" % (d_mirror, u_appr))
        if d_appr > u_appr:
            problems.append("_appr_log 定义(%d) 晚于使用(%d)" % (d_appr, u_appr))
        if d_mirror > d_update:
            problems.append("_ftmirror 定义(%d) 晚于 update 定义(%d)" % (d_mirror, d_update))
    if problems:
        raise SystemExit("词法作用域闸不过：%s" % "; ".join(problems))
    print("词法作用域闸过：_ftmirror@%d _appr_log@%d 使用@%d update@%d"
          % (d_mirror, d_appr, u_appr, d_update))


def check_appr_row(src):
    """**行完整性闸**：APPR 的格式符个数、表头列数、取数列数三者必须一致。

    为什么必须有：CSV 列错位是"数据看着有、结论全错"的经典来源；而 `print(format, …)`
    参数少了 Lua 直接运行时报错、多了则静默丢列——两者都够隐蔽，必须在生成期拦下。
    """
    i = src.find("local function _appr_log")
    if i < 0:
        raise SystemExit("APPR 块缺失")
    blk = src[i:i + 4000]
    fm = re.search(r'print\(string\.format\("([^"]*)"', blk)
    hm = re.search(r'print\("(APPRHDR[^"]*)"\)', src)
    args = re.findall(r'_num\(V\["(\w+)"\]\)', blk)
    if not fm or not hm:
        raise SystemExit("APPR 格式串或表头缺失（format=%s hdr=%s）"
                         % (bool(fm), bool(hm)))
    specs = re.findall(r"%[-+ #0-9.]*[dfsxX]", fm.group(1))
    hcols = hm.group(1).split(",")[3:]          # 去掉 **3** 个前缀字段：APPRHDR,cid,t
    probs = []
    if len(specs) != 2 + len(args):
        probs.append("格式符 %d ≠ 2(固定列) + 取数 %d" % (len(specs), len(args)))
    if hcols != args:
        probs.append("表头列 %d ≠ 取数列 %d%s"
                     % (len(hcols), len(args),
                        ("；首个不同: %s vs %s"
                         % (next((a for a, b in zip(hcols, args) if a != b), "?"),
                            next((b for a, b in zip(hcols, args) if a != b), "?")))))
    if "_appr_hdr()" not in src:
        probs.append("表头函数 _appr_hdr() 从未被调用（CSV 会没有列名）")

    # ★分流前缀闸：parser 靠**行首标记**分流（TEL,/APPR,）。数据行若不带 `APPR,`
    #   前缀，parse_telemetry 永远匹配不到 ⇒ **整条流静默消失**（第一版正是如此：
    #   只有表头是 APPRHDR，数据行是裸 `%d,%.3f,…`）。此处与 parser 的期望逐字对齐。
    if not fm.group(1).startswith("APPR,"):
        probs.append("数据行格式串未以 `APPR,` 开头（实际 %r）⇒ parser 分流不到"
                     % fm.group(1)[:24])
    if not hm.group(1).startswith("APPRHDR,"):
        probs.append("表头未以 `APPRHDR,` 开头")

    if probs:
        raise SystemExit("APPR 行完整性闸不过：%s" % "；".join(probs))
    print("APPR 行完整性闸过：%d 列（表头/格式符/取数三者一致），"
          "数据行带 `APPR,` 前缀，表头已挂 initialize" % len(args))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inplace", action="store_true")
    ap.add_argument("--cols", default="", help="逗号分隔，覆盖 APPR 列集")
    args = ap.parse_args()

    gen = load("ft_mirror_gen", os.path.join(SCRIPTS, "ft_mirror_gen.py"))
    patch = gen.load_patch()
    keys = set(gen.MIRROR_KEYS) - gen.MIRROR_BAN

    lua, sel = gen.render(patch.PANEL, keys, False)
    gen.check_lua_syntax(lua, "ft_mirror.lua")

    # 镜像文件：包成 `local _ftmirror = (function() ... end)()` 以便内联进 addon
    body = lua.replace("return M", "return M", 1)
    mirror_mod = "-- ==== 面板镜像（自动生成：ft_mirror_gen.py）====\nlocal _ftmirror = (function()\n%s\nend)()\n" % body

    cols = [c.strip() for c in args.cols.split(",") if c.strip()] or APPR_COLS
    cols = [c for c in cols if c in sel]
    block = emit_appr_block(cols)

    addon_path = os.path.join(HERE, "telemetry-addon.lua")
    src = io.open(addon_path, encoding="utf-8").read()

    # 幂等：先剥掉上一次的注入块（以标记注释界定）
    src = re.sub(r"\n-- ==== 面板镜像（自动生成.*?-- ==== /面板镜像 ====\n", "\n", src, flags=re.S)
    src = re.sub(r"\n-- ==== APPR：FT 进近面板内部量落盘.*?-- ==== /APPR ====\n", "\n", src, flags=re.S)

    mirror_mod = "-- ==== 面板镜像（自动生成：ft_mirror_gen.py）====\n" + \
                 "local _ftmirror = (function()\n" + body + "\nend)()\n-- ==== /面板镜像 ====\n"
    block = block + "-- ==== /APPR ====\n"

    # ★注入点必须在 **update() 定义之前**（Lua 是词法作用域：`local` 只对其**之后**的代码可见。
    #   第一版把镜像插在 update 之后 ⇒ update 里的 `_appr_log()` 与 `_ftmirror` 全是 nil，
    #   每帧 `attempt to call a nil value`。此处以文件开头的 `local _frame = 0` 为锚，
    #   把镜像与 APPR 定义整体插在它**之前**。）
    anchor = "local _origInitialize = initialize"
    if anchor not in src:
        sys.exit("注入锚未找到（addon 头部结构变了？）")
    src = src.replace(anchor, mirror_mod + "\n" + block + "\n" + anchor, 1)

    # 在 update() 内的 TEL/FT8 打印之后调用 _appr_log()。
    m2 = re.search(r"\n(\t*)(-- FT8 定高环内部量：.*?\n\t*print\(string\.format\("
                   r"\"FT8,.*?\n\t*end\n)", src, re.S)
    if not m2:
        sys.exit("APPR 调用点未找到（FT8 打印块定位失败）")
    indent = m2.group(1)
    src = src[:m2.end(1)] + "\n%s_appr_log()\n" % indent + src[m2.end(1):]

    # 表头必须在 initialize() 里打一次（否则 CSV 无列名）。挂到 TELHDR 那行之后。
    m3 = re.search(r"(\n\t*print\(\"TELHDR[^\n]*\n)", src)
    if not m3:
        sys.exit("TELHDR 定位失败（无法挂 APPRHDR）")
    src = src[:m3.end(1)] + "\t_appr_hdr()\n" + src[m3.end(1):]

    gen.check_lua_syntax(src, "telemetry-addon+mirror")
    check_definition_order(src)
    check_appr_row(src)

    if args.inplace:
        bak = addon_path + ".premirror"
        if not os.path.exists(bak):
            shutil.copy2(addon_path, bak)
            print("备份 ->", os.path.basename(bak))
        io.open(addon_path, "w", encoding="utf-8").write(src)
        print("已写入", os.path.basename(addon_path))
    else:
        out = os.path.join(HERE, "telemetry-addon.mirrored.lua")
        io.open(out, "w", encoding="utf-8").write(src)
        print("已写入", os.path.basename(out), "（未动原文件；--inplace 才覆盖）")
    print("镜像 %d 条；APPR 列 %d 个：%s" % (len(sel), len(cols), ",".join(cols)))


if __name__ == "__main__":
    main()
