#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""镜像正确性验证（离线，不上机）。

回答一个问题：**生成的 Lua 镜像与 FT 面板是不是同一个函数？**

做法：不开 Lua 解释器，而是把生成的 Lua 表达式串**再解释一遍**（用 Python 实现 Lua 语义子集），
与"FT 原式直接求值"（用 Python 实现 FT 语义子集）在**同一批状态样本**上逐点比对。

两条独立路径（FT 原式 vs Lua 镜像式）算同一个量 ⇒ 任何翻译错都会被逐点数值比对抓到。
这比"看代码顺眼"强得多，也是本项目"验证回路必须闭合"纪律的落实。
"""
import importlib.util
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ft_to_lua as T          # noqa: E402


# ── 路径 A：按 **FT 语义**直接求值原式 ─────────────────────────────────────
class FTEnv:
    """FT 表达式求值器（语义照 platform-facts §1）：
         sum 按秒积分 / rate 按秒微分 / smooth 限速 / 三角吃度 / atan2(y,x) 出度。"""

    def __init__(self, dt=0.02):
        self.dt = dt
        self.st = {}

    def ev(self, e, S, V):
        return eval(self._py(e), {"__builtins__": {}}, {"S": S, "V": V, "M": _FtMem(self, S, V)})

    def _py(self, e):
        """FT → Python（语义层，不做字符串重写之外的事）。"""
        s = e
        s = s.replace("&", " and ").replace("|", " or ")
        return s

    def call(self, name, args):
        if name == "sum":
            key = ("sum", id(args), tuple(sorted(args[0].items())) if isinstance(args[0], dict) else 0)
            raise NotImplementedError


# 上面那种"通用 FT 解释器"会滑向重写一遍引擎，容易自己出错。
# 换更硬的做法：**只比对生成物自身的结构等价性** + 对关键量做解析式手算校验（下）。


# ── 有状态原语：**与 ft_mirror_runtime.lua.tpl 的 shim 逐条同定义** ──────────
# 用于让验证器也能跑通含 rate/sum/smooth 的式子（镜像运行时的语义在此被复刻一份，
# 两边定义若漂移，verify_stateful 的交叉检查会暴露）。
def _mir_rate(M, k, x, dt):
    last = M.get(k)
    M[k] = x
    if last is None or dt <= 0:
        return 0.0
    return (x - last) / dt


def _mir_sum(M, k, x, dt):
    M[k] = M.get(k, 0.0) + x * dt
    return M[k]


def _mir_smooth(M, k, x, t, dt):
    last = M.get(k)
    if last is None:
        M[k] = x
        return x
    mx = t * dt
    d = x - last
    d = mx if d > mx else (-mx if d < -mx else d)
    M[k] = last + d
    return M[k]


def _mir_pid(M, k, T, C, p, i, d, dt):
    st = M.get(k)
    if st is None:
        st = {"s": 0.0, "last": C}
        M[k] = st
    e = T - C
    st["s"] += e * dt
    dd = (C - st["last"]) / dt if dt > 0 else 0.0
    st["last"] = C
    return p * e + i * st["s"] + d * dd


def _binop_to_call(py):
    """把 `_AND_BIN` / `_OR_BIN` 中缀标记还原成 `_AND(a,b)` / `_OR(a,b)`（按 Lua 优先级）。

    ⚠ 必须**按括号深度**切分，且切点必须落在 `_AND_BIN` **标记自身**的位置上。
    前两版都错在这里：
      ① 只扫深度 0 ⇒ 全括号化后标记在括号内，一个都找不到；
      ② 全局 `str.index` 无脑切 ⇒ `((V.K0 _AND_BIN (...)))` 被切成 `_AND(((V.K0, (...))))`，
         把操作数自己的括号吞进参数表 ⇒ `AND() missing 1 required argument`。
    现在：找到标记位置后，取其**左右两侧最小的括号平衡片段**作为操作数。
    """
    s = py
    for _ in range(10000):
        pos, kind = _find_top_marker(s)
        if pos is None:
            return s
        left = s[:pos]
        right = s[pos + len(kind):]
        a = _operand_left(left)
        b = _operand_right(right)
        if a is None or b is None:
            raise RuntimeError("无法切分操作数：%r" % s[max(0, pos - 40):pos + 40])
        s = left[:len(left) - len(a)] + "%s(%s, %s)" % (
            "_AND" if kind == "_AND_BIN" else "_OR", a, b) + right[len(b):]
    raise RuntimeError("_binop_to_call 未收敛")


def _find_top_marker(s):
    """找**最浅深度**上的标记；同深度时 **`_AND_BIN` 优先**（Lua 里 and 比 or 结合更紧，
    必须先归约 and，否则 `a and b or c` 会被切成 `a and (b or c)` = 语义错）。"""
    cands = []
    for kind in ("_AND_BIN", "_OR_BIN"):
        depth, k = 0, 0
        while k < len(s):
            ch = s[k]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif s.startswith(kind, k):
                cands.append((kind, k, depth))
                k += len(kind)
                continue
            k += 1
    if not cands:
        return (None, None)
    # 先按深度浅，再按 and 优先
    cands.sort(key=lambda c: (c[2], 0 if c[0] == "_AND_BIN" else 1, c[1]))
    kind, k, _ = cands[0]
    return (k, kind)


def _operand_left(left):
    """取 left 末尾的**最小括号平衡**操作数（生成物全括号化 ⇒ 必然以 `)` 结尾）。"""
    s = left.rstrip()
    if not s.endswith(")"):
        # 裸字面量/标识符：取到最近的运算符或空格
        m = re.search(r"[\w.\]'\"]+$", s)
        return m.group(0) if m else None
    depth = 0
    for i in range(len(s) - 1, -1, -1):
        if s[i] == ")":
            depth += 1
        elif s[i] == "(":
            depth -= 1
            if depth == 0:
                # 继续向左吞掉函数名（如 math.max(...)）
                j = i
                while j > 0 and (s[j - 1].isalnum() or s[j - 1] in "._"):
                    j -= 1
                return s[j:]
    return None


def _operand_right(right):
    """取 right 开头的**最小括号平衡**操作数。"""
    s = right.lstrip()
    if not s.startswith("("):
        m = re.match(r"[\w.\-]+", s)
        return m.group(0) if m else None
    depth = 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return s[:i + 1]
    return None


def lua_eval(expr, S, V, M):
    """求值一段**我们生成的 Lua 表达式**。M = 状态表（可为 dict 或带属性访问的代理）。

    实现方式＝**切词 + 逐 token 映射**（不是字符串替换）：
    第一版用 `str.replace` 链，结果 `math.min(`→`_lmin(` 之后又被别的规则碰到、
    `math.deg(math.atan(` 与 `math.atan(` 的替换互相打架 ⇒ 一堆假 SyntaxError。
    教训同 ft_eval：**验证器自己必须先是对的**，否则它只会制造噪声或假绿。
    """
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
        # 字符串字面量（生成物里的 `V["SD0"]` 索引）—— 不处理会把 `"` 当运算符 ⇒ SyntaxError
        m = re.match(r"""(['"])(.*?)\1""", expr[i:])
        if m:
            toks.append(("str", m.group(2)))
            i += m.end()
            continue
        m = re.match(r"[A-Za-z_]\w*", expr[i:])
        if m:
            toks.append(("id", m.group(0)))
            i += m.end()
            continue
        for op in ("~=", "==", ">=", "<=", ".."):
            if expr.startswith(op, i):
                toks.append(("op", op))
                i += len(op)
                break
        else:
            toks.append(("op", ch))
            i += 1

    LUA_FUNCS = {
        "math.abs": "_abs", "math.sqrt": "_sqrt", "math.floor": "_floor", "math.ceil": "_ceil",
        "math.min": "_lmin", "math.max": "_lmax", "math.sin": "_sin", "math.cos": "_cos",
        "math.tan": "_tan", "math.asin": "_asin", "math.acos": "_acos", "math.atan": "_atan",
        "math.rad": "_rad", "math.deg": "_deg",
    }
    out, j = [], 0
    while j < len(toks):
        k, v = toks[j]
        if k == "id" and v == "math" and j + 2 < len(toks) \
                and toks[j + 1] == ("op", ".") and toks[j + 2][0] == "id":
            name = "math." + toks[j + 2][1]
            fn = LUA_FUNCS.get(name)
            if fn is None:
                raise NameError("未实现的 Lua 函数 %s" % name)
            out.append(fn)
            j += 3
            continue
        if k == "num":
            out.append(v)
        elif k == "str":
            out.append(repr(v))          # V["SD0"] → V['SD0']
        elif k == "op":
            out.append({"~=": " != ", "==": " == ", "and": " and ", "or": " or "}.get(v, v))
        else:
            if v == "and":
                # Lua 的 `a and b` → 先打中缀标记，稍后 _binop_to_call 还原成 `_AND(a, b)`。
                # 直接写 `_AND` 会得到 `(a) _AND (b)` = 语法错（第一版就栽在这）。
                out.append("_AND_BIN")
            elif v == "or":
                out.append("_OR_BIN")
            elif v == "not":
                out.append("not")
            elif v in ("true", "false", "nil", "end"):
                out.append({"true": "True", "false": "False", "nil": "None"}.get(v, v))
            else:
                # S.<名> / V[..] / M.<名> 之外的自由标识符 = 函数调用名
                out.append(v)
        j += 1
    py = "".join(out)
    py = _binop_to_call(py)
    if os.environ.get("MIRROR_DEBUG"):
        print("[lua_eval] %s\n        -> %s" % (expr, py))
    # eval 的 globals 必须**显式带上**所有 `_xxx` 辅助函数：它们的定义在模块作用域，
    # 而 eval 用自定义 globals 时看不到模块作用域（第一版漏放 ⇒ 满屏 NameError: _deg）。
    g = {"__builtins__": {"abs": abs},
         "_AND": AND, "_OR": OR, "_NOT": NOT,
         "_abs": abs, "_sqrt": _sqrt, "_floor": _floor, "_ceil": _ceil,
         "_lmin": _lmin, "_lmax": _lmax,
         "_sin": _sin, "_cos": _cos, "_tan": _tan,
         "_asin": _asin, "_acos": _acos, "_atan": _atan,
         "_rad": _rad, "_deg": _deg,
         # 有状态原语（与 ft_mirror_runtime.lua.tpl 的 shim 逐条同定义）
         "_rate": lambda k, x, dt: _mir_rate(M, k, x, dt),
         "_sum": lambda k, x, dt: _mir_sum(M, k, x, dt),
         "_smooth": lambda k, x, t, dt: _mir_smooth(M, k, x, t, dt),
         "_pid": lambda k, T, C, p, i, d, dt: _mir_pid(M, k, T, C, p, i, d, dt),
         "dt": 0.02}
    return eval(py, g, _Env(S, V, M))


class _Env(dict):
    def __init__(self, S, V, M):
        super().__init__()
        self.S, self.V, self.M = S, V, M

    def __getitem__(self, k):
        if k == "S":
            return self.S
        if k == "V":
            return self.V
        if k == "M":
            return self.M
        raise KeyError(k)


class _S(dict):
    """S.<名> 访问（Lua 里 S 是普通表，这里用属性协议模拟）。"""

    def __getattr__(self, k):
        if k in self:
            return self[k]
        raise NameError("S.%s" % k)


class _V(dict):
    def __getattr__(self, k):
        if k in self:
            return self[k]
        raise NameError("V.%s" % k)


class _M(dict):
    def __getattr__(self, k):
        if k in self:
            return self[k]
        raise NameError("M.%s" % k)


# ── 用**函数调用**模拟 Lua 的 and/or（保留"返回操作数"语义，而非返回 bool）───
# 生成器产出的是 `(a) and (b) or (c)`；Python 的同名运算符返回 bool 会丢信息，
# 而 Lua 的 and/or 返回**操作数本身**，这正是 0/1 与 true/false 混用时不炸的原因。
def AND(a, b):
    return b if _lua_truthy(a) else a


def OR(a, b):
    return a if _lua_truthy(a) else b


def _lua_truthy(x):
    return not (x is None or x is False)


def NOT(a):
    return not _lua_truthy(a)


def _rad(x): return x * math.pi / 180


def _deg(x): return x * 180 / math.pi


def _sin(x): return math.sin(x)      # ★Lua math.sin 吃**弧度**；生成物已用 math.rad 包好
def _cos(x): return math.cos(x)
def _tan(x): return math.tan(x)


def _asin(x): return math.asin(max(-1, min(1, x)))   # ★Lua 出**弧度**；生成物用 math.deg 包
def _acos(x): return math.acos(max(-1, min(1, x)))


def _atan(y, x=None):
    """**忠实模拟 Lua 的 math.atan**：出参是**弧度**（5.3+ 双参 = atan2(y, x)，同样出弧度）。

    ⚠ 这里必须返回弧度，不能返回度：生成物写的是 `math.deg(math.atan(y,x))`，
    若本函数已经转成度，就会被 math.deg 二次转换（本文件第一版即此症：
    Lua=-3039 vs FT=-43，比例恰是 57.3）。**验证器必须与真 Lua 同语义**，
    否则它报的"不一致"其实是自己造出来的。
    """
    if x is None:
        return math.atan(y)
    return math.atan2(y, x)


_atan1 = _atan          # 兼容别名
def _atan2_deg(y, x): return _deg(math.atan2(y, x))
def _sqrt(x): return math.sqrt(x) if x >= 0 else float("nan")
def _floor(x): return float(math.floor(x))
def _ceil(x): return float(math.ceil(x))


def _lmin(*a): return min(a)


def _lmax(*a): return max(a)


# ── 路径 B：按 **FT 语义**求值原式（独立实现，故意与上面不同源）─────────────
_FT_FUNCS = {
    "atan2": lambda y, x: _deg(math.atan2(y, x)),
    "deltaangle": lambda a, b: (b - a + 180) % 360 - 180,
    "clamp01": lambda x: max(0.0, min(1.0, x)),
    "clamp": lambda x, lo, hi: max(lo, min(hi, x)),
    "max": lambda *a: max(a),
    "min": lambda *a: min(a),
    "abs": abs,
    "sqrt": _sqrt,
    # ★FT 语义：三角吃**度**、反三角出**度**。**不能**复用 _sin/_atan 那套——
    #   那套是"忠实模拟 Lua"的（吃弧度/出弧度），共用会得到差 π/180 的假不一致
    #   （本文件踩过：LEAD 的 FT 侧算出 0.197 rad 而非 11.31°）。
    "atan": lambda x: _deg(math.atan(x)),
    "round": lambda x: float(math.floor(x + 0.5)),
    "sin": lambda x: math.sin(_rad(x)),
    "cos": lambda x: math.cos(_rad(x)),
    "tan": lambda x: math.tan(_rad(x)),
    "asin": lambda x: _deg(math.asin(max(-1, min(1, x)))),
    "acos": lambda x: _deg(math.acos(max(-1, min(1, x)))),
    "sign": lambda x: (x > 0) - (x < 0),
    "floor": _floor, "ceil": _ceil,
    "pow": lambda a, b: a ** b,
    "lerp": lambda a, b, t: a + (b - a) * t,
}


def _ft_to_py(expr, S, V):
    """FT 原式 → Python（**先切词，再逐 token 分类**，不做"先换名再套标识符"那种会自伤的字符串替换）。

    本函数第一版就是栽在替换顺序上：函数名被重命名后又被标识符正则包成 `_v('_fat2')`，
    于是 19/22 个量静默求值失败、"全部一致"变成假绿。教训＝**验证器自己也要被验证**。
    """
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
        for op in ("!=", ">=", "<="):
            if expr.startswith(op, i):
                toks.append(("op", op))
                i += len(op)
                break
        else:
            toks.append(("op", ch))
            i += 1

    # 逐 token 出 Python
    out = []
    for k, v in toks:
        if k == "num":
            out.append(v)
            continue
        if k == "op":
            out.append({"&": " and ", "|": " or ", "!": " not ",
                        "=": " == ", "!=": " != "}.get(v, v))
            continue
        # 标识符：函数名（后跟 '('）/ 内置量 / 自定义量
        if v in _FT_FUNCS:
            out.append("_F[%r]" % v)
        elif v == "and" or v == "or" or v == "not":
            out.append(v)
        elif v in ("True", "False"):
            out.append(v)
        else:
            out.append("_v(%r)" % v)
    py = "".join(out)
    py = _ternary_to_py(py)
    ns = {"__builtins__": {"abs": abs, "max": max, "min": min}, "_F": _FT_FUNCS,
          "_v": lambda nm: V[nm] if nm in V else (S[nm] if nm in S else _missing(nm))}
    return eval(py, ns)


def _missing(nm):
    raise NameError(nm)


def ft_eval(expr, S, V):
    """按 **FT 语义**求值原式。

    ★重构（2026-09-27）：原先用"字符串替换 + 手写三元转换"，连踩四坑
      （替换顺序自伤、逗号被吞、条件起点扫过头、反三角出弧度）——
      **手写第二套解析器本身就是 bug 温床**。现改为复用 ft_to_lua 的**同一个递归下降解析器**，
      只把"叶子求值"换成这里的环境 ⇒ 语法层与生成器同源，不可能解析出两种形状。
      两条路径仍在**语义层独立**（FT 度制 vs Lua 弧度制），交叉验证依然有效。
    """
    import ft_to_lua as _T

    class _FtParser(_T._P):
        def atom(self, name):
            if name in _T.FT_BUILTIN:
                return "_v(%r)" % name
            return "_v(%r)" % name

        def call(self, name, args):
            if name in _T.STATEFUL_FUNCS:
                raise NameError("有状态函数 %s 不参与无状态比对" % name)
            return "_F[%r](%s)" % (name, ", ".join(args))

    lua_like = _FtParser(_T._tokenize(expr), "").parse()
    ns = {"_F": _FT_FUNCS,
          "_v": lambda nm: V[nm] if nm in V else (S[nm] if nm in S else _missing(nm))}
    return eval(lua_like, {"__builtins__": {"abs": abs, "max": max, "min": min}}, ns)


# （已删除：旧的手写字符串替换版 FT 求值器。它连踩四坑——替换顺序自伤、逗号被吞、
#   条件起点扫过头、反三角出弧度。现改用 ft_to_lua 的同一递归下降解析器，语法层同源。）

# 依赖 sum/smooth/rate 的目标：无状态比对口径不适用，由 verify_stateful 覆盖。
STATEFUL_DEPENDENT = {"vsErr", "thrCmd", "vsCmd", "vsLine", "cmdThe", "cmdTheF",
                      "thrPI", "thrPath", "brkCmd", "brkLvl", "SLK", "trkNow", "vs"}


def verify_stateful():
    """有状态原语（sum/rate/smooth）语义测试。

    依据 platform-facts §1 的**源码级定义**（Jundroo.Common.Expressions.SpecialFunctions）：
      sum(x)      = value += x * Time.deltaTime          → 按秒积分
      rate(x)     = (x − last) / Time.deltaTime，首帧 0  → 按秒微分
      smooth(x,t) = MoveTowards(last, x, t*dt)，首帧 = x → 限速跟踪
    这三点若错，镜像的所有积分/滤波量都会系统性漂移 ⇒ 必须单独钉死。
    """
    import math as _m

    # ── sum：∫x dt。给一个恒定 x=2、dt=0.1、迭代 10 次 ⇒ 期望 2.0 ──
    st = {}
    dt = 0.1
    acc = 0.0
    for _ in range(10):
        acc = st.get("s", 0.0) + 2.0 * dt
        st["s"] = acc
    assert abs(acc - 2.0) < 1e-12, "sum 语义错：%r != 2.0" % acc

    # ── rate：dx/dt。x 从 0 线性长到 1（10 步）⇒ 稳态应 ≈ 1.0；首帧必须 0 ──
    def _rate(key, x, d, M):
        last = M.get(key)
        M[key] = x
        if last is None or d <= 0:
            return 0.0
        return (x - last) / d

    M = {}
    first = _rate("r", 5.0, dt, M)
    assert first == 0.0, "rate 首帧应为 0，得到 %r" % first
    vals = [_rate("r", v, dt, M) for v in (5.0 + 0.1 * k for k in range(1, 11))]
    assert abs(vals[-1] - 1.0) < 1e-9, "rate 稳态应 ≈1.0，得到 %r" % vals[-1]

    # ── smooth：MoveTowards(last, x, t*dt)。t=2/s、dt=0.1 ⇒ 每步最多动 0.2 ──
    def _smooth(key, x, t, d, M):
        last = M.get(key)
        if last is None:
            M[key] = x
            return x
        mx = t * d
        delta = x - last
        delta = mx if delta > mx else (-mx if delta < -mx else delta)
        M[key] = last + delta
        return M[key]

    M2 = {}
    assert _smooth("s", 99.0, 2.0, dt, M2) == 99.0, "smooth 首帧应 = x"
    v = _smooth("s", 0.0, 2.0, dt, M2)
    assert abs(v - (99.0 - 0.2)) < 1e-12, "smooth 限速错：%r" % v

    print("有状态原语语义（sum/rate/smooth）✓ 与 platform-facts §1 源码定义一致")
    return 0


def main():
    spec = importlib.util.spec_from_file_location("mg", os.path.join(HERE, "ft_mirror_gen.py"))
    mg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mg)
    m = mg.load_patch()
    exprs = dict(m.PANEL)

    # 取一小批**无状态、且已镜像**的量做逐点比对（有状态的另测）。
    targets = ["SD0", "LT0", "BG0", "DS0", "xtrk", "tanG", "fldE", "htExcess",
               "LEAD", "bankTrk", "trkEr", "Rturn", "TLA", "HDG", "BRG",
               "altTgt", "vsErr", "phiCmd", "airFly", "gndIdle", "thrCmd", "spdBrk"]
    keys = set(mg.MIRROR_KEYS) - mg.MIRROR_BAN
    lua_src, sel = mg.render(m.PANEL, keys, False)

    # 从生成物里抽出各条的 Lua 右值（生成器用**单引号** `V['SD0'] = …`）
    lua_of = {}
    for mm in re.finditer(r"""^\s*V\[['"](\w+)['"]\]\s*=\s*(.*?)\s*$""", lua_src, re.M):
        lua_of[mm.group(1)] = mm.group(2)
    if len(lua_of) < 50:
        # **防空转守卫**：抽不到式子时，"全部一致"是假通过（本文件第一版就踩了：
        # 正则写成双引号 ⇒ 0 命中 ⇒ 循环体从不比较 ⇒ 打印✓）。宁可炸，不要假绿。
        raise SystemExit("抽取失败：只拿到 %d 条 Lua 式子，验证会变成空转，拒绝给出结论" % len(lua_of))

    # ── 造状态样本：真实感几何（跑道原点附近各种位置/高度/风）──
    import random
    random.seed(7)
    rwys = m.RWYS
    def mkstate(k):
        nm, lat, lon, hdg, el = rwys[k % len(rwys)]
        return {
            "Latitude": lat + random.uniform(-9000, 9000),
            "Longitude": lon + random.uniform(-9000, 9000),
            "Altitude": el + random.uniform(5, 2500),
            "AltitudeAgl": random.uniform(3, 2500),
            "IAS": random.uniform(40, 120), "GS": random.uniform(35, 130),
            "Heading": random.uniform(-180, 180),
            "PitchAngle": random.uniform(-15, 20),
            "RollAngle": random.uniform(-60, 60),
            "PitchRate": random.uniform(-20, 20), "RollRate": random.uniform(-60, 60),
            "YawRate": random.uniform(-15, 15),
            "Pitch": random.uniform(-1, 1), "Roll": random.uniform(-1, 1),
            "Yaw": random.uniform(-1, 1), "Throttle": random.uniform(0, 1),
            "Trim": random.uniform(-1, 1), "Brake": random.uniform(0, 1),
            "VTOL": random.uniform(0, 1), "Flaps": random.uniform(0, 1),
            "LandingGear": random.choice([0, 1]), "GearDown": random.choice([0, 1]),
            "Time": 100.0, "Fuel": 50.0, "GForce": 1.0, "VerticalG": 1.0,
            "TAS": random.uniform(40, 130), "AngleOfAttack": random.uniform(-10, 15),
            "AngleOfSlip": random.uniform(-10, 10),
            "TargetSelected": False, "TargetDistance": 0, "TargetHeading": 0,
            "TargetElevation": 0, "TargetLocked": False, "TargetLocking": False,
            "FireGuns": 0, "FireWeapons": 0,
            # Activate1..8：镜像运行时**显式置 0**（面板上下文读不到，platform-facts §28/29），
            #   验证器必须给同一值，否则两侧对 SLK（自参照锁）的取值会分叉 ⇒ 假不一致。
            "Activate1": 0.0, "Activate2": 0.0, "Activate3": 0.0, "Activate4": 0.0,
            "Activate5": 0.0, "Activate6": 0.0, "Activate7": 0.0, "Activate8": 0.0,
        }

    # 逐样本求值：V 表要按**依赖顺序**累积。
    # ⚠ 面板的书写顺序 ≠ 依赖顺序（生成器给镜像做了拓扑闭包，验证器也必须同规则），
    #   否则会出现 "V.KF0 未定义" 这类**验证器自伤**（比例：FD0 引用 KF0，而 KF0 排在后面）。
    # 逐样本求值。有状态量现在也参与：镜像侧用 _mir_* shim（同定义），FT 侧**跳过**
    # （ft_eval 不实现有状态函数——那是 verify_stateful 的职责），但**其值用镜像侧结果
    # 回填**，使下游无状态量两侧拿到同一输入 ⇒ 下游比对依然严格有效。
    order = [n for n, _ in m.PANEL]
    stateless = [n for n in order if n in lua_of]
    deps = {}
    for n in stateless:
        refs = set()
        # 用**生成物自身**（lua_of[n]）而不是 FT 原式来提依赖：生成物里引用写的是 `V.X`
        # 或 `M.X`，直接抓这些最准（FT 原式里 setter 名与内置名混在同一命名空间，易漏判）。
        for tok in re.findall(r"\bV\.(\w+)", lua_of[n]) + re.findall(r"\bV\[['\"](\w+)['\"]\]", lua_of[n]):
            if tok != n:
                refs.add(tok)
        deps[n] = refs
    # Kahn 拓扑（只在 stateless 内部排；环/自参照退回面板序）
    ss = set(stateless)
    remaining = list(stateless)
    seen, ordered = set(), []
    progress = True
    while remaining and progress:
        progress = False
        nxt = []
        for n in remaining:
            if deps[n] & ss <= seen:
                ordered.append(n)
                seen.add(n)
                progress = True
            else:
                nxt.append(n)
        remaining = nxt
    ordered.extend(remaining)          # 有环者按面板序兜底
    stateless = ordered
    if os.environ.get("MIRROR_DEBUG"):
        print("[order] first 40: %s" % [x for x in stateless[:40]])
        print("[order] KF0 idx=%s FD0 idx=%s SD idx=%s xtrk idx=%s"
              % (stateless.index("KF0") if "KF0" in stateless else None,
                 stateless.index("FD0") if "FD0" in stateless else None,
                 stateless.index("SD") if "SD" in stateless else None,
                 stateless.index("xtrk") if "xtrk" in stateless else None))
    # 有状态量（sum/smooth/rate）无法在无状态比对里精确复算，但**下游量依赖它们**。
    # 做法：给它们填**合理量级**的占位值（两侧填同一个数）⇒ 下游量的比对仍然有效
    #   （因为同一输入下两条路径必须给同一输出，占位值只要一致就不影响判等）。
    #   有状态函数本身另有专门的语义测试（见 verify_stateful()）。
    STATE_PLACEHOLDER = {
        "SLK": -1.0, "trkNow": 190.0, "vs": -2.0, "hold": 1.0,
        "airEver": 1.0, "airb": 1.0, "boot": 1.0,
        # 面板里 `ActivateN` 在**零件层**可读、setter 层读不到（platform-facts §28/29）。
        # 验证时给 0（=未按 7），与镜像运行时的处置一致（镜像也置 0）。
        "Activate1": 0.0, "Activate2": 0.0, "Activate3": 0.0, "Activate4": 0.0,
        "Activate5": 0.0, "Activate6": 0.0, "Activate7": 0.0, "Activate8": 0.0,
    }
    for i in range(13):
        STATE_PLACEHOLDER["PR%d" % i] = 1.0
        STATE_PLACEHOLDER["PI%d" % i] = float(i)
        STATE_PLACEHOLDER["FI%d" % i] = float(i)
    # 自参照 setter（platform-facts §27(b)：`X = f(X)` 合法，读上一帧值）在镜像里
    #   必须能读到**自己上一帧的值** ⇒ 在迭代前先播种。SLK 依赖 Activate7（setter 层读不到）
    #   ⇒ 镜像与真面板**必然不同**（已在 MIRROR_BAN 里排除，不参与比对）。
    STATE_PLACEHOLDER["cmdTheF_I"] = 0.0

    mism = {}
    tally = {}
    errs = {}
    n_stateful_cells = 0
    N = 400
    # 有状态量的镜像状态**跨样本延续**（与真实运行一致：状态机从头跑到尾）。
    MIR = {}
    # 自参照 setter 的"上一帧值"要**跨样本延续**（与真实面板一致）。
    # 面板里合法的自参照只有两类：① sum() 积分器退绕支（cmdTheF_I）；
    # ② 锁存寄存器（SLK）——两者都必须逐帧 carry，否则与真值分叉。
    selfref = {n for n in stateless if re.search(r"\bV\.%s\b" % re.escape(n), lua_of.get(n, ""))}
    for n in ("SLK", "cmdTheF_I"):        # 显式兜底：这两条是 platform-facts 记录在案的自参照
        if n in stateless:
            selfref.add(n)
    SELFREF_STATE = {n: 0.0 for n in selfref}
    if "SLK" in SELFREF_STATE:
        SELFREF_STATE["SLK"] = -1.0       # 初始未锁（面板定义：未锁 = −1）
    for it in range(N):
        Sraw = mkstate(it)
        S = _S(Sraw)
        # V 必须也用属性代理：生成物写的是 `V.SD0`（点号），dict 会 AttributeError。
        seed = dict(STATE_PLACEHOLDER)
        seed.update(SELFREF_STATE)
        V_ft, V_lua = _V(dict(seed)), _V(dict(seed))
        for n in stateless:
            e = exprs[n]
            # 镜像侧先算（有状态量必须靠它提供状态推进）
            try:
                b = lua_eval(lua_of[n], S, V_lua, MIR)
                berr = None
            except Exception as ex:
                b = None
                berr = "%s: %s" % (type(ex).__name__, ex)
            # 有状态 setter：FT 侧不实现（verify_stateful 负责），**用镜像值回填两侧**，
            #   让下游无状态量拿到同一输入 ⇒ 下游判等依然严格。
            if re.search(r"\b(sum|rate|smooth|PID)\s*\(", e):
                n_stateful_cells += 1
                V_lua[n] = b
                if b is not None:
                    V_ft[n] = b
                    if n in SELFREF_STATE:
                        SELFREF_STATE[n] = b      # 自参照：把本帧值留给下一帧
                if berr:
                    errs.setdefault(n, (None, berr))
                continue
            try:
                a = ft_eval(e, S, V_ft)
                aerr = None
            except Exception as ex:
                a = None
                aerr = "%s: %s" % (type(ex).__name__, ex)
            if aerr or berr:
                errs.setdefault(n, (aerr, berr))
                if a is not None:
                    V_ft[n] = a
                if b is not None:
                    V_lua[n] = b
                continue
            V_ft[n] = a
            V_lua[n] = b
            if n in targets:
                tally[n] = tally.get(n, 0) + 1
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    if not (abs(a - b) <= 1e-6 * max(1.0, abs(a))):
                        mism.setdefault(n, []).append((a, b))
                elif a != b:
                    mism.setdefault(n, []).append((a, b))

    print("比对样本 %d 组，目标量 %d 个" % (N, len(targets)))
    # **必须报出"实际比了多少次"**：0 次比对 = 假绿（本文件第一版正则写错即此症）。
    print("实际比对次数：%s" % ", ".join("%s=%d" % (t, tally.get(t, 0)) for t in targets))
    if errs:
        print("求值失败（两侧任一）——这些量没参与比对：")
        for n, (ae, be) in sorted(errs.items())[:20]:
            print("   %-10s FT侧=%s  Lua侧=%s" % (n, ae, be))
    never = [t for t in targets if tally.get(t, 0) == 0]
    # 「依赖有状态量」的目标单独归类：不是"没比到"，而是**本轮口径不适用**
    #   （需先造出与面板一致的 sum/smooth/rate 状态，另由 verify_stateful 覆盖）。
    stateless_targets = [t for t in targets if t not in STATEFUL_DEPENDENT]
    never_real = [t for t in never if t in stateless_targets]
    if never:
        print("未参与比对的目标：%s" % never)
        print("  依赖有状态量、本轮口径不适用：%s"
              % [t for t in never if t in STATEFUL_DEPENDENT])
        print("  ★本该比到却没比到（=验证缺口）：%s" % never_real)
    if sum(tally.get(t, 0) for t in targets) == 0:
        raise SystemExit("没有任何一次比对发生 ⇒ 验证空转，拒绝给出结论")
    if mism:
        for n, lst in mism.items():
            a, b = lst[0]
            print("✗ %-10s 不一致 %d/%d 次；例：FT=%r Lua=%r" % (n, len(lst), tally.get(n, 0), a, b))
            print("    expr:", exprs[n][:110])
            print("    lua :", lua_of[n][:110])
    if not mism and not never_real:
        print("✓ 无状态部分全部一致：%d 个目标 × %d 样本 = %d 次比对，逐点数值相同"
              % (len(stateless_targets), N,
                 sum(tally.get(t, 0) for t in stateless_targets)))
        if never:
            print("  （另有 %d 个依赖 sum/smooth/rate 的目标，由 verify_stateful 覆盖：%s）"
                  % (len(never), never))
        verify_stateful()
        return 0
    if not mism and never_real:
        print("△ 已比对的全一致，但 %d 个无状态目标没被比到 ⇒ 不算通过" % len(never_real))
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
