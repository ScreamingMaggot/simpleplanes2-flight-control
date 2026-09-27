#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 ft_ta2_patch 的 PANEL 生成 Lua 镜像（**同一份式子**，同步由构造保证）。

用户 2026-09-27 的核心痛点：
  setter 值无法写日志；Label 只能人眼读数 ⇒ 样本离散、耗时、易误判。
本模块的答案：**读不到就复算**（telemetry-addon.lua 的 FT8 已有成功先例），
且**不手抄**——由生成器从 PANEL 机械翻译 ⇒ 从根上消灭"镜像与面板错位"
（ftlite_probe 的 ALARM 镜像就是被手抄错位坑过的）。

用法：
  python ft_mirror_gen.py            # 默认只镜像进近关键量（M3/M4 用）
  python ft_mirror_gen.py --all      # 全量 456 条
  python ft_mirror_gen.py --out X.lua
"""
import argparse
import importlib.util
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ft_to_lua as T   # noqa: E402


def load_patch():
    """载入 ft_ta2_patch（唯一真源），拿到 PANEL 与执行器式。"""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ft_ta2_patch.py")
    spec = importlib.util.spec_from_file_location("ft_ta2_patch", p)
    m = importlib.util.module_from_spec(spec)
    saved = sys.argv[:]
    sys.argv = [sys.argv[0]]      # 防止把 --all 之类传给它的顶层参数解析
    try:
        spec.loader.exec_module(m)
    finally:
        sys.argv = saved
    return m


# ── 镜像范围 ────────────────────────────────────────────────────────────────
# M3/M4（进近/航段/盘旋/五边）的关键内部量。全是几何+比较+少量平滑 ⇒ 可精确镜像。
# 顺序无关（求值按面板自身顺序），但列在此处便于人读。
MIRROR_KEYS = [
    # 识别与选择链（选哪条跑道）
    "SD", "LT", "TLA", "HDG", "BRG", "rwyOk", "rwyPri", "SLK",
    # M3 点目标识别 + 航段几何（**这是崩掉六版的那一块**）
    "DS0", "BG0",
    # 航迹/风/横偏
    "trkNow", "trkGd", "trkUse", "CRAB", "XW", "HW", "xtrk", "trkEr",
    "Rturn", "LEAD", "bankTrk",
    # 垂直环（v2.32~34 最贵的教训：看不见 vsCmd/cmdThe 就别改）
    "altTgt", "tanG", "fldE", "htExcess", "vsLine", "vsCmd", "vsErr", "vsInt",
    "cmdTheF_P", "cmdTheF_I", "cmdTheF", "cmdThe",
    # 横向指令
    "cmdPhi", "phiCmdF", "phiCmd",
    # 能量环（油门/减速板/反推三通道）
    "VAPP", "airFly", "gndIdle", "thrErr", "thrInt", "thrPath", "thrPI", "thrCmd", "thrNow",
    "spdBrk", "revOn",
    # 构型
    "appr", "gearCmd", "brkT", "brkLvl", "brkCmd", "gearUp", "lgWarn",
    # 门控
    "boot", "airb", "hold", "RCAP", "vsLim", "airEver",
]

# 镜像**必须排除**的量：含 ActivateN 或依赖面板上下文读不到的名字 ⇒ 与真值必然不同，
# 混进日志会制造假证据（比没有数据更坏）。
MIRROR_BAN = {"SLK", "thrNow"}


def build(panel, keys, all_keys=False):
    exprs = dict(panel)
    order = [n for n, _ in panel]
    if all_keys:
        sel = order
    else:
        sel = [k for k in order if k in set(keys)]
    sel_set = set(sel)

    # 依赖闭包：镜像一条，它引用的自定义 setter 也得镜像（否则 V.x 是 nil）。
    # 反复迭代到不动点 —— 这是"必须给出全套依赖"的机械化版本，防手漏。
    changed = True
    while changed:
        changed = False
        for n in list(sel_set):
            for tok in re.findall(r"[A-Za-z_]\w*", exprs.get(n, "")):
                if tok in T.FT_BUILTIN or tok in sel_set or tok not in exprs:
                    continue
                if re.match(r"(?i)^activate\d+$", tok):
                    continue
                sel_set.add(tok)
                changed = True

    sel = [n for n in order if n in sel_set]

    # ── 逐条翻译。有状态函数已由翻译器**内联**成 `_rate(...)`/`_sum(...)`/`_smooth(...)`
    #    调用（自包含：内部更新状态并返回）⇒ 每条 setter 恰好一条赋值语句，
    #    不存在"更新语句与赋值语句互相覆盖"的旧 bug。 ──
    lines = []
    n_state = 0
    for n in sel:
        lua, st, _aud = T.transpile_full(exprs[n], n)
        lines.append((n, lua))
        n_state += len(st)
    # 依赖闭包后仍引用未镜像名字 = 闭包有洞，显式炸掉，不要留 nil 上机。
    for n, lua in lines:
        for tok in re.findall(r"V\.(\w+)", lua) + re.findall(r"""V\[['"](\w+)['"]\]""", lua):
            if tok not in sel_set:
                raise T.TranspileError("镜像 %s 引用了未镜像的 %s（闭包有洞）" % (n, tok))
    return sel, lines, n_state


def render(panel, keys, all_keys=False, tpl_path=None):
    """产出完整的 Lua 镜像源串。"""
    if tpl_path is None:
        tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "ft_mirror_runtime.lua.tpl")
    tpl = io.open(tpl_path, encoding="utf-8").read()

    # 降级安全性机械门（类型推断，不靠人眼）：本项目为"静默错值"付过 6 个架次。
    bad, _flagged = T.audit_panel_bool_conditions(panel)
    if bad:
        raise T.TranspileError("三元降级不安全（条件非布尔）：%s" % (bad[:5],))

    sel, lines, n_state = build(panel, keys, all_keys)

    # 求值体：按面板/依赖顺序，每条一条赋值。有状态调用已内联在式子里。
    ev = "\n".join('  V["%s"] = %s' % (n, lua) for n, lua in lines)
    ev = "-- 有状态调用点（rate/sum/smooth）共 %d 个，各有独立状态格\n%s" % (n_state, ev)

    out = tpl.replace("__MIRROR_EVAL__", ev)
    out = out.replace("__MIRROR_BODY__", "-- （内置量快照已在 M.step 顶部填写，无需额外 body）")
    # V 表键名清单：供 step() 首帧把每条预置 0（FT 引擎的 setter 初值就是 0；
    # 空表会让自参照 setter 首帧读到 nil ⇒ nil 算术抛错，见 tpl 里的长注）。
    vkeys = "{" + ", ".join('"%s"' % n for n, _ in lines) + "}"
    out = out.replace("__VKEYS__", vkeys)
    check_bool_coercion(out)
    check_nil_safety(out, sel)
    return out, sel


def _split_top_args(s):
    """按顶层逗号切分实参串。"""
    out, d, cur = [], 0, []
    for ch in s:
        if ch == "(":
            d += 1
        elif ch == ")":
            d -= 1
        if ch == "," and d == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def check_bool_coercion(lua_src):
    """**布尔入数值闸**（2026-09-27 第四次架次事故的机械防复发）。

    FT 有 bool→数隐式转换（`clamp01(MU12 > 0.5)` 合法）；Lua **没有**：
        math.min(1, true) → bad argument #2 to 'min' (number expected, got boolean)
    ⇒ 翻译器给每个数值函数实参套 `_n()`。本闸核对：数值函数的**直接实参**里
    不得出现裸比较式，除非被 `_n(` 包住。

    ⚠ 只查**直接实参**：若实参本身是另一个函数调用（如 `math.max(0, math.min(1, _n(x)))`），
      那是内层调用自己的事，本层不该管——第一版没做这层区分，把已正确包裹的式子
      全报成假阳性（满屏 12 条，全是 `_n(` 已包住的）。
    """
    probs = []
    numfns = ("math.min", "math.max", "math.abs", "math.floor", "math.ceil",
              "math.sqrt", "math.rad", "math.sin", "math.cos", "math.tan",
              "math.asin", "math.acos", "math.atan")
    for ln, line in enumerate(lua_src.split("\n"), 1):
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        for fn in numfns:
            k = 0
            while True:
                k = line.find(fn + "(", k)
                if k < 0:
                    break
                a0 = k + len(fn) + 1
                d, i = 1, a0
                while i < len(line) and d > 0:
                    if line[i] == "(":
                        d += 1
                    elif line[i] == ")":
                        d -= 1
                    i += 1
                inner = line[a0:i - 1]
                k = i if i > k else k + 1
                for a in _split_top_args(inner):
                    a = a.strip()
                    if not a:
                        continue
                    if not re.search(r"(<|>|~=|==|!=)", a):
                        continue          # 不含比较 ⇒ 无论怎样都是数值，安全
                    # 剥外层括号
                    st, changed = a, True
                    while changed and st.startswith("(") and st.endswith(")"):
                        changed = False
                        d2, ok = 0, True
                        for j, ch in enumerate(st):
                            if ch == "(":
                                d2 += 1
                            elif ch == ")":
                                d2 -= 1
                                if d2 == 0 and j != len(st) - 1:
                                    ok = False
                                    break
                        if ok:
                            st = st[1:-1].strip()
                            changed = True
                    if st.startswith("_n("):
                        continue              # 已包裹 ✓
                    # 实参本身是另一个数值函数调用 ⇒ 交给内层那次检查判断（见函数注释）
                    if any(st.startswith(f2 + "(") for f2 in numfns):
                        continue
                    probs.append("第 %d 行 %s(…) 的实参未做布尔转换：%s" % (ln, fn, a[:68]))
    if probs:
        raise SystemExit("布尔入数值闸不过（Lua 会抛 number expected, got boolean）：\n  "
                         + "\n  ".join(probs[:12]))
    print("布尔入数值闸过：数值函数实参均经 _n() 或本就是数值式")


def check_nil_safety(lua_src, sel):
    """**nil 安全闸**（2026-09-27 第五架次事故的机械防复发）。

    背景：FT 引擎里 setter 初值 = **0**；镜像 V 是空表 ⇒ 首帧读到 nil。
    加上 Lua 的 `and/or` 三元降级遇到 nil 会**静默传递**（nil 当假值继续 or），
    最终在某个算术处才爆——报错行与真因常常不在一处（第五局：报 1162 行，
    真因是自参照 `cmdTheF_I` 读自己）。

    本闸做两件事：
      ① **拓扑**：每条 `V[x] = …` 引用的 `V.y` 必须已在本条**之前**赋值；
         自参照（引用自己）单独列出——那是合法的（§27b），但**必须**靠 V 预置 0 兜底，
         故必须有 `__VKEYS__` 预置机制存在。
      ② **确认预置机制在**：生成物里必须出现 `for _, k in ipairs(` 的 V 预置语句。
    """
    evals = re.findall(r'^\s*V\["(\w+)"\]\s*=\s*(.*)$', lua_src, re.M)
    idx = {n: i for i, (n, _) in enumerate(evals)}
    probs, selfrefs, missing, forward = [], [], [], []
    for i, (n, e) in enumerate(evals):
        for ref in sorted(set(re.findall(r"\bV\.(\w+)", e))):
            if ref == n:
                selfrefs.append(n)
            elif ref not in idx:
                missing.append((n, ref))
            elif idx[ref] > i:
                forward.append((n, ref))
    for n, r in missing:
        probs.append("%s 引用了**不在镜像里**的 %s（V 表里永不会赋值）" % (n, r))
    for n, r in forward:
        probs.append("%s 引用了**排在它之后**的 %s（前向引用 ⇒ 首帧 nil）" % (n, r))
    # 自参照必须有 V 预置兜底
    if selfrefs and "for _, k in ipairs(" not in lua_src:
        probs.append("存在自参照 setter %s，但生成物没有 V 表预置 0 的语句 "
                     "⇒ 首帧读到 nil 会抛 arithmetic on a nil value" % sorted(set(selfrefs)))
    if probs:
        raise SystemExit("nil 安全闸不过：\n  " + "\n  ".join(probs[:12]))
    print("nil 安全闸过：%d 条求值无缺失/前向引用；自参照 %s（已由 V 预置 0 兜底）"
          % (len(evals), sorted(set(selfrefs)) or "无"))


def check_lua_syntax(src, label):
    """用**真 Lua 解析器**（luaparser，build_patch.py 同款闸门）静态校验产出。

    为什么必须做：镜像由程序生成、又直接进游戏 Lua 沙箱，语法错会让 **整个 MFD 静默瘫痪**
    （telemetry-addon 全废 = 我们又回到"什么都看不见"）。生成即校验，不靠人眼。
    """
    try:
        from luaparser import ast as _ast
    except ImportError:
        print("WARN: 未装 luaparser，跳过 Lua 语法闸（建议 pip install luaparser）")
        return
    try:
        _ast.parse(src)
    except Exception as e:
        raise SystemExit("LUA 语法闸不过（%s）：%s" % (label, e))
    print("Lua 语法闸过（luaparser）: %s" % label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="镜像全部面板 setter")
    ap.add_argument("--keys", default="", help="逗号分隔的镜像键（覆盖默认集）")
    ap.add_argument("--out", default="ft_mirror.lua")
    args = ap.parse_args()

    m = load_patch()
    keys = set(MIRROR_KEYS)
    if args.keys:
        keys = set(k.strip() for k in args.keys.split(",") if k.strip())
    keys -= MIRROR_BAN

    lua, sel = render(m.PANEL, keys, args.all)
    check_lua_syntax(lua, args.out)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.out)
    io.open(out, "w", encoding="utf-8").write(lua)
    print("镜像 %d/%d 条 -> %s" % (len(sel), len(m.PANEL), out))
    print("含：", ", ".join(sel[:24]), "..." if len(sel) > 24 else "")


if __name__ == "__main__":
    main()
