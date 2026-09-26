#!/usr/bin/env python3
"""FT-Lite 自主着陆律直写 TESTaircraFT.xml（唯一真源=本脚本）。SC-5。
用法: python ft_autoland_patch.py [--apply]   默认 dry-run 只报差异。
规则: 首次 apply 自动备份 .pre-FTal.bak；重建 Variables 面板 + 替换副翼/升降舵/油门/起落架表达式。
激活: Activate7（MFD 无依赖，纯机体分发，工坊可用）。
几何: 固定 Cochran 22L——瞄准点 A=(−27710.2,15240.8)（threshold 前 250 m，v4.66 账），
      ch=225°（cos=sin=−0.707107），场地标高 3 m，道线斜率 0.0564（3.23°）。
法典: sin/cos 参数=度；AngleOfAttack=−真α；轴正=推杆；RollAngle 正=左坡；
      Activate1-8 在输入轴白名单（FT 文档实锤）；HOLD 类保留字雷区已避名。
v0.4（app55 验尸）: ①滚转律双项反号定罪（ra 恒负=右滚越转越远）→ 串级两项翻正；
      ②表序链选被 11 km 外走廊劫持 → 改 BW=min|LT| 择优 + BT 自参照黏滞（setter 逐拍
      求值、读同名全局=上一拍值，平台免费锁存器）；③闸门中途失格=律半程撒杆 →
      接合改锁存（进 2 km 咬合、SD>600∧|LT|<1500 保持、越界/近地脱开）；
      ④62 m/s 平飞下限钉死坡度上限 20+0.7(V−62)（55° 坡 62 m/s=螺旋掉高）。
      ⚠ Lua 探杆读 craft.Controls.Activate7 pcall 失败（A7=−1）——FT 白名单≠Lua 代理面。"""
import os, re, sys, io

PROBE = "--probe" in sys.argv
MINPANEL = "--minpanel" in sys.argv   # 只留 P1/P2 两个短 setter：分离"面板可用性"与"长式子/条数"
FEW = "--few" in sys.argv             # 面板条数二分：只烘焙前 4 条走廊
GEARSTOCK = "--gearstock" in sys.argv  # 把 4 个起落架件恢复原生 input="LandingGear"（清残留用）
GEARLAW = "--gearlaw" in sys.argv      # 反向：把起落架通道重新接上表达式（仅作复测用，见 §32）
THRTEST = "--thrtest" in sys.argv      # 油门通道自证（app78 二阶：挂桨距，不挂发动机）

CRAFT = os.path.expandvars(r"%USERPROFILE%\AppData\LocalLow\Jundroo\SimplePlanes 2\Crafts\TESTaircraftFT.xml")
# ⚠ 文件名教训：Windows 大小写不敏感，"TESTaircraFT.xml" 会解析成 "TESTaircraft.xml"（正主曾因此被覆写）。
#   文件名必须真不同（TESTaircraftFT.xml），游戏内显示名取机体 name 属性="TESTaircraFT"。

# ── v0.3 全机场烘焙：13 跑道走廊；v0.4 择优选择（BW 全扫描 min|LT| + BT 自参照黏滞）──
# (name, thr_lat, thr_lon, hdg, field_elev)  源=analysis/data/runway-locations.json 同一张表
RWYS = [
    ("Cochran 04L", -29883, 12873, 45, 3),  ("Cochran 22L", -27887, 15064, 225, 3),
    ("Cochran 18",  -26945, 14477, 180, 3),
    ("Shepard 34",  -2330,  4381,  345, 11), ("Shepard 22",  -2556,  4340,  225, 11),
    ("Bannock 05",  -38878, 6533,  50, 5),  ("Bannock 23",  -37451, 8234,  230, 5),
    ("Bannock 08",  -38872, 6204,  80, 5),  ("Bannock 26",  -38681, 7288,  260, 5),
    ("Kunimitsu 1", -5540,  12797, 10, 10), ("Kunimitsu 19", -4500, 12980, 190, 10),
    ("Kunimitsu 4", -6180,  12122, 40, 10), ("Kunimitsu 22", -5160,  12978, 220, 10),
]
import math
if FEW:
    RWYS = RWYS[:4]
N = len(RWYS)
def runway_setters():
    # 符号法典 v0.9（app68 桌面复算炸出的**双向反号**）：封版 Lua（telemetry-addon.lua
    # ftlite_probe 镜像同式）为 s = (A−P)·ĥ、l = (A−P)·(sin,−cos)，A=瞄准点、P=本机；
    # 旧 FT 版写成 (P−A) → SD 正负语义倒转（"跑道前方 6 km"变成"已飞越 6 km"），
    # 走廊判定与 TLA/VSP 全部反。此处按封版式重写，勿再"顺手改符号"。
    rows = []
    meta = []
    for i, (nm, la, lo, hd, el) in enumerate(RWYS):
        h = math.radians(hd); c, s = math.cos(h), math.sin(h)
        AL, LO = la - 250*c, lo - 250*s        # 瞄准点=threshold 前 250 m（v4.66 账）
        rows.append(("SD%d" % i, "(%.1f - Latitude) * %.6f + (%.1f - Longitude) * %.6f" % (AL, c, LO, s)))
        rows.append(("LT%d" % i, "(%.1f - Latitude) * %.6f - (%.1f - Longitude) * %.6f" % (AL, s, LO, c)))
        meta.append((AL, LO, hd, el))
    return rows, meta

_SET, _META = runway_setters()

# ── Setter 面板（v0.9 重写：全短式逐级锦标赛链）───────────────────────────
# 两条平台铁律（app59 反编译 + app68 实飞二分，均为实锤）：
#  ① Setter 只能引用**排在它自己之前**已定义的名字——前向引用/自参照一律 Expression
#     CompileException，且一条炸=整个 <Variables> 面板全灭（Value 走 IsCompiled==false →
#     0f，症状="开关按了没有任何反应"）。"上一拍值"一律交给 rate()/smooth() 的内置记忆。
#  ② app68 二分：2 条短 setter 的面板能驱动副翼（用户"滚了"），而 13 走廊 min|LT| 折叠 +
#     按 BT 索引取值（单条 1~2 KB）的 65 setter 面板全灭（"依旧不滚"）→ **长式子这条面
#     在这个规模上不可信**。选择器推倒：改表序首个合格走廊的逐级小链，每级一次三目、
#     复制一份载荷，单式 ≤ 60 字符。择优（min|LT|）代价：两条走廊同时合格时按表序取先——
#     闸门是方向性的（SD>0 排除背向跑道），同场平行跑道不会同时合格，实测再判。
# 顺序=传感器几何→闸门→选择链→律量。
_G = []
for _i, (_nm, _la, _lo, _hd, _el) in enumerate(RWYS):
    _G.append(("G%d" % _i,
               "(abs(LT%d) < max(900, 2 * RCAP)) & (SD%d > -200) & (SD%d < 15000)"
               % (_i, _i, _i)))   # 可接合窗 v0.10：|LT| ≤ max(900, 2r)。app64 定罪旧式
               # `1.15|LT|≤r@55` 在 65 m/s 只许 272 m 侧偏=把进场速度下的接管全饿死（封版律带
               # D 项从 661 m 也收得拢；2r 是切线捕获下限，900 m 作低速地板）。
               # 近边 v0.8 定在 1500，app70 定罪改 300：跑道本身一两公里长，门在 1.5 km 就
               # 撒手=最关键的短五边没人飞（末段 LT −193→−383 发散即此账）。v0.11 再放到 −200：
               # app71 实证横向已飞成（rol 轴 0% 活动下 LT +495→±3 保持 45 s），但门在 SD=300
               # 就断=离头 300 m、还差 250 m 高度时把杆交还给飞行员。现在多给 200 m 过门槛，
               # 落地段由 WA 拉平接管；再往后（SD<−200）才是"已飞越"。背向跑道不会误接：
               # 反向跑道的 SD 在同一点上必然更大（选近者天然赢），且 |LT| 窗只有几百米。

# 逐级选择链：**已建立走廊中最近者**（比较键=链自身携带的 best SD，无需额外索引链）。
# app68 之后仿真实锤：表序首个合格走廊会被 13 km 外一条"恰好压着延长线"的走廊劫持
# （|LT|=82 m 比本场 450 m 还小）→ 飞机被拽离本场、飞出远走廊窗口、脱开、再来一次。
# 改按 SD 最小：谁离我最近且已建立，就落谁；同距离平手取表序先（严格 < ）。
# 哨兵：QS 尾=+9999999（无解，ENG 的 SD<15000 门挡死），QL/QT 尾=−9999999。
_TAILB = "9999999"
_TAIL = "-9999999"
_SEL = []
_prev = (_TAILB, _TAIL, _TAIL, "0")
for _i, (_nm, _la, _lo, _hd, _el) in enumerate(RWYS):
    _pSD, _pLT, _pTLA, _pHD = _prev
    _k = "(G%d) & (SD%d < %s)" % (_i, _i, _pSD)
    _SEL.append(("QS%d" % _i, "(%s ? SD%d : %s)" % (_k, _i, _pSD)))
    _SEL.append(("QL%d" % _i, "(%s ? LT%d : %s)" % (_k, _i, _pLT)))
    _SEL.append(("QT%d" % _i, "(%s ? %d + 0.0564 * max(SD%d, 0) : %s)" % (_k, _el, _i, _pTLA)))
    _SEL.append(("QD%d" % _i, "(%s ? %d : %s)" % (_k, _hd, _pHD)))
    _prev = ("QS%d" % _i, "QL%d" % _i, "QT%d" % _i, "QD%d" % _i)

_PROBE = [("P1", "1"), ("P2", "Latitude")] if PROBE else []   # plumbing 探杆只在 --probe 入面板
SETTERS = _PROBE + _SET + [
    ("CFG",  "(IAS < 66 ? 26 : (IAS < 71 ? 36 : (IAS < 76 ? 43 : (IAS < 85 ? 49 : (IAS < 97 ? 53 : 55)))))"),
    ("RCAP", "IAS * IAS / 13.5"),             # 55° 坡切线捕获半径（Lua 分箱 r=V²/13.5 同源）
] + _G + _SEL + [
    ("SD",   _prev[0]),                        # 链尾别名：选中走廊四件载荷
    ("LT",   _prev[1]),
    ("TLA",  _prev[2]),                        # 道线高 AMSL = 场地标高 + 3.23° 下滑（0.0564）
    ("HDG",  _prev[3]),                        # 走廊线航向（选中跑道磁航向）
    # 主电不在面板里做：app62 定案 `Activate7` 在 setter 上下文读不到，而本机无襟翼件（零件清单只有
    # Roll/Trim/Yaw/Brake/Throttle/LandingGear）→ 开关下放到零件输入表达式（文档座舱盖一节实测面）
    ("LTD",  "smooth(clamp(rate(LT), -40, 40), 6)"),   # 侧偏率：rate 自带记忆，不需自参照差分
    ("LEFF", "LT + 2.5 * LTD"),                # v4.68 同款 D 项（治 S 弯等幅振荡）
    ("CM3",  "min(30, 0.06 * abs(LEFF)) + min(14, 0.12 * abs(LEFF))"),
    # ── 横向律：v0.9 结构归位（app68 仿真实锤，不是调参问题）──────────────────
    # 旧 FT 版 `PHI_C = ±CM3` 把**切入角**当**坡度**用：横向回路成了 坡度→航向→侧偏 的双
    # 积分链（仿真：450 m 侧偏进场→坡度 41° 猛切→过线 −99→+336 m 等幅发散）。封版 Lua
    # （telemetry-addon.lua v4.67/68，app44 实测 l 1900→−5 m/50 s）是两级：
    #   psi_cmd = 线航向 − clamp(±lead, ±40)   →  坡度目标 = −(psi_cmd − 航向)（钳 CFG）
    # 即"切入角→期望航向→坡度"，只剩单积分，天然收敛。照搬：
    ("LEAD", "clamp(CM3 * (LEFF > 0 ? 1 : -1), -40, 40)"),
    ("PSI",  "HDG - LEAD"),                    # 期望航向=线航向−前置角（封版 psi_cmd 同式）
    # v0.12 归位：官方函数表第 803 行 `deltaangle(a,b)`=最短转角（示例正是 deltaangle(Heading,
    # TargetHeading)），直接给真方位差，不用 sin 周期函数凑回绕（旧式小角≈线性但 90° 后反而
    # 回缩，eps=120° 只当 60° 用）。增益 1.2≈旧式 65·sin 在 ±25° 内的斜率，行为不变、边界更准。
    ("PHI_C", "clamp(-1.2 * deltaangle(Heading, PSI), -CFG, CFG)"),
    # ── 纵向：app71+仿真实锤的"追不上道线"是**结构性的静差**，不是限幅不够 ──────────
    # 纯 P 道路径跟踪追一条以 0.0564·V（80 m/s 时 4.5 m/s）下沉的斜坡，稳态误差=斜率/增益
    # =4.5/0.1=**45 m 永远收不拢**（仿真 E 局实锤：err 200→45 后就地躺平）。封版律本来就有
    # 前馈项（path_cmd 用 sink_cmd 显式给），FT 版照搬：减掉道线自身的下沉率。
    ("SSK",  "(IAS > 88 ? -12 : (IAS > 76 ? -10 : -8))"),   # 沉底权限随速度（低速给 −8 不再抽能量）
    ("VVT",  "clamp(0.1 * (TLA - Altitude) - (SD > 0 ? 0.0564 * GS : 0), SSK, 6)"),
               # 历史账：app70 一律 −4（1700 m 误差要 425 s）、v0.10 按速度 −8/−4——都只动了限幅，
               # 静差那条没动；app52"沉底=能量螺旋"的教训仍守：低速只许 −8，且油门有 0.35 地板。
    ("ALF",  "clamp(rate(Altitude), -15, 15)"),
    ("VSP",  "78 + 12 * clamp((SD - 2000) / 6000, 0, 1)"),   # 远段 90 有能量转弯→2 km 内 78
    # 推力需求 TDE（0~1）：地板 0.35（app52 无能量螺旋案）+ P 项追 VSP。刻意不引用任何控制轴
    # （§29：setter 面板读不到 ActivateN，其它轴同样未证），"叠加在玩家输入之上"留在零件式里做。
    ("TDE",  "clamp(0.35 + 0.05 * (VSP - IAS), 0, 1)"),
    ("WA",   "clamp01((45 - AltitudeAgl) / 30)"),
    ("CM1",  "1.5 * (VVT - ALF) + 3 * (1 / cos(clamp(abs(RollAngle), 0, 60)) - 1)"),
    ("CM2",  "8 + AngleOfAttack + 3 * (1 / cos(clamp(abs(RollAngle), 0, 60)) - 1)"),
    ("CMD",  "CM1 + WA * (CM2 - CM1)"),
    # 接合门（软锁存用 smooth 的记忆，非自参照）：升起≈2.9 s，中途失格也是软脱开；
    # 脱扣=|LT|>2500（保持窗外 1.65 倍）或近地，GLIDE ABORT 的 Lite 形。
    # 无解=哨兵 SD=+9999999；v0.10 后链的输出域=300~15000 或哨兵，这里把门重复一遍是因为
    # 律不能假设上游永远合格。
    ("ENG",  "(SD > -200) & (SD < 15000) & abs(LT) < 2500 & AltitudeAgl > 3"),
    ("ARM",  "smooth(ENG ? 1 : 0, 0.35)"),
    ("HLD",  "ARM > 0.5"),
]

# ── 舵面/系统律（HLD=0 时逐字回退原律，飞行员直通）──
# 滚转串级符号：约定=杆负→坡度负(右)（t31）；封版律同式，app55 离线重放判其自洽。
ACT = "(((Activate7 ? 1 : 0) > 0.5) & HLD)"      # 开关在零件上下文读（app62：setter 上下文读不到）
AIL = ("clamp(Roll + (%s ? smooth(clamp(-0.010 * (PHI_C - RollAngle) + 0.004 * RollRate, "
       "-0.45, 0.45), 3) : 0), -1, 1)" % ACT)
ELE = ("clamp(Trim + PID(-10 * (%s ? clamp(-0.045 * (CMD - PitchAngle) - 0.007 * PitchRate "
       "- (CMD > 4 ? 0.055 * CMD : 0), -1, 1) : Pitch), PitchAngle, -0.10, 0, 0), -1, 1)" % ACT)
# 油门：接通=地板 0.35（app52 定罪"轴 0+P=无能量螺旋"，飞行员推杆只许往上加）+ P 项追 VSP。
# v0.14 补 retard（app76 定罪）：拉平阶段无条件地板还在推 → 飘 20 m、61 m/s 重接地（gf 尖峰 13.6）。
# 封版教训⑩"拉平必收光油门(agl<30)，用能量收升力"——WA 正是 45→15 m 的拉平混合量，>0.5=低于 30 m。
THR  = "(%s ? (WA > 0.5 ? 0 : max(Throttle, TDE)) : Throttle)" % ACT
# 螺旋桨=真正的推力阀门（app78 定案：发动机 IC 只改转速/油耗，桨 IC 才出推力）。
# 未接通时逐字回退原生 VTOL 滑块，不抢玩家的桨距控制。
PROP = "(%s ? (WA > 0.5 ? 0 : TDE) : VTOL)" % ACT
# ── 起落架通道：**默认不触碰起落架零件**（法典 §32，app72~75 定案）─────────────────
# 规则：GearLeg/GearBay 的 input **只认裸轴名直接绑定**（`LandingGear`）——任何 FT 表达式形式
# 都不驱动它，含语义等价的 `(LandingGear)` 与 `1*LandingGear`（app75 用户实机对照）。
# 控制面类零件（副翼/升降舵/油门）相反，吃表达式。所以律无法自动放轮=平台边界。
# 历史坑（别再犯）：v0.9~v0.12b 四种表达式写法全测过、零阻力台阶；`--gearstock` 曾把原生
# 恢复写成 `(LandingGear)`，等于我亲手制造了"手动也放不下"，还拿去怀疑用户的机体。
# 默认路径不写起落架件；`--gearstock` 逐字节写裸轴名，`--gearlaw` 仅作复测开关。
GEAR = "(AltitudeAgl < 250 ? 0 : LandingGear)"

# 起落架零件的 input 必须是【裸轴名】——直接绑定；`(LandingGear)`、`1*LandingGear` 这类
# 表达式形式一律不再驱动起落架（app72~75 实锤，其中 app75 是我自己用括号把恢复写坏，
# 害得用户以为机体坏了、还被我怀疑机体故障）。恢复原生=逐字节还原，不做任何"等价改写"。
GEAR_AXIS = "LandingGear"

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ── 发货闸 2：引用顺序检查（app59 实锤的失败模式）─────────────────────────
# 平台规则：<Variables> 面板里任何 setter 只能引用**排在它之前**已定义的名字、内置只读
# 变量、以及函数；前向引用/自参照 → "Name not defined: X" → 整面板 IsCompiled=false，
# 所有值退 0f（=按了开关毫无反应）。这条比词法闸更致命，必须单独扫。
_JD_READONLY = set("""ActivateN Altitude AltitudeAgl AngleOfAttack AngleOfSlip Brake FireGuns FireWeapons
Flaps Fuel GForce GS GearDown Heading IAS LandingGear LaunchCountermeasures Latitude Longitude Pitch
PitchAngle PitchRate Roll RollAngle RollRate SelectedWeapon TAS TargetDistance TargetElevation
TargetHeading TargetSelected Throttle Time Trim VTOL VerticalG Yaw YawRate""".split())
_JD_FUNCS = set("""min max abs clamp clamp01 lerp sqrt floor ceil round sin cos tan asin acos atan atan2
rate sum smooth deltaangle lerpangle PID BoolToNumber NumberToBool""".split())
def check_refs(setters):
    known = set(_JD_READONLY) | set(_JD_FUNCS)
    defined = []          # 已在其之前定义的 setter 名
    for name, expr in setters:
        for tok in re.findall(r"[A-Za-z_]\w*", expr):
            if tok in known or re.match(r"(?i)^activate\d+$", tok):
                continue
            if tok == name:
                raise ValueError("setter %s 自参照 `%s`——平台判 Name not defined，整面板死亡" % (name, tok))
            if tok not in defined:
                raise ValueError("setter %s 引用 `%s`：既非内置也未在其之前定义" % (name, tok))
        defined.append(name)
    return len(defined)

# 发货闸：Jundroo 表达式词法白名单（源=反编译 Jundroo.Common.Expressions.Tokens.
# OperatorToken 的 case 表）。相等是单 `=`——写 `==` 会被切成两个 `=`，第二个落进一元位
# → ExpressionCompileException: Unary operator not supported: Equal，**整个 Variables
# 面板静默死亡**（app56 实锤：A7 怎么按都没反应）。科学计数 `1e9` 不赌，一律写全。
_JD_OPS = {'+', '-', '*', '/', '&', '|', '!', '>', '<', '>=', '<=', '=', '!=', '?', ':', '%'}
_JD_CHARS = set(" \t(),;")
def lint(expr, name):
    if "==" in expr or "&&" in expr or "||" in expr:
        raise ValueError("%s: 含 `==`/`&&`/`||`——Jundroo 相等是单 =、与是单 &" % name)
    if re.search(r"\d[eE][+-]?\d", expr):
        raise ValueError("%s: 科学计数法未证实，写全数字" % name)
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch in _JD_CHARS: i += 1; continue
        if re.match(r"\d", ch):
            i = re.match(r"\d+\.?\d*", expr[i:]).end() + i; continue
        if re.match(r"[A-Za-z_]", ch):
            i = re.match(r"[A-Za-z_]\w*", expr[i:]).end() + i; continue
        m = next((o for o in ('>=', '<=', '!=') if expr.startswith(o, i)), None)
        if m: i += len(m); continue
        if ch in _JD_OPS: i += 1; continue
        raise ValueError("%s: 非法字符 %r @%d" % (name, ch, i))
    # 括号平衡
    if expr.count('(') != expr.count(')'):
        raise ValueError("%s: 括号不配平" % name)

# ── 发货前仿真（铁律：几何/目标点类表达式必须过方向检查或仿真）──
# FT 表达式迷你解析器：递归下降 → Python AST 编译执行（求值对象=本文件自带常量）。
# 语义映射：布尔=数值 0/1；&=乘（逐值，FT 文档）；|=max(a,b)（FT 文档逐值或）；
#           比较/三元产出 0/1；rate/smooth/PID 在选线仿真中退化为 0/直通/0。
import ast as _ast
_TOKRE = re.compile(r"\s*([A-Za-z_]\w*|&&|\|\||<=|>=|!=|=|\d+\.?\d*(?:[eE][+-]?\d+)?|[<>=+\-*/^()?,:&|!])")
# 法典：Jundroo 表达式相等=单 `=`（`==` 会被切成两个 `=` →
# ExpressionCompileException: Unary operator not supported: Equal，整个 Variables 面板死亡）
def _tok(s):
    s = s.replace("&amp;&amp;", "&&").replace("&amp;", "&")   # 面板存的是转义态，先还原
    if "==" in s: raise ValueError("表达式含 `==`：Jundroo 相等是单 `=`，== 会让面板整体编译失败")
    out, i = [], 0
    while i < len(s):
        m = _TOKRE.match(s, i)
        if not m: raise ValueError("坏 token @%d: %r" % (i, s[i:i+24]))
        out.append(m.group(1)); i = m.end()
    return out

def _parse_ft(s):
    ts = _tok(s); pos = [0]
    def peek(): return ts[pos[0]] if pos[0] < len(ts) else None
    def take(t=None):
        v = peek()
        if t and v != t: raise ValueError("期望 %r 得到 %r @ %s" % (t, v, s))
        pos[0] += 1; return v
    def primary():
        t = take()
        if t == '(':
            e = tern(); take(')')
            return e
        if t and t[0].isdigit() or re.match(r"^\.\d", t or ""):
            return _ast.Constant(value=float(t))
        if t and re.match(r"^[A-Za-z_]", t):
            if peek() == '(':
                take('(')
                args = [] if peek() == ')' else [tern()]
                while peek() == ',':
                    take(); args.append(tern())
                take(')')
                return _ast.Call(func=_ast.Name(id=t), args=args, keywords=[])
            return _ast.Name(id=t)
        raise ValueError("无法解析 %r" % t)
    def leaf():
        if peek() == '-':
            take(); return _ast.Call(func=_ast.Name(id='__bin__'),
                                     args=[_ast.Constant(value='-'), _ast.Constant(value=0.0), leaf()],
                                     keywords=[])
        return primary()
    def lvl(syms, nxt):
        a = nxt()
        while peek() in syms:
            op = take()
            a = _ast.Call(func=_ast.Name(id='__bin__'),
                          args=[_ast.Constant(value=op), a, nxt()], keywords=[])
        return a
    def mul():  return lvl({'*', '/', '^'}, leaf)
    def add():  return lvl({'+', '-'}, mul)
    def rel():  return lvl({'<', '>', '=', '!=', '<=', '>='}, add)
    def bwan(): return lvl({'&', '&&'}, rel)
    def bwor(): return lvl({'|', '||'}, bwan)
    def tern():
        c = bwor()
        if peek() == '?':
            take(); a = tern(); take(':'); b = tern()
            return _ast.IfExp(test=_ast.Call(func=_ast.Name(id='__truth__'), args=[c], keywords=[]),
                              body=a, orelse=b)
        return c
    e = tern()
    if peek() is not None: raise ValueError("残留 token %r in %r" % (peek(), s))
    return _ast.fix_missing_locations(e)

def _truth(x): return x if isinstance(x, bool) else abs(x) > 1e-12
def _bin(op, a, b):
    A = a if isinstance(a, bool) else float(a); B = b if isinstance(b, bool) else float(b)
    r = {'*': lambda: A*B, '/': lambda: A/B, '^': lambda: A**B,
         '+': lambda: A+B, '-': lambda: A-B,
         '<': lambda: A < B, '>': lambda: A > B, '=': lambda: abs(A-B) < 1e-9,
         '!=': lambda: abs(A-B) >= 1e-9, '<=': lambda: A <= B, '>=': lambda: A >= B,
         '&': lambda: A*B, '&&': lambda: (A != 0) and (B != 0),
         '|': lambda: max(A, B), '||': lambda: ((A != 0) or (B != 0))}[op]()
    return r if isinstance(r, bool) else float(r)
_FTFUN = dict(__bin__=_bin, __truth__=_truth,
              abs=abs, sqrt=math.sqrt, floor=math.floor, cos=lambda d: math.cos(math.radians(d)),
              sin=lambda d: math.sin(math.radians(d)), tan=lambda d: math.tan(math.radians(d)), acos=lambda r: math.degrees(math.acos(r)),
              atan2=lambda a, b: math.degrees(math.atan2(a, b)),
              clamp=lambda x, a, b: max(a, min(b, x)),
              clamp01=lambda x: max(0.0, min(1.0, x)),
              min=min, max=max,
              deltaangle=lambda a, b: (b - a + 180.0) % 360.0 - 180.0,   # 官方表：最短转角
              lerpangle=lambda a, b, t: a + ((b - a + 180.0) % 360.0 - 180.0) * t,
              rate=lambda x: 0.0, smooth=lambda x, r: float(x), PID=lambda *a: 0.0)
_PROG = {n: compile(_ast.Expression(body=_parse_ft(f)), "<ft:%s>" % n, "eval") for n, f in SETTERS}

SIM_SKIP = {"LTD"}      # rate/smooth 的内置记忆在 Python 侧无法建模：仿真由调用方差分供值
def sim_tick(env):
    """按面板顺序求值一轮 setter；面板名不预置，前向/自参照当场 NameError（与平台同规则）。"""
    g = dict(_FTFUN); g.update(env)
    for n, f in SETTERS:
        if n in SIM_SKIP:
            continue
        try:
            g[n] = eval(_PROG[n], g)
        except NameError as e:
            raise RuntimeError("setter %s 悬空名: %s\n  expr=%s" % (n, e, f[:160]))
    env.update({n: float(g[n]) if not isinstance(g[n], bool) else g[n]
                for n, _ in SETTERS if n not in SIM_SKIP or n in g})
    return env

def repl_table():
    # 必须在 main() 内即时取 GEAR/THR 现值：早先写成模块级常量，--probe 改全局后表仍是旧律（自查到）
    return [
        (r'input="clamp\(Roll [+-][^"]*"',  'input="%s"' % esc(AIL),  2, "副翼"),
        # 锚式严格匹配原始式样：本机座舱控制件本身有 input="Roll"，放宽会误吞（app59 现场实证）
        (r'input="clamp\(Trim \+ PID\([^"]*"', 'input="%s"' % esc(ELE), 2, "升降舵"),
    ]

def patch_gear(xml, expr):
    """起落架通道按【零件类型】定位替换，不按 input 文本匹配。
    v0.12 踩坑：律改写成 `(AltitudeAgl > 400 ? 1 : 0)` 后旧文本指纹（LandingGear）消失，
    文本式正则替换次数=0 → 幂等性破裂，重打一次就把机体留在旧律上还不报错。
    返回 (xml, 替换次数)。"""
    cnt = [0]
    def one(m):
        blk, k = re.subn(r'(<InputController\.State[^>]*input=")[^"]*(")',
                         lambda mm: mm.group(1) + esc(expr) + mm.group(2), m.group(0))
        cnt[0] += k
        return blk
    xml = re.sub(r'<Part\b[^>]*partType="Gear[^"]*"[^>]*>.*?</Part>', one, xml, flags=re.S)
    return xml, cnt[0]

def corridor_pt(rwname, sd, lat_off=0.0, hdg=190):
    """按走廊几何摆飞机：A−P = sd·(cos,sin) + lat_off·(sin,−cos)（与 runway_setters 同镜）。"""
    nm, la, lo, hd, el = [x for x in RWYS if x[0] == rwname][0]
    r = math.radians(hd); c_, s_ = math.cos(r), math.sin(r)
    AL, LO = la - 250*c_, lo - 250*s_
    return AL - sd*c_ - lat_off*s_, LO - sd*s_ + lat_off*c_, hd


def vertical_cap(err0, V=80.0, sd0=8000.0, rwname=None):
    """一维纵向捕获仿真：面板 VVT 取真值（sim_tick），道线=场高+0.0564·max(SD,0)。
    返回"误差收进 ±30 m 时还剩多少 SD"，追不上=None。判读的是**发货前**的消高预算。"""
    rwname = rwname or ("Kunimitsu 19" if any(x[0] == "Kunimitsu 19" for x in RWYS) else RWYS[-1][0])
    nm, rla, rlo, hd, el = [x for x in RWYS if x[0] == rwname][0]
    sd = sd0; alt = el + 0.0564 * sd + err0
    for _ in range(900):
        la, lo, _h = corridor_pt(rwname, sd, 0.0, hd)
        r = sim_tick(dict(Latitude=la, Longitude=lo, Heading=hd, IAS=V, GS=V,
                          Altitude=alt, AltitudeAgl=max(alt - el, 1.0), PitchAngle=0, PitchRate=0,
                          RollAngle=0, RollRate=0, AngleOfAttack=0, Throttle=0.5,
                          LandingGear=1.0, Activate7=1.0, Time=0.0, LTD=0.0))
        if abs(alt - (el + 0.0564 * max(sd, 0))) < 30:
            return sd
        alt += r["VVT"]; sd -= V
        if sd < 200:
            return None
    return None


def envelope_table():
    print("── 纵向捕获包线（8 km / 14 km 进场，最大可吃掉的高线误差）──")
    for V in (80.0, 95.0, 110.0):
        row = []
        for sd0 in (8000.0, 14000.0):
            ok = [e for e in range(0, 3000, 100)
                  if vertical_cap(e, V=V, sd0=sd0) is not None]
            row.append(max(ok) if ok else 0)
        print("  IAS %3.0f m/s:  8 km ≤ %+5d m   14 km ≤ %+5d m" % (V, row[0], row[1]))


def patch_engine(xml, expr):
    """油门通道按【零件类型】定位（partType 含 Engine 的零件，本机=JPropEngineRadial）。
    与 patch_gear 同因：按 input 文本匹配会在式子本身不含 'Throttle' 时替换 0 处（app78
    第二次踩），而发动机零件里只有那一条 IC，位置稳定。"""
    cnt = [0]
    def one(m):
        blk, k = re.subn(r'(<InputController\.State[^>]*input=")[^"]*(")',
                         lambda mm: mm.group(1) + esc(expr) + mm.group(2), m.group(0), count=1)
        cnt[0] += k
        return blk
    xml = re.sub(r'<Part\b[^>]*partType="[^"]*Engine[^"]*"[^>]*>.*?</Part>', one, xml, flags=re.S)
    return xml, cnt[0]


def patch_prop(xml, expr):
    """螺旋桨 IC 定位：partType="PropellerAssembly*" 里那条 input="VTOL" 的 IC
    （另一条 input="Disabled" 不许碰）。SP2 发动机与螺旋桨是两个部件（文档 §5），
    推力出自桨距需求，所以能量通道必须挂在这里，挂发动机上只会改转速/油耗。（app78）"""
    cnt = [0]
    def one(m):
        # 锚=该零件的【第一条 IC】（盘上顺序：VTOL 桨距在前、Disabled 在后）。
        # 不按 input 内容匹配——那是规范 36 刚记的坑：上一次 apply 写进去的式子会把锚吃掉。
        blk, k = re.subn(r'(<InputController\.State[^>]*input=")[^"]*(")',
                         lambda mm: mm.group(1) + esc(expr) + mm.group(2), m.group(0), count=1)
        cnt[0] += k
        return blk
    xml = re.sub(r'<Part\b[^>]*partType="[^"]*Propeller[^"]*"[^>]*>.*?</Part>', one, xml, flags=re.S)
    return xml, cnt[0]


def wrapd(a):
    return (a + 180) % 360 - 180

def check():
    """运动学仿真：把 SETTERS 当被测物真跑（点质量 1 s 步长）。四局判卷——
    A=app55 复刻（劫持定罪局：必须收进本机场走廊，不能被邻场抢走）；
    B=走廊内直连（500 m 侧偏收线）；C=跑道后方；D=超可达大侧偏（后两局闸门必须拒接）。"""
    print("── v0.9 发货前仿真（全短式链）──")
    names = [x[0] for x in RWYS]
    def sel_of(sd, lt, la, lo):
        """面板不给索引：用解析复算反查选中的是哪条走廊（SD/LT 双指标同时对上才算）。
        与 runway_setters 同式：SD=(A−P)·ĥ，LT=(A−P)·(sin,−cos)。"""
        for i, (AL, LO, hd, el) in enumerate(_META):
            dLa, dLo = AL - la, LO - lo
            c, s = math.cos(math.radians(hd)), math.sin(math.radians(hd))
            if abs(dLa*c + dLo*s - sd) < 1 and abs(dLa*s - dLo*c - lt) < 1:
                return names[i], hd
        return "-", 0.0
    def run(name, la, lo, hdg, ias, agl, tmax=600.0, expect=None):
        # 只喂内置传感器：面板名一律不预置，让"前向/自参照"在仿真里也当场炸（与平台同规则）
        env = dict(Latitude=la, Longitude=lo, Heading=hdg, IAS=ias, GS=ias,
                   Altitude=agl + 10.0, AltitudeAgl=agl, PitchAngle=0.0, PitchRate=0.0,
                   RollAngle=0.0, RollRate=0.0, AngleOfAttack=0.0, Throttle=0.0,
                   LandingGear=1.0, Activate7=1.0, Time=0.0, LTD=0.0)
        phi = 0.0; V = ias; t = 0.0; lt_prev = None; st = 0
        while t < tmax:
            r = sim_tick(env)
            sel, shdg = sel_of(r["SD"], r["LT"], env["Latitude"], env["Longitude"])
            assert abs(r["HDG"] - shdg) < 1 or sel == "-", "HDG 链与选中走廊不一致"
            eps = wrapd(r["PSI"] - hdg)
            phi_c = r["PHI_C"]
            if r["ARM"] > 0.5:
                phi += (phi_c - phi) * min(1.0, 1.0 / 1.5)       # 坡度跟随 1.5 s 时间常数
            else:
                phi += (0.0 - phi) * min(1.0, 1.0 / 1.5)         # 脱开=松杆回中（仿真简化）
            omega = math.degrees(9.81 * math.tan(math.radians(phi)) / V)  # 左滚率正
            hdg_new = wrapd(hdg - omega)   # 法典 t31：左滚→航向减小（hr 向东增大）
            mr = math.radians((hdg + hdg_new) / 2)
            la += V * math.cos(mr); lo += V * math.sin(mr)
            hdg = hdg_new; t += 1.0
            # LTD 由仿真侧差分供值（平台侧是 rate/smooth 的内置记忆）
            ltd = r["LTD"]
            if lt_prev is not None:
                ltd = 0.886 * ((r["LT"] - lt_prev) / 1.0) + 0.114 * ltd
            lt_prev = r["LT"]
            env.update(Latitude=la, Longitude=lo, Heading=hdg, RollAngle=phi, Time=t, LTD=ltd)
            if int(t) % 20 == 0 and t > 0:
                print(" %s t=%4.0f sel=%-13s SD=%+7.0f LT=%+7.0f hdg %+6.0f eps %+5.1f phi %+5.1f ARM=%d" %
                      (name, t, sel, r["SD"], r["LT"], hdg, eps, phi, r["ARM"]))
            # 判卷=**稳定收线**（app68 复仿真教训：首次穿越 |LT|<150 不等于接住，
            # 旧判据把发散 S 弯的第一次过线也算 PASS）：连续 15 s 在线内+轴向对正+未过近
            if abs(r["LT"]) < 200 and abs(eps) < 8 and -200 < r["SD"] and r["ARM"] > 0.5:
                st += 1
            else:
                st = 0
            if st >= 15:
                print(" %s >>> t=%.0f s 收线稳定（连续 15 s）：sel=%s SD=%.0f LT=%+.0f eps=%+.1f" %
                      (name, t, sel, r["SD"], r["LT"], eps))
                return (not expect) or sel.startswith(expect)
        print(" %s >>> %.0f s 未稳定（sel=%s LT=%+.0f SD=%+.0f）" % (name, tmax, sel, r["LT"], r["SD"]))
        return False
    def rw_pt(rwname, sd, lat_off, hdg):
        """按走廊几何摆飞机：瞄准点沿陆方向回退 sd、侧偏 lat_off（右正）。
        与 runway_setters 同镜：A−P = sd·(cos,sin) + lat_off·(sin,−cos)。"""
        nm, la, lo, hd, el = [x for x in RWYS if x[0] == rwname][0]   # 面板锚=瞄准点：直接用 AL/LO
        r = math.radians(hd); c_, s_ = math.cos(r), math.sin(r)
        AL, LO = la - 250*c_, lo - 250*s_
        return AL - sd*c_ - lat_off*s_, LO - sd*s_ + lat_off*c_, hdg
    # 场景跑道随面板裁剪而变（--few 只剩前 4 条）：取表尾那条，邻场劫持关系同样成立
    rwA = "Kunimitsu 19" if "Kunimitsu 19" in names else names[-1]
    fld = rwA.split()[0]
    la0, lo0, hd0 = rw_pt(rwA, 8000, 450, 185)
    okA = run("A 择优不劫持", la0, lo0, hd0, 95, 900, tmax=200, expect=fld)  # 合法剖面：判=必须本机场，非邻场
    la, lo, hd = rw_pt(rwA, 6000, 500, 190)
    okB = run("B 侧偏收线", la, lo, hd, 90, 800, tmax=200)   # 允许中途移交给邻近走廊
    def one_shot(la, lo, hdg, ias):
        env = sim_tick(dict(Latitude=la, Longitude=lo, Heading=hdg, IAS=ias, GS=ias,
                            Altitude=800, AltitudeAgl=790, PitchAngle=0, PitchRate=0,
                            RollAngle=0, RollRate=0, AngleOfAttack=0, Throttle=0,
                            LandingGear=1.0, Activate7=1.0, Time=0.0, LTD=0.0))
        return env
    e1 = one_shot(*rw_pt(rwA, 20000, 0, 190), 80)   # 场站北 20 km：四条 15 km 半径外全拒
    e2 = one_shot(*rw_pt(rwA, 5000, 8000, 190), 80) # 8 km 大侧偏：窗内无解→拒
    okC = (e1["ARM"] == 0.0)
    okD = (e2["ARM"] == 0.0)
    print(" C 后方拒接: %s (ARM=%.0f SD=%.0f LT=%.0f)" % ("PASS" if okC else "FAIL", e1["ARM"], e1["SD"], e1["LT"]))
    print(" D 超可达拒接: %s (ARM=%.0f SD=%.0f LT=%.0f)" % ("PASS" if okD else "FAIL", e2["ARM"], e2["SD"], e2["LT"]))
    # ── E) 纵向捕获包线扫描（app71 起；实现提到模块级 vertical_cap()，--envelope 可扫速度）
    caps = [(e, vertical_cap(e)) for e in range(0, 1600, 200)]
    far = [(e, vertical_cap(e, sd0=14000.0)) for e in range(0, 2400, 400)]
    env8 = max([e for e, c in caps if c is not None] or [0])
    env14 = max([e for e, c in far if c is not None] or [0])
    okE = env8 >= 400          # 发货线：8 km/80 m/s 至少吃掉 400 m 高线误差
    print(" E 纵向捕获包线（80 m/s，最大可吃掉的高线误差）: 8 km=%d m   14 km=%d m" % (env8, env14))
    print("   捕获点(8 km 进场): " + "  ".join("%d→%s" % (e, ("SD=%.0f" % c) if c else "追不上") for e, c in caps))
    print("   判据(8 km 至少吃 400 m): %s" % ("PASS" if okE else "FAIL"))
    assert okA and okB and okC and okD and okE, "仿真未过——禁止发货"
    print(" 仿真五局全过")

REPL_EXTRA = []

def main():
    global AIL, ELE, THR, GEAR, REPL_EXTRA, SETTERS
    if THRTEST:
        # 油门通道自证（与 §32 起落架案同一手法：纯内置量、两值都喂足、物理不可伪造）：
        # 前 30 s 强制 0（怠速），30 s 后强制 1（满油）。判读只看一件事——
        #   30 s 后不推杆不俯冲而 IAS 一路涨（发动机声/RPM 起来）= 通道活着；
        #   30 s 后毫无反应、IAS 停在怠速平衡值 = 通道死，FT-Lite 的油门通道要撤，
        #   能量管理退回"飞行员管油门"，交付说明照起落架那样写。
        # app78 一阶判决：油耗台阶证明零件级表达式确实驱动了发动机（0→0.00013/s），但 IAS
        # 反而继续掉（89→84）⇒ 只证到"发动机转了"，没证到"出推力了"。且桨距是
        # pitchControlType="Auto"，"桨在细距"不成立，不许拿它当改接线的理由。
        # 二阶 A/B/C：0~30 s 强制怠速 / 30~60 s 强制满油（表达式驱动）/ 60 s 后交还油门杆
        # （轴驱动）。比较两段加速度：表达式段不涨、手推段涨 ⇒ 零件级输入只驱动发动机
        # 本体、推力仍走轴 ⇒ 油门通道对 FT-Lite 无效，整块撤掉并写进交付边界。
        THR = "(Time > 30 ? 1 : 0)"          # 发动机：仍给满（app78 已证它会转、会烧油）
        PROP_TEST = "(Time > 30 ? 1 : 0)"    # 螺旋桨：这才是推力阀门
        print("!! THRTEST2：发动机+螺旋桨两条 IC 同式（Time>30?1:0）。")
        print("   判读：30 s 后明显加速=桨距是能量通道，律改挂桨；仍不加速=两条都不认，撤通道。")
    if "--envelope" in sys.argv:          # 只出包线表（交付说明里要引这个数）
        envelope_table()
        return
    if MINPANEL:
        SETTERS = [("P1", "1"), ("P2", "Latitude")]
    check_refs(SETTERS)
    print("引用闸过：%d setter 全部只用内置或先前已定义名" % len(SETTERS))
    for n, f in SETTERS:
        lint(f, n)
    for tag, e in (("AIL", AIL), ("ELE", ELE), ("THR", THR), ("PROP", PROP), ("GEAR", GEAR)):
        lint(e, tag)
    # 引用闸也必须扫零件式：v0.15 差点把引用了不存在 setter `TDE` 的零件式发出去——
    # 那正是 app59 的整面死法，而当时 check_refs 只看 setter 面板，漏得干干净净。
    check_refs(list(SETTERS) + [("AIL", AIL), ("ELE", ELE), ("THR", THR), ("PROP", PROP), ("GEAR", GEAR)])
    print("词法闸过：%d setter + 4 律均在 Jundroo 白名单内" % len(SETTERS))
    if not MINPANEL:
        check()
    apply = "--apply" in sys.argv
    if PROBE:
        # 唯一问题：面板 setter 的值能不能进【零件输入表达式】（SC-2 战斗机上是能用的，本机未证）。
        # 仪器选在必然可观测的通道：副翼固定盘量 = -0.4 × P1（P1=面板里的常数 1）
        #   飞机自己压坡度盘旋 → setter→零件 这条引用面通，断点在逻辑
        #   完全平飞不改姿态   → 本机 setter 面板根本不被零件读到，架构要改成零件式内自算
        # 其余通道全部直通，避免与律混读；起落架/油门/升降舵回到原式
        # 隔离步 2：纯常数（不经面板、不经任何变量）——若仍无盘量，说明盘上的副翼式子根本没被执行
        # 分叉判读（一次飞行二择一）：P2=Latitude（传感器直通，飞行中≈几千 → 0.02 倍必饱和）
        #   滚  = 面板值能进零件，那 P1 的"常数 1"才是问题（字面量/类型），我按这条改
        #   不滚 = 面板→零件引用面在本机不通，FT-Lite 改成零件式内自算，不再有面板中间量
        AIL = "clamp(Roll - 0.02 * P2 - 0.35 * P1, -1, 1)"
        ELE = "clamp(Trim + PID(-10 * Pitch, PitchAngle, -0.10, 0, 0), -1, 1)"
        THR = "Throttle"
        GEAR = "LandingGear"
        print("!! 隔离步 2：副翼=纯常数 -0.35（不经面板）。不滚=机体没重载/式子没跑；滚=面板是唯一断点")
    if MINPANEL:
        SETTERS = [("P1", "1"), ("P2", "Latitude")]
        AIL = "clamp(Roll - 0.35 * P1, -1, 1)"
        ELE = "clamp(Trim + PID(-10 * Pitch, PitchAngle, -0.10, 0, 0), -1, 1)"
        THR = "Throttle"
        GEAR = "LandingGear"
        print("!! MINPANEL：面板只有 2 条短 setter。滚=面板可用（凶手在长式子/条数）；不滚=本机面板压根不加载")
    else:
        # 摘探针：方向舵必须显式复原（正常路径原本不碰它，盘上会残留灯式子）
        REPL_EXTRA = [(r'input="clamp\(Yaw - 0\.04 ?\* ?YawRate[^"]*"',
                       'input="clamp(Yaw - 0.04*YawRate, -1, 1)"', 1, "方向舵复原")]

    xml = io.open(CRAFT, encoding="utf-8").read()
    orig = xml

    block = "  <Variables>\n" + "".join(
        '    <Setter variable="%s" function="%s" priority="0" />\n' % (n, esc(f))
        for n, f in SETTERS) + "  </Variables>"
    xml, n = re.subn(r"  <Variables>.*?</Variables>", lambda m: block, xml, flags=re.S)
    assert n == 1, "Variables 块替换次数=%d" % n

    # REPL_EXTRA 两支各自填：--probe 加尾舵灯，正常模式把尾舵复原成原式
    for pat, rep, want, tag in repl_table() + REPL_EXTRA:
        xml, n = re.subn(pat, rep, xml)
        assert n == want, "%s 替换次数=%d 期望=%d" % (tag, n, want)
        print("%s x%d ok" % (tag, n))

    xml, n = patch_prop(xml, PROP_TEST if THRTEST else PROP)
    assert n == 1, "螺旋桨 IC 替换次数=%d 期望=1（按 partType=*Propeller* 定位）" % n
    print("螺旋桨 x%d ok（推力通道）" % n)
    xml, n = patch_engine(xml, THR)
    assert n == 1, "油门（按 partType=*Engine* 定位）替换次数=%d 期望=1" % n
    print("油门 x%d ok（按零件类型定位）" % n)

    if GEARSTOCK or GEARLAW:
        xml, n = patch_gear(xml, GEAR_AXIS if GEARSTOCK else GEAR)
        assert n == 4, "起落架 替换次数=%d 期望=4（按 partType=\"Gear*\" 定位）" % n
        print("起落架 x%d ok（%s）" % (n, "恢复原生" if GEARSTOCK else "接上律"))
    else:
        print("起落架通道未触碰（§32：GearLeg/GearBay 只认裸轴名直接绑定，表达式形式一律不驱动）")

    import xml.etree.ElementTree as ET
    ET.fromstring(xml)
    print("setters x%d, XML well-formed" % len(SETTERS))
    if not apply:
        print("dry-run only; --apply to write into TESTaircraFT.xml"); return
    bak = CRAFT + ".pre-FTal.bak"
    if not os.path.exists(bak):
        io.open(bak, "w", encoding="utf-8").write(orig)   # 备份克隆体的未补丁原态
        print("backup ->", bak)
    io.open(CRAFT, "w", encoding="utf-8").write(xml)
    print("APPLIED ->", CRAFT)
    # 填坑：设计器试飞读 __editor__.xml，只改命名机体文件会让用户永远慢一版（app67 抓到）
    ed = os.path.join(os.path.dirname(CRAFT), "__editor__.xml")
    if os.path.exists(ed):
        io.open(ed, "w", encoding="utf-8").write(xml)
        print("同步 -> __editor__.xml（设计器试飞读这份）")

if __name__ == "__main__":
    main()
