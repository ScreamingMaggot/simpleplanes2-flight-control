#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FT 表达式 → Lua 表达式翻译器（单一真源的执行者）。

**存在理由**（2026-09-27，用户点破的真问题）：
  面板 setter 由游戏表达式引擎求值，**从不写进 Player.log**；CraftProxy 也没有变量袋，
  Lua 读不到。Label 是唯一窗口，而要人眼读数 ⇒ 样本离散、易误判。
  telemetry-addon.lua 里已有一条成功先例（FT8 定高环"复算"，见该文件 §24-33）：
  **读不到就按同一条式子复算**，把内部量打进日志。

  但手抄式子 = 必然错位（ftlite_probe 的 ALARM 镜像就被这个坑过："镜像与 FT 同表同式，
  差值即烘焙错位"）。⇒ 本模块把 ft_ta2_patch.py 的 PANEL **同一份式子**机械翻译成 Lua，
  由同一个脚本同时产出 FT 面板与 Lua 镜像 ⇒ **同步由构造保证**，不靠人工核对。

翻译规则（FT 白名单 → Lua）：
  运算符：`=`→`==`、`&`→`and`、`|`→`or`、`!`→`not`、`!=`→`~=`（其余 + - * / % > < >= <= ?: 同形）
  三元   ：`A ? B : C` → `(A) and (B) or (C)`  ← 注意 False=−1 的 FT 约定，见 _bool_convention
  函数   ：clamp/clamp01/smooth/sum/rate/PID/deltaangle/lerp/lerpangle/sign/repeat 需 shim
内置变量：直接读快照表 `S`（由 Lua 每帧从 craft 代理与 Controls 填好）

⚠ 本翻译器**只保证语法与函数语义**；`sum`/`smooth`/`rate` 是**有状态**的，Lua 侧必须
  自己维护状态，且初值与面板一致才不漂。见 emit_mirror() 的 stateful 处理与文档 §漂移。
"""
import re

# ── FT 内置常量/变量名（照 ft_ta2_patch.BUILTIN 抄；翻译时原样读快照）──────────
FT_BUILTIN = set("""Activate1 Activate2 Activate3 Activate4 Activate5 Activate6 Activate7 Activate8
Altitude AltitudeAgl AngleOfAttack AngleOfSlip Brake FireGuns FireWeapons Flaps Fuel GForce GS
GearDown Heading IAS LandingGear Latitude Longitude Pitch PitchAngle PitchRate Roll RollAngle
RollRate TAS TargetDistance TargetElevation TargetHeading TargetSelected Throttle Time Trim VTOL
VerticalG Yaw YawRate""".split())

# ── FT 函数 → Lua 表达式模板 ────────────────────────────────────────────────
# 逐条在这里声明"这个 FT 函数在 Lua 里怎么算"。**没有条目 = 拒绝翻译**（宁可报错也不静默出错）。
# 占位符：{0}/{1}/… 取第 n 个实参；{*} = 全部实参逗号连接（变参函数用）。
SIMPLE_FUNCS = {
    "abs":      "math.abs({0})",
    "sqrt":     "math.sqrt({0})",
    "sin":      "math.sin(math.rad({0}))",     # FT 三角吃**度**（atan2 出参为度，见 platform-facts）
    "cos":      "math.cos(math.rad({0}))",
    "tan":      "math.tan(math.rad({0}))",
    "asin":     "math.deg(math.asin({0}))",
    "acos":     "math.deg(math.acos({0}))",
    "atan":     "math.deg(math.atan({0}))",
    # ★FT `atan2(y, x)` 出参是**度**。Lua 的 `math.atan(y, x)` 出参是**弧度**
    #   ⇒ 必须包一层 math.deg，且**只包一层**。实参顺序与 FT 相同，不要交换。
    #   两处前科（都被 verify_mirror 的逐点比对抓出）：
    #     ① 写成 `math.atan({1}, {0})` = 参数对调；
    #     ② 写成 `math.atan({0},{1})` 而忘了 deg ⇒ 弧度当度用。
    "atan2":    "math.deg(math.atan({0}, {1}))",
    "floor":    "math.floor({0})",
    "ceil":     "math.ceil({0})",
    "round":    "math.floor({0} + 0.5)",
    "min":      "math.min({*})",
    "max":      "math.max({*})",
    "clamp":    "math.max(({1}), math.min(({2}), ({0})))",
    "clamp01":  "math.max(0, math.min(1, ({0})))",
    "sign":     "(({0}) > 0 and 1 or (({0}) < 0 and -1 or 0))",
    "pow":      "(({0}) ^ ({1}))",
    "lerp":     "(({0}) + ((({1}) - ({0})) * ({2})))",
    # deltaangle(a,b) = Mathf 惯例 norm(b−a)，结果落在 ±180（platform-facts §21 实锤）
    "deltaangle": "((( ({1}) - ({0}) ) + 180) % 360 - 180)",
    "lerpangle":  "(({0}) + deltaangle({0}, {1}) * ({2}))",
}
# 实参个数守卫：(最少, 最多)；None = 不限
ARITY = {"abs": (1, 1), "sqrt": (1, 1), "sin": (1, 1), "cos": (1, 1), "tan": (1, 1),
         "asin": (1, 1), "acos": (1, 1), "atan": (1, 1), "atan2": (2, 2),
         "floor": (1, 1), "ceil": (1, 1), "round": (1, 1),
         "min": (2, None), "max": (2, None), "clamp": (3, 3), "clamp01": (1, 1),
         "sign": (1, 1), "pow": (2, 2), "lerp": (3, 3),
         "deltaangle": (2, 2), "lerpangle": (3, 3)}
# 有状态函数：翻译成对镜像状态表的读写（见 emit_mirror）
STATEFUL_FUNCS = {"sum", "rate", "smooth", "PID"}


class TranspileError(Exception):
    pass


def _is_literal_false(lua_expr):
    """Lua 表达式是否可能求值为 nil/false（and/or 降级的杀手）。"""
    s = lua_expr.strip()
    return s in ("false", "nil")


# 已知的布尔产出形态：比较、and/or/not 复合、以及布尔比较函数。用于"条件必须真布尔"的守卫。
_BOOL_RE = re.compile(
    r"(<|>|~=|==|!=)"                      # 比较
    r"|(^|\W)(and|or|not)(\W|$)"           # 逻辑复合
    r"|(^|\W)(TargetSelected|TargetLocked|TargetLocking|trkGd)(\W|$)"  # 已知布尔量
)


def _looks_boolean(lua_expr):
    return bool(_BOOL_RE.search(lua_expr))


def audit_panel_bool_conditions(panel):
    """**降级安全性审计**（机械门，不靠人眼）：

    `and/or` 降级要求每个三元条件在运行时是**真布尔**。面板里大量条件是 setter 名引用
    （`KP0 ? SD0 : …`），翻译器看不见它们背后的类型 ⇒ 在此做**跨 setter 类型推断**：
    一个 setter 是布尔的充要条件 = 其 FT 式子顶层是 `& | !` 复合或比较。

    返回 (bad, flagged)。bad 非空 ⇒ 降级不安全，**拒绝产出镜像**。
    本函数存在的理由：本项目为"静默错值"付过 6 个架次；类型假设必须是可执行的检查。
    """
    exprs = dict(panel)
    flagged = set()
    for n, e in panel:
        _, _, aud = transpile_full(e, n)
        for c in aud["nonbool_conds"]:
            mm = re.match(r"V\.(\w+)$", c.strip())
            if mm:
                flagged.add(mm.group(1))
    bad = []
    for n in sorted(flagged):
        if n not in exprs or not _ft_top_is_bool(exprs[n]):
            bad.append((n, exprs.get(n, "<未定义>")))
    return bad, sorted(flagged)


def _ft_top_is_bool(e):
    """FT 式子是否布尔值（顶层 `& | !` 或比较）。用于跨 setter 类型推断。"""
    e = e.strip()
    while e.startswith("(") and e.endswith(")"):
        d, ok = 0, True
        for i, ch in enumerate(e):
            if ch == "(":
                d += 1
            elif ch == ")":
                d -= 1
                if d == 0 and i != len(e) - 1:
                    ok = False
                    break
        if not ok:
            break
        e = e[1:-1].strip()
    d = 0
    for ch in e:
        if ch == "(":
            d += 1
        elif ch == ")":
            d -= 1
        elif d == 0 and ch in "&|":
            return True
    return bool(re.search(r"(<|>|!=)", e))




def _tokenize(expr):
    """切词：数字 / 标识符 / 多字符运算符 / 单字符。与 ft_ta2_patch.lint 的字符白名单同源。"""
    toks, i, n = [], 0, len(expr)
    while i < n:
        ch = expr[i]
        if ch in " \t":
            i += 1
            continue
        m = re.match(r"\d+\.?\d*", expr[i:])
        if m:
            toks.append(("num", m.group(0)))
            i += m.end()
            continue
        m = re.match(r"[A-Za-z_]\w*", expr[i:])
        if m:
            toks.append(("id", m.group(0)))
            i += m.end()
            continue
        for op in (">=", "<=", "!="):
            if expr.startswith(op, i):
                toks.append(("op", op))
                i += len(op)
                break
        else:
            toks.append(("op", ch))
            i += 1
    return toks


class _P:
    """递归下降解析器。只处理翻译需要的结构：
       三元(右结合、单层) / 二元(优先级) / 一元 / 函数调用 / 括号 / 原子。
    不做类型检查——FT 是动态类型，翻译保持同构即可。"""

    # 优先级表（照 FT 运算符白名单；数值来自常见表达式语言惯例，仅影响重写括号）
    BIN = [
        ["|"], ["&"], ["=", "!="], [">", ">=", "<", "<="],
        ["+", "-"], ["*", "/", "%"],
    ]

    def __init__(self, toks, varname=""):
        self.t = toks
        self.i = 0
        self.varname = varname
        self.st_n = 0        # 有状态调用计数器（本式子内唯一）
        self.st_info = []    # [(key, funcname, args)] 供 emit_mirror 生成状态声明与更新
        self._cond_kinds = []  # [(cond_lua, looks_bool)] 供静态审计

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def stateful(self, name, args):
        """把 FT 的有状态函数翻成**自包含的 Lua 表达式**（内部更新状态并返回值）。

        FT 语义（platform-facts §1 源码实锤）：
          sum(x)      = value += x*dt （按秒积分）
          rate(x)     = (x − last)/dt （按秒微分，首帧 0）
          smooth(x,t) = MoveTowards(last, x, t*dt)  （限速跟踪，首帧 = x）
          PID(T,C,p,i,d) = p·e + i·Σe·dt + d·(C_last−C)/dt，e = T−C

        ★设计（2026-09-27 修）：**不要**把"更新"与"赋值"拆成两条语句。
        前一版那样做有两个真 bug（已由生成物人眼复核抓到）：
          ① 一条式子里两个 rate() 会先后写同一个 `V['trkNow']` ⇒ 前一个结果被覆盖
             （`atan2(rate(Lon), rate(Lat))` 退化成只剩 rate(Lat)）；
          ② 有状态 setter 被"更新语句"和"普通赋值语句"各写一次 ⇒ 后者用状态格裸值覆盖前者。
        改为内联调用：每个有状态调用点各有独立状态格，表达式即最终值，一条赋值搞定。
        """
        key = "%s__st%d" % (self.varname or "x", self.st_n)
        self.st_n += 1
        self.st_info.append((key, name, args))
        if name == "rate":
            return "_rate(%r, %s, dt)" % (key, args[0])
        if name == "sum":
            return "_sum(%r, %s, dt)" % (key, args[0])
        if name == "smooth":
            return "_smooth(%r, %s, %s, dt)" % (key, args[0], args[1])
        if name == "PID":
            return "_pid(%r, %s, %s, %s, %s, %s, dt)" % (
                key, args[0], args[1], args[2], args[3], args[4])
        raise TranspileError("未处理的有状态函数 %s" % name)

    def parse(self):
        e = self.ternary()
        if self.i != len(self.t):
            raise TranspileError("尾部未消费：%r" % (self.t[self.i:],))
        return e

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expect(self, val):
        k, v = self.take()
        if v != val:
            raise TranspileError("期望 %r，得到 %r" % (val, v))

    def parse(self):
        e = self.ternary()
        if self.i != len(self.t):
            raise TranspileError("尾部未消费：%r" % (self.t[self.i:],))
        return e

    def ternary(self):
        cond = self.binary(0)
        if self.peek()[1] == "?":
            self.take()
            a = self.ternary()
            self.expect(":")
            b = self.ternary()
            # ── and/or 降级的**两个前提**，在此机械守卫（别靠人眼，本项目为"静默错值"付过 6 个架次）──
            # ① 真分支不能是 nil/false —— Lua 里 `c and false or b` 在 c 真时返回 b（错值）。
            #    本面板真分支只会是数字（含 0；**Lua 里 0 为真**，故 `c and 0 or 1` 正确）。
            # ② 条件必须是**真布尔** —— Lua 里数字 0 为真，而 FT 里若把 0 当假用就会反。
            #    本面板一切非比较条件都是 `& | !` 复合，两语言同为 bool ⇒ 安全。
            if _is_literal_false(a):
                raise TranspileError(
                    "三元真分支是 false/nil 字面量 ⇒ Lua and/or 降级会错值：%s" % a)
            self._cond_kinds.append((cond, _looks_boolean(cond)))
            return "((%s) and (%s) or (%s))" % (cond, a, b)
        return cond

    def binary(self, lvl):
        if lvl >= len(self.BIN):
            return self.unary()
        left = self.binary(lvl + 1)
        while self.peek()[1] in self.BIN[lvl]:
            op = self.take()[1]
            right = self.binary(lvl + 1)
            left = "(%s %s %s)" % (left, self._op(op), right)
        return left

    @staticmethod
    def _op(op):
        return {"=": "==", "&": "and", "|": "or", "!=": "~="}.get(op, op)

    def unary(self):
        k, v = self.peek()
        if v == "-":
            self.take()
            return "(-%s)" % self.unary()
        if v == "!":
            self.take()
            return "(not %s)" % self.unary()
        if v == "+":
            self.take()
            return self.unary()
        return self.primary()

    def primary(self):
        k, v = self.take()
        if v == "(":
            e = self.ternary()
            self.expect(")")
            return "(%s)" % e
        if k == "num":
            return v
        if k == "id":
            if self.peek()[1] == "(":
                self.take()
                args = []
                if self.peek()[1] != ")":
                    while True:
                        args.append(self.ternary())
                        if self.peek()[1] == ",":
                            self.take()
                            continue
                        break
                self.expect(")")
                return self.call(v, args)
            return self.atom(v)
        raise TranspileError("意外 token %r" % (v,))

    def call(self, name, args):
        if name in STATEFUL_FUNCS:
            # 有状态函数：翻译成对**镜像状态表** M 的读写。key 由调用点位置决定（见 self.st_key），
            # 保证同一式子里的每个 rate()/sum()/smooth() 各有独立状态格。
            return self.stateful(name, args)
        tpl = SIMPLE_FUNCS.get(name)
        if tpl is None:
            raise TranspileError("未知 FT 函数 %s()（先在 SIMPLE_FUNCS 里声明语义）" % name)
        lo, hi = ARITY.get(name, (1, None))
        if len(args) < lo or (hi is not None and len(args) > hi):
            raise TranspileError("%s() 实参个数 %d 不在 [%s, %s]" % (name, len(args), lo, hi))
        out = tpl.replace("{*}", ", ".join(args))
        return out.format(*args)

    def atom(self, name):
        if name in FT_BUILTIN:
            return "S.%s" % name
        # 非内置 = 自定义 setter 名 ⇒ 读镜像快照（同一份式子按面板顺序求值后落表）
        return "V.%s" % name


def transpile_full(expr, varname=""):
    """返回 (lua_expr, state_info, audit)。
    audit = {"nonbool_conds": [...]} —— 非布尔条件的**告警**（不阻断，但要人工过目）。"""
    p = _P(_tokenize(expr), varname)
    lua = p.parse()
    nonbool = [c for c, ok in p._cond_kinds if not ok]
    return lua, p.st_info, {"nonbool_conds": nonbool}


def transpile(expr, varname=""):
    """FT 表达式 → Lua 表达式串（只要无状态部分；有状态会被翻成 M.* 引用）。"""
    return transpile_full(expr, varname)[0]


if __name__ == "__main__":
    # 自测：拿几条真面板式子过一遍，人眼核对
    tests = [
        ("trkNow",  "atan2(rate(Longitude), rate(Latitude))"),
        ("BG",      "190 + atan2(0 - LT0, SD0)"),
        ("xtrk",    "(SD < 15000) ? LT : 0"),
        ("bankTrk", "-clamp(trkEr + LEAD, -30, 30)"),
        ("LEAD",    "clamp(atan(xtrk / max(400, Rturn)), -45, 45)"),
        ("htExcess", "(SD < 15000) ? max(0, (Altitude - fldE) - SD * tanG) : 0"),
        ("tanG",    "clamp(GS * 0.12, 3, 7) / max(GS, 5)"),
        ("vsInt",   "clamp(sum((((abs(Roll) < 0.05) & (abs(Pitch) < 0.05)) & (abs(vsErr) < 10)) ? vsErr * 0.35 : 0), -20, 20)"),
    ]
    for n, e in tests:
        lua, st, aud = transpile_full(e, n)
        print("%-9s %s" % (n, e))
        print("      => %s" % lua)
        for k, fn, a in st:
            print("         st %-14s %s(%s)" % (k, fn, ", ".join(a)))

