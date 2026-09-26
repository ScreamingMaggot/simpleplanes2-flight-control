#!/usr/bin/env python3
"""TESTaircraft2 的 Funky Trees 飞控层（唯一真源）。SC-6 / #18 起步版。

v0.1 = 姿态指令电传（attitude-command fly-by-wire）+ 失速门 + 座舱 Label 读数。
用法: python ft_ta2_patch.py [--apply]        默认 dry-run 只报差异与闸门结果。

写法规范（照 Droplet 强例，见 analysis/ft-droplet-study.md §8；不要再犯的旧病在 §8 表里）：
  ① 面板只放少量、每条一个物理含义、名字说人话的 setter；
  ② 执行器每零件一行短式子，不拿表达式做循环展开；
  ③ 缩放交给 IC 的 min/max 属性，式子里留物理量；
  ④ 状态与记忆用内置三原语：clamp01(Time*k) 软启动 / smooth(x,9999*flag) 冻结 / 边沿比较；
  ⑤ 逻辑在数值域写：-A 取反、A&B、A|B，不写 ((X?1:0)>0.5)；
  ⑥ 观测用 Label 的 designText 里的 {表达式}，不再拿绑轴的遥测当仪器。

本版安全设计：**律只写在零件式里、只读控制轴与内置量，不依赖任何面板量** ——
这样即使面板整体编译失败（app59 那类全灭），飞机照飞，我们只是丢了读数（顺带复测 §29）。
"""
import os, re, sys, io, math, time, hashlib

try:                                 # 控制台是 GBK：✓/⇒ 这类字形编码不了会直接崩在 print 上，
    sys.stdout.reconfigure(errors="replace")   # 而崩在收尾 print 时文件其实已经写完了——最阴的一类假失败
except Exception:
    pass

NOMFD = "--nomfd" in sys.argv   # 默认**保留** MFD（用户否决摘零件方案）；--nomfd 才摘
GEARTEST = "--geartest" in sys.argv  # 旧别名，已并入 --probeic（2026-09-25 探针 B 成立后作废）

CRAFT = os.path.expandvars(
    r"%USERPROFILE%\AppData\LocalLow\Jundroo\SimplePlanes 2\Crafts\TESTaircraft2.xml")
FINGERPRINT = os.path.join(os.path.dirname(CRAFT), ".ft-ta2-fingerprint.json")

# ── 面板（Droplet 写法：每条一个物理含义）─────────────────────────────────
# `arm` 是给 §29 复测用的：面板能否读 ActivateN。律不依赖它，只影响 Label 显示。
# ── 跑道表（源=analysis/data/runway-locations.json —— Lua 时代从地图硬标的绝对坐标）──────
# 13 条真跑道（另有 2 直升机坪 / 2 弹射器，跳过）。`pos`="lon,elev,lat"，`rot`.y=航向。
import json as _json
def load_runways():
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "runway-locations.json")
    _d = _json.load(io.open(_p, encoding="utf-8"))
    _out = []
    for _e in _d:
        if ("Helipad" in _e["name"]) or ("Catapult" in _e["name"]):
            continue   # 只要真跑道（Bannock 的取名是 Station，别再按 Airport 过滤）
        _lon, _elev, _lat = [float(v) for v in _e["pos"].split(",")]
        _hdg = float(_e["rot"].split(",")[1])
        _out.append((_e["name"].replace(" Airport", "").strip(), _lat, _lon, _hdg, _elev))
    return _out

RWYS = load_runways()

# 面板顺序铁律：只能引用排在它前面的名字 ⇒ ① 状态/门控 → ② 走廊几何 → ③ 闸门 →
# ④ 逐级选择链（最近者，比较键=链自身 carry 的 best SD）→ ⑤ 消费（横向/纵向律量）。
PANEL = [
    ("boot",   "clamp01(Time * 0.25)"),                       # 4 s 软启动
    ("cmdPhi", "-60 * Roll"),                                 # 杆量→坡度指令（飞行员）
    ("vs",     "rate(Altitude)"),                             # 爬升率
    ("airb",   "clamp01((AltitudeAgl - 5) / 5)"),             # 空中门（地面外环不出手；SC-1 滑跑滚翻账）
    ("hold",   "smooth(((abs(Roll) > 0.05) | (abs(Pitch) > 0.05)) ? 0 : 1, 2)"),  # 手操让位/松杆 0.5 s 淡入
    ("RCAP",   "IAS * IAS / 13.5"),                           # 55° 坡切线捕获半径（走廊 |LT| 窗用）
    ("vsLim",  "(IAS > 42 ? 20 : 5)"),                        # 高度环权限（<150 kph 收 ±5）
    # 自动刹车的**升空锁**：出生就在跑道上，AGL/近场条件与"落地滑跑"长得一模一样——
    # 没有这把锁，开机第一秒就把满刹车压在轮子上，油门再大也起不来（不可复现的"卡在跑道"）。
    # sum((cond)?1:0) 是 ∫dt：离地 30 m 以上累计 1 s 即置 1，一次飞行内有记忆、面板死则=0（失效安全）。
    ("airEver", "clamp01(sum((AltitudeAgl > 30) ? 1 : 0))"),
]
for _i, (_nm, _lat, _lon, _hdg, _el) in enumerate(RWYS):
    _h = math.radians(_hdg); _c, _s = math.cos(_h), math.sin(_h)
    # SD=(阈值−P)·ĥ（阈值在前为正）；LT=(P−阈值)·(s,−c)（正=中线左侧，与 bankTrk 的符号推导一致）
    PANEL.append(("SD%d" % _i, "(%.1f - Latitude) * %.6f + (%.1f - Longitude) * %.6f" % (_lat, _c, _lon, _s)))
    PANEL.append(("LT%d" % _i, "(Latitude - %.1f) * %.6f - (Longitude - %.1f) * %.6f" % (_lat, _s, _lon, _c)))
for _i, (_nm, _lat, _lon, _hdg, _el) in enumerate(RWYS):
    # 【v1.6 过阈值悬崖】旧闸门 `SD > -50` ⇒ **一起过阈值走廊就消失**，`altTgt` 从"场高"跳到
    # VTOL 旋钮那 500 m ⇒ 律在 19 m 高度猛拉机头（用户 2026-09-25："触发复飞了还是怎么滴"；
    # 实测 AGL 19→17 时 pa −0.7°→+7.6°、AGL 被拉到 49 m、IAS 68→42 再掉回来拍地）。
    # 修：**走廊要活到滑跑段**——阈值后 3.5 km 内、且 AGL<100 时仍算在走廊里。
    #   `AGL<100` 这道守卫防"刚起飞/低空掠过机场"时被身后的走廊按住不让爬（留空门仍有效）。
    PANEL.append(("G%d" % _i,
                  "((SD%d > -50) | ((SD%d > -3500) & (AltitudeAgl < 100))) & "
                  # 窗宽上限 1800 m：`2*RCAP` 是按 IAS² 放的，而 IAS 传感器在触地/变形时会跳出
                  # 100+ m/s 的假数（app88 坠机帧 IAS 132 / GS 38）⇒ 窗宽能从 900 暴涨到 2600 m，
                  # 把同场的横交跑道整个请进候选集。限死在 1800 m：真需要宽窗的高速进场照样覆盖。
                  "(abs(LT%d) < max(900, min(2 * RCAP, 1800))) & (SD%d < 15000)" % (_i, _i, _i, _i)))
# ── v2.7 跑道选型 = **机头前向锥内最近**（对齐 Lua 版 SC-3b；此前是"全场 |SD| 最小"，会选到身后的）──
# BG_i = 从本机看第 i 条跑道**入口**的方位（世界系）：V=本机→入口，在 (ĥ, 右法) 基下分量 = (SD, −LT)
#        ⇒ BG = HDG_i + atan2(−LT_i, SD_i)（FT 三角按度）。
#        （注：v2.23 取证怀疑此符号镜像了真方位；但上一版实飞"能落"就是按此式，回退先照旧，M3 重做时一起重推。）
# DS_i = 本机到入口的距离（sqrt 而不是 |SD|：斜着进近时 |SD| 会骗人）。
# 锥门只加在"入口还在前方"（SD>0）的候选上：刚过阈值那条 SD<0，若也套锥就重演 v1.6 的过阈值悬崖。
# 反向端头（04L↔22L，SD≈−整条长）靠"距离最小"输给我们自己刚过的那条，不靠 |SD|  tricks。
for _i, (_nm, _lat, _lon, _hdg, _el) in enumerate(RWYS):
    PANEL.append(("BG%d" % _i, "%d + atan2(0 - LT%d, SD%d)" % (_hdg, _i, _i)))
    PANEL.append(("DS%d" % _i, "sqrt(SD%d * SD%d + LT%d * LT%d)" % (_i, _i, _i, _i)))
# ── 选场 v2.19（M1 移植 SC-3b v4.35 两级制）：**指向优先**（安全版：只认已在中线走廊里的场，绝不远处抓） ──
RUN_PRI = 45
_prevP = ("9999999", "-9999999", "-9999999", "0", "9999999", "0")
_prevF = ("9999999", "-9999999", "-9999999", "0", "9999999", "0")
for _i, (_nm, _lat, _lon, _hdg, _el) in enumerate(RWYS):
    _pPS, _pPL, _pPT, _pPD, _pPP, _pPU = _prevP
    _pFS, _pFL, _pFT, _pFD, _pFP, _pFU = _prevF
    PANEL.append(("K%d" % _i,
                  "((G%d) & (((SD%d < 0) & (abs(LT%d) < 300)) | (abs(deltaangle(BG%d, Heading)) < 60))"
                  " & (abs(deltaangle(%d, Heading)) < 35 + clamp(DS%d / 50, 0, 55)))"
                  % (_i, _i, _i, _i, _hdg, _i)))
    PANEL.append(("PR%d" % _i, "(smooth((abs(deltaangle(BG%d, Heading)) < %d) ? 1 : 0, 2) > 0.5)" % (_i, RUN_PRI)))
    PANEL.append(("KP%d" % _i, "(K%d & PR%d & (DS%d < %s))" % (_i, _i, _i, _pPS)))
    PANEL.append(("PS%d" % _i, "(KP%d ? SD%d : %s)" % (_i, _i, _pPS)))
    PANEL.append(("PL%d" % _i, "(KP%d ? LT%d : %s)" % (_i, _i, _pPL)))
    PANEL.append(("PT%d" % _i, "(KP%d ? %d + 0.0524 * max(SD%d, 0) : %s)" % (_i, _el, _i, _pPT)))
    PANEL.append(("PD%d" % _i, "(KP%d ? %d : %s)" % (_i, _hdg, _pPD)))
    PANEL.append(("PP%d" % _i, "(KP%d ? BG%d : %s)" % (_i, _i, _pPP)))
    PANEL.append(("PU%d" % _i, "(KP%d ? 1 : %s)" % (_i, _pPU)))
    PANEL.append(("KF%d" % _i, "(K%d & (DS%d < %s))" % (_i, _i, _pFS)))
    PANEL.append(("FS%d" % _i, "(KF%d ? SD%d : %s)" % (_i, _i, _pFS)))
    PANEL.append(("FL%d" % _i, "(KF%d ? LT%d : %s)" % (_i, _i, _pFL)))
    PANEL.append(("FT%d" % _i, "(KF%d ? %d + 0.0524 * max(SD%d, 0) : %s)" % (_i, _el, _i, _pFT)))
    PANEL.append(("FD%d" % _i, "(KF%d ? %d : %s)" % (_i, _hdg, _pFD)))
    PANEL.append(("FP%d" % _i, "(KF%d ? BG%d : %s)" % (_i, _i, _pFP)))
    PANEL.append(("FU%d" % _i, "(KF%d ? 1 : %s)" % (_i, _pFU)))
    _prevP = ("PS%d" % _i, "PL%d" % _i, "PT%d" % _i, "PD%d" % _i, "PP%d" % _i, "PU%d" % _i)
    _prevF = ("FS%d" % _i, "FL%d" % _i, "FT%d" % _i, "FD%d" % _i, "FP%d" % _i, "FU%d" % _i)
_HAS_P = "(%s > 0.5)" % _prevP[5]
_HAS_F = "(%s > 0.5)" % _prevF[5]
PANEL += [
    ("rwyPri", "(" + _HAS_P + ") ? 1 : 0"),
    ("rwyOk",  "(" + _HAS_P + " | " + _HAS_F + ") ? 1 : 0"),
    ("SD",  "((" + _HAS_P + ") ? %s : %s)" % (_prevP[0], _prevF[0])),
    ("LT",  "((" + _HAS_P + ") ? %s : %s)" % (_prevP[1], _prevF[1])),
    ("TLA", "((" + _HAS_P + ") ? %s : %s)" % (_prevP[2], _prevF[2])),
    ("HDG", "((" + _HAS_P + ") ? %s : %s)" % (_prevP[3], _prevF[3])),
    ("BRG", "((" + _HAS_P + ") ? %s : %s)" % (_prevP[4], _prevF[4])),
    ("trkNow", "atan2(rate(Longitude), rate(Latitude))"),     # 当前地速航迹（rate() 开头几帧不可信，见 trkGd）
    ("trkGd",  "((Time > 0.5) & (AltitudeAgl > 20) & (GS > 25))"),
    ("trkUse", "trkGd ? trkNow : Heading"),                   # 起步/地面/低速 → 用机头方向当代理
    # ★风的反演（app88 结案：320 kph 阵风在进近途中立起来，我把"空速与地速分道 100 m/s"误判成掉件，
    #   其实完全相容：IAS=相对空气、GS=相对地，|W|=89 m/s 时两者差 100 m/s 是算术必然。）
    #   律手里只有 IAS/GS/Heading/trkNow 四个量，风是**推**出来的：机头与地速航迹的夹角=蟹角，
    #   侧风分量 = IAS·sin(蟹角)，顺逆风分量 = IAS·cos(蟹角) − GS。
    #   必须排在 trkNow/trkUse 之后：面板只能引用排在前面的名字（引用闸实测拦下过一次）。
    ("CRAB",   "trkGd ? deltaangle(trkNow, Heading) : 0"),
    ("XW",     "IAS * sin(CRAB)"),
    ("HW",     "IAS * cos(CRAB) - GS"),
    ("xtrk",   "(SD < 15000) ? LT : 0"),                      # 横偏（米；走廊外不做横向修正）
    ("trkEr",  "(SD < 15000) ? deltaangle(trkUse, HDG) : 0"), # 航迹误差 vs 跑道航向
    # 前置角 = **按转弯半径算的提前量**（用户 2026-09-25 点名的做法）：
    # R = GS²/(g·tan30°) = GS²/5.66（30° 坡的转弯半径）；看向"前方 R 处的中线点"⇒ 前置角 = atan(横偏/R)。
    # 物理含义：速度越快 R 越大、前置角越小（温和）；越慢 R 越小、越紧；对准时 atan(0)=0 自动归零。
    # （app31 定罪：固定 0.06/0.12 双调度在高速段仍嫌"转向太慢"。）
    ("Rturn",  "GS * GS / 5.66"),
    ("LEAD",   "clamp(atan(xtrk / max(400, Rturn)), -45, 45)"),
    ("bankTrk", "-clamp(trkEr + LEAD, -30, 30)"),
    # 高度目标：min(VTOL 旋钮, 走廊道线高)；走廊外只用 VTOL（避免哨兵值参与 min）
    # 【v2.15 诊断作废·用户 2026-09-26 纠正】我曾把"起飞超调"归因到"7 层着陆分支被误触发"。
    #   用户反问"没开 7 怎么会被当成着陆"——对。核代码：`Activate7` 关时 ELE 用 `cmdTheF`，
    #   而 cmdTheF* 只用 `vsErrH/altTgtH`（旋钮），`altTgt/TLA/拉平` 一个都不进 8 层通路 ⇒ **7/8 未耦合**。
    #   所以那个归因只对"7 挂着起飞"成立；本例 7 关 ⇒ 病在 **8 层环自身**，见 cmdTheF_I 处（积分饱和）。
    ("altTgt", "min(VTOL > 0 ? 500 + 1500 * VTOL : 500 + 500 * VTOL, (SD < 15000) ? TLA : 9999999)"),
    # M4 只读第一步——"能否在最大下滑角内接住"的余量（米）：>0 = 现有五边接不住（太高/距离不够），需消高盘旋。
    #   可下滑最陡正切 tanG = sinkMax/GS（与 vsCmd 下沉预算同式）；场高 el = TLA − 0.0524·max(SD,0)；
    #   沿 γmax 从当前高度到入口能落到的地板 = el + SD·tanG ⇒ htExcess = 高出该地板多少。走廊外=0。
    ("tanG",     "clamp(GS * 0.12, 3, 7) / max(GS, 5)"),
    ("fldE",     "TLA - 0.0524 * max(SD, 0)"),
    ("htExcess", "(SD < 15000) ? max(0, (Altitude - fldE) - SD * tanG) : 0"),
    # 道线自身以 0.0524·GS 下沉（85 m/s 时 4.5 m/s）⇒ 纯 P 追斜坡的稳态误差=斜率/增益=18 m
    # （app30 实测 +16~+18 m 恒定滞后，与 SC-5 当年同案）⇒ 补上前馈项。
    # v1.6：前馈**只对斜坡段有效**（`SD > 0`）——过阈值后道线是平的（`max(SD,0)`），
    #   再减 0.0524·GS 就等于凭空要 3.4 m/s 额外下沉，正好压在拉平段上。
    # 【v2.3 前馈定标（含一次我自己差点写反的符号）】要追的道线 H=elev+0.0524·max(SD,0)，
    # 其**时间导数** = 0.0524·rate(SD)（进近时 rate(SD)<0 ⇒ 该项为负 ⇒ 正确地"要下沉"）。
    # 旧写法 `− 0.0524·GS` 用的是地速而非**沿跑道轴的接近率**：顺风/侧滑/CRAB 时两者差 30+ m/s，
    # 而且 `GS` 恒正 ⇒ 符号是"碰巧对"的。现在直接用 `rate(SD)` 并把 `rate()` 钳住（法典：rate 必钳，
    # 走廊切换那一拍 SD 会跳变 ⇒ 不钳就是一个巨型尖峰）。
    # 另注：`TLA` 到阈值就止于场高（本来就该这样），所以"目标在降"不是病；病在下面那条积分门。
    # vsLine=道线本身要的垂直速度（3° 线在 SD→0 时**直接扎进场地**，所以低空必须让位给拉平项）
    ("vsLine", "0.25 * (altTgt - Altitude) + (((SD > 0) & (SD < 15000)) ? 0.0524 * clamp(rate(SD), -160, 160) : 0)"),
    # ★v2.7.2 拉平（app86 血的教训：30 m 以下下沉率从 3.1 涨到 9.6 m/s、pa 反而 −1.1° ⇒ 拍地）。
    #   现实程序=指数收光：vs_flare = −0.10·agl（25 m→−2.5、10 m→−1.0、4 m→−0.4；50 m/s 平飞下时间常数 10 s ⇒ 飘 ~500 m）。
    #   只在 agl<30 生效、且只把指令**改浅**（max），绝不比道线更陡；15 m 以下原有 `cmdThe ≥ 6°` 地板继续兜底。
    #   系数含 GS：**按地速收高**才与风无关（时间常数版在逆风里飘得短、顺风里飘得长，接地点散布 ∝ V²）；
    #   D=300 m ⇒ 衰减长度 agl(x)=agl0·e^(−x/300)，50 m/s 时等效 −0.06·agl/秒·米。
    #   D=300 被 app87 判死：GS=66 时它只在 agl<15 m 才比道线浅（−agl·GS/300 > −3.4 ⇒ agl<15.5），
    #   实测 14 m 还带 −4.5 m/s 下沉 ⇒ 拍地后弹起 12 m（豚跳）。D=480 ⇒ 25 m 起收光（τ≈7 s）。
    #   下限 0.4 m/s：3 m 以下不再要求更浅（否则贴地拉不平、平飘过长）。
    # ★★v2.21（M2 第一刀）下沉指令按地速物理钳 —— 治 L1 短接 / L2 撞岸（2026-09-26 cid=7489）
    #   病：旧 `vsCmd=clamp(…, -vsLim, vsLim)` 且 vsLim=IAS>42?20 ⇒ 远高于线时 0.25·Δh 能要到 **−20 m/s 下沉**
    #        (≈18° 下滑)，而 3° 道线真实下沉只 0.0524·GS≈2.8 m/s ⇒ 用 7 倍下沉追线 ⇒ 冲过线下 ⇒ 近地已在线下 ⇒ 短接/撞水。
    #   SC-3b v4.28 原话：『能瞬态落地的下沉 ≠ 能持续飞道的下沉』。修＝**下沉预算挂地速**：
    #        下钳 −clamp(GS·0.12, 3, 7)（最大约 7° 下滑角，低速收到 3）；上钳 +3（低于线允许缓爬回线，不再一路低到撞地）。
    #   拉平项(AGL<34)仍走 max(vsLine,−收光)，只在**正在下沉**时生效。
    # 【v2.27 用户定：爬升预算 3→7（对"低于道线爬不回"掉海的修正）】上钳由死 `3` 改成**与下沉对称的
    #   `clamp(GS·0.12, 3, 7)`**（巡航/进近速度下=7 m/s，低速自动收到 3，免低速猛拉机头）；仍只在 7 层通路消费。
    ("vsCmd",  "clamp((AltitudeAgl < 34) ? max(vsLine, -clamp(AltitudeAgl * clamp(GS, 20, 90) / 480, 0.4, 6)) : vsLine, -clamp(GS * 0.12, 3, 7), clamp(GS * 0.12, 3, 7))"),
    ("vsErr",  "vsCmd - vs"),
    # 近区积分（|vsErr|<4 m/s 才积）：大误差段交给 P+前馈，避免积分攒大风车后顶着不放
    # 【v2.4】旧门 `abs(vsErr) < 4` 是**这场事故的直接原因**：撞水前 vsErr 一路 4.4，刚好卡在门外
    # ⇒ 积分被冻死 ⇒ 只剩纯 P 姿态环（内环 0.040/°也是 P）⇒ 留下 ~2.4° 永久姿态偏置
    # ⇒ `pa` 死钉 1.1°、下沉 −2.7 m/s 永不修正 ⇒ "飞机没打算去目标高度"（用户判语，正确）。
    # 修：**门放宽到 10 m/s、积分速率降到 0.35**（原来是"门内 1.2/单位秒"，太凶容易攒风车）。
    # 门仍要留：大误差段（比如高 200 m 截获）该由 P+前馈干活，别让积分提前攒满顶着不放。
    # 【同形隐患·挂账，暂不动】7 层的 vsInt 也有同一道 `abs(vsErr)<10` 误差门（同因）。但用户实测
    #   7 层着陆跟随良好、且"无论 7 是否开、稳态误差只在**再起飞后**出现"指向的是 8 层定高环 ⇒
    #   **不为没坏的通道冒险**，只改 vsIntH；若哪天 7 层复飞/再进近也出现遗留偏差，照 vsIntH 同法去掉误差门。
    ("vsInt",  "clamp(sum((((abs(Roll) < 0.05) & (abs(Pitch) < 0.05)) & (abs(vsErr) < 10)) ? vsErr * 0.35 : 0), -20, 20)"),
    # 拉平（v1.1 加）：AGL<15 m 时姿态指令至少 +6°（把机头抬起来），仍受下游失速门约束。
    # ── v2.8 双模式分离（用户 2026-09-26 定："必须分离降落模式和持存的稳定模式"）──────────
    #   8 号组 = **持存稳定模式**（app88 结案：组 8 上电即 true ⇒ 它只能当常驻底层，不能当人工开关）：
    #     只把杆量映射成姿态/坡度指令、松杆回平回中，不碰构型/油门/刹车/道线。
    #   7 号组 = **降落模式**（人工按才有）：走廊+3° 道线+拉平+自动放轮+滑跑刹车+反推+进近油门管理。
    #   面板读不到 ActivateN（§29 + app59 整面死），门一律写在**零件表达式**里（app62/63 已证可读）；
    #   面板只把两套指令各算一份：cmdTheF/phiCmdF=纯姿态增稳，cmdThe/phiCmd=带航迹航径修正。
    # ── 8 层专用：**定高**（目标只认 VTOL 旋钮那条，绝不掺走廊道线）──────────────────
    #   v2.8 我分过头了：把整条航径修正（含定高）一起塞进 7 号 ⇒ 持存模式里松杆只剩"姿态回平"，
    #   高度随气流走。用户 2026-09-26 指出"定高怎么不在 8 里生效"⇒ 现拆开：
    #   8 = 杆→姿态 + 定高(vsErrH/vsIntH)；7 = 在此之上换成"走廊道线 + 拉平"并接管构型/油门/刹车。
    ("altTgtH", "VTOL > 0 ? 500 + 1500 * VTOL : 500 + 500 * VTOL"),
    ("vsCmdH",  "clamp(0.25 * (altTgtH - Altitude), -vsLim, vsLim)"),
    ("vsErrH",  "vsCmdH - vs"),
    # ★★撤回 v2.12 的"去掉误差门"（2026-09-26，用户实测反打）：去掉门后，**从跑道起飞这一整段大误差爬升
    #   被全力积分** ⇒ `vsIntH` 一路顶到 +15 ⇒ 顶部**大幅超调**（实测 pa 冲到 +8°、高度越过目标 20+ m），
    #   随后积分器穿越零点退绕时**姿态骤然回抽**（pa 7.6°→0.2° 仅 0.3 s，pr 冲到 +28°/s）⇒ 用户判"不是健康的控制律"，完全正确。
    #   这正是 v2.4 注释里警告过的"积分提前攒满顶着不放"——我上一次为了治"遗留旧值"把门删了，等于把风车又装回去。
    #   ⇒ **恢复误差门**（爬升这种大误差段不准积），先把超调／抽回消掉；"再起飞后的稳态误差"另找正解，
    #   不再拿积分门当唯一旋钮来回拧（门是"积不积"，稳态误差是"积多少、遗留值怎么清"，是两件事）。
    # ★★★v2.14 定高环正解 = **条件积分（抗饱和）**，2026-09-26 用户读数定案。
    #   用户实测两态：标定 274 → 一路爬到 336（再缓升到 400）；读数 vsCmd/vs/vsInt = −20/+1.2/**−12.8（恒定）**。
    #   诊断：`|vsErrH|≈16>10` ⇒ 误差门关闭 ⇒ **积分器冻结在遗留值**；而这个遗留值在 P 之外持续顶着机头
    #   ⇒ P 项压不住 ⇒ 抬头缓爬跑飞（2389 那次是快跑飞，这次是慢跑飞，同一个"门冻住遗留值"）。
    #   ⇒ 结论：**误差门（拿"误差大小"当积分开关）此路不通**——关了会冻住遗留值→跑飞，全开会把整段爬升积进去→超调。
    #   正解是教科书 **条件积分**：**当 P 项自己还没饱和时才积分**（P 已饱和=正在做大幅机动，积分只会攒假账）。
    #   实现要点：把"纯 P 指令"`cmdTheF_P` 先算出来（**排在积分器之前**，不引用 vsIntH ⇒ 无自引用、无前向引用），
    #   积分门只加一条 `abs(cmdTheF_P) < 25`：
    #     · 从地面爬升：P=0.8×(274−0)≈+52 ≫ 25 ⇒ **不积** ⇒ 无超调（治 v2.12 的病）；
    #     · 高于目标：P=0.8×(−16)≈−13 < 25 ⇒ **照常积**（负向）⇒ 退绕 ⇒ 不再冻住跑飞（治 2389/本局的病）；
    #     · 平飞近目标：P≈0 ⇒ 正常积 ⇒ 消稳态误差（治 +18 的病）。
    #   一个门同时关掉三种病，且不碰 HUD、不碰 7 层在用通道、不做自引用。
    # ★★★v2.16 起飞超调的**真**根因（7 关、8 层环自身）：爬升段积分饱和。
    #   起飞时飞机远低于目标 ⇒ `vsCmdH` 顶到 +vsLim(高速 20) ⇒ `vsErrH≈+20`；于是
    #   `cmdTheF_P = 0.8×20 = +16°`，而 v2.14 的门 `|cmdTheF_P|<25` 判"没饱和"⇒ **放行积分** ⇒
    #   `cmdTheF_I` 一路顶到 +20 ⇒ `cmdTheF = 16+20 = +36°` 巨抬头 ⇒ **超大超调**；到目标附近误差反号，
    #   积分器从 +20 慢慢退绕 ⇒ **回正延迟**；退过零 ⇒ 恢复正常。**与用户观察逐条吻合。**
    #   根治＝教科书 **按"速率指令饱和"做条件积分**：`abs(vsCmdH)` 顶到 vsLim 时（=俯仰环已被迫输出极限爬升率，
    #   此时积分只会攒假账）**不积**；只有 `vsCmdH` 未饱和（已在目标 ±4·vsLim 内）才积。
    #   这同时天然避开旧坑：**"积分器不会被喂到饱和"**，所以不存在"冻结在饱和值"（2389 跑飞）也没有"整段爬升积进去"（v2.12 超调）。
    ("cmdTheF_P", "min(-30 * Pitch + hold * airb * (0.8 * vsErrH), (IAS < 45 ? 8 : 90))"),
    # ★★★v2.17 根因定案（2026-09-26，用户"第1→2遍重开、第2→3遍只落地再起飞就坏"给的关键对照）：
    #   cid=73802 同会话三次起飞实测——好的两遍爬升段积分项 I≈−4 / 恒 8.0°；坏的第 3 遍 **I≈+16、恒 20.7°**
    #   ⇒ 同一个律、同一操作，积分项差了 20°，唯一的差别是"第 2→3 遍之间没重开、`sum()` 不清零"
    #   ⇒ **坏起飞 = 带着上一架次的积分残留起飞**（这正是从 2389 到现在的总根，我前面一直在调门、没治"清零"）。
    #   修：给积分器加**退绕支** `sum(gate ? err*0.35 : −cmdTheF_I*1.5)`——门内正常积、门外（地面/大瞬态）
    #   按 τ≈0.67 s 把积分拉回 0 ⇒ 落地几秒内清零 ⇒ 下一架次从 0 起，与"重开"等价。
    #   FT 无内置抗饱和，自参照(引用自身上一帧值)是唯一写法；已在 ALLOW_SELFREF 白名单显式放行。
    ("cmdTheF_I", "clamp(sum(((abs(Roll) < 0.05) & (abs(Pitch) < 0.05) & (abs(vsCmdH) < (vsLim - 0.5))) ? vsErrH * 0.35 : (0 - cmdTheF_I * 1.5)), -20, 20)"),
    ("cmdTheF", "min(cmdTheF_P + hold * airb * cmdTheF_I, (IAS < 45 ? 8 : 90))"),
    # ★★v2.20 拔掉"低空钉子"（2026-09-26 用户："7 开平飞段不定高，飘在海平面上几米"）：
    #   数据（cid=2389 末段）：飞机在 **AGL 8~20 m 带里连挂 85 s + 40 s**（t=134-219、279-319），
    #   alt≈12 m / pa≈+3° / ias≈62 —— 不是"不定高"，是**卡在 12 m 下不去**（"飘在海平面上几米"）。
    #   机制：7 层 `cmdThe` 的**硬地板 `(AGL<15)?6:-90`**。下降接近 15 m ⇒ 地板抬到 +6° ⇒ 抬头 ⇒ 停在 ~12 m；
    #   AGL 稍过 15 ⇒ 地板变 −90 ⇒ 低头 ⇒ 又掉回来 ⇒ **15 m 处极限环**，且**永远触不了地**（地板不许低于 +6）。
    #   而拉平本来已由 `vsCmd` 的拉平项（按 AGL 收光下沉率）负责——这道地板是**重复覆盖且互相打架**。
    #   修：把"按 AGL 硬切"换成**按下沉率的连续防砸地板** `clamp(0.9*(-vs-1.5),0,8)`：
    #   只在**下沉 >1.5 m/s** 时抬机头（防砸），平飞/轻下沉时地板=0 ⇒ 能落地；对 vs 连续 ⇒ 无阈值抖动。
    #   （同族两次前科：`vs<0` 门、app88 跑道跳——**硬阈值=抖振源**；此处连根换成连续量。）
    ("cmdThe",  "min(max(-30 * Pitch + hold * airb * (0.8 * vsErr + vsInt), clamp(0.9 * (0 - vs - 1.5), 0, 8)), (IAS < 45 ? 8 : 90))"),
    ("phiCmdF", "cmdPhi"),
    ("phiCmd",  "cmdPhi + hold * airb * bankTrk"),
    # ── v2.0 能量环（用户 2026-09-25 深夜授权"油门 + 空中减速板都给你，但这俩不能打架"）──────
    # 打架的解法不是"协调"，是**在空速轴上分区、互斥、留死区**（SC-3b v4.8 同族教训）：
    #   IAS < VAPP        → 油门加（减速板缴械，因它门在 VAPP+12 之上）
    #   VAPP ~ VAPP+12    → 死区：油门按上式随动、减速板恒 0
    #   IAS > VAPP+12     → 油门此时必然已被 P 式压到 0（0.06·12=0.72 > 任何盘位余量）⇒ 减速板才动
    # ⇒ 两个执行器**在同一空速上永不同时做相反的事**。本机减速板权限实测极大（全开 12 s 吃 20 m/s），
    #   所以顶格只给 **0.4**，且 **AGL<100 m 一律缴械**（拉平段不许突然加阻力）。
    ("VAPP",    "55"),                                     # 五边目标表速 m/s（本机成功局接地 41~45、超速局冲到 77）
    # 用户 2026-09-25 深夜追问"没看到油门管理"引出的边界修正：**律只在走廊内管事**。
    # 上一版 airFly 不看走廊 ⇒ 接通 8 号后连巡航都被锁在 55 m/s（抢了不该抢的权限）。
    # 现在：走廊外（`SD` 哨兵）一律交还油门杆；进走廊才接管，出走廊即交还。
    ("airFly",  "((airEver > 0.5) & (AltitudeAgl >= 3) & (SD < 15000)) ? 1 : 0"),
    ("gndIdle", "((airEver > 0.5) & (AltitudeAgl < 3) & (SD < 15000)) ? 1 : 0"),  # 接地即收光（retard），同走廊域
    # 【v2.4 第二处】旧律 `Throttle + 0.06*(VAPP-IAS)` 是**把杆位当基线**：杆在 0 时律最多给
    # 0.06·4 = 0.24 ⇒ 五边几乎无功率，姿态环再怎么修也追不上道线（这局 t=108 起杆就是 0）。
    # 改成 **`max(Throttle, PI)`**：杆位只当"地板"（你推上去律绝不低于它），
    # 而律自己能靠积分把油门顶到需要的位置（有界积分 + 死区 12 m/s 防风车）。
    ("thrErr",  "VAPP - IAS"),
    ("thrInt",  "clamp(sum(((((abs(thrErr) < 12) & (airFly > 0.5)) ? thrErr * 0.03 : 0))), 0, 1)"),
    # 【v2.27·用户 2026-09-26 "应用 B"：给"低于道线要爬"补能量】自动油门加**道线偏差前馈**——
    #   低于 3° 线(altTgt>Altitude)才多给油（正项、带上限，免风车）；在线/高于线=0，不干扰正常下滑。
    ("thrGlide","clamp(0.01 * (altTgt - Altitude), 0, 0.3)"),
    ("thrPI",   "clamp(0.10 * thrErr + thrInt + thrGlide, 0, 1)"),
    # 三段用乘式拼平（不用嵌套三元，未证的语法不赌）：出生未飞=交还油门杆；空中=P 律；接地=0。
    # 【v2.5】`max(Throttle, thrPI)` 被实飞判死：用户五边把杆推到 1.00 ⇒ 律**零权限**，
    # IAS 被拉到 87.4 m/s（313 kph）、接地还有 48.9 —— "杆位是地板"在"该收油"的场景等于废掉油门环。
    # 改成真实航空器的自动油门做法：**杆位仍当地板（律不许越你往下），但只在没超速时**；
    # 一旦 `thrErr < −8`（比 VAPP 快 8 m/s 以上）律取得**下权**，可以直接收到 PI 值。
    # 两段用 thrRet 乘式拼平（不赌嵌套三元）：thrRet=0 ⇒ max(杆,PI)；thrRet=1 ⇒ PI。
    ("thrRet",  "((thrErr < -8) & (airFly > 0.5)) ? 1 : 0"),
    # 【v2.25·用户 2026-09-26 定：按 7 后油门完全交律接管】去掉 `max(Throttle, …)` 那层"杆位地板"——
    #   空中段油门 = 纯 `thrPI`（飞行员推油门不再抬高它，自动油门独占）；接地=gndIdle 收光；
    #   起飞前在地面(airFly=0、未 idle)仍交回油门杆（否则 7 按在地面推不动、没法起飞）。
    #   注：整段仍受 APP_GATE(=7*boot*rwyOk) 选通 ⇒ 走廊外/未认场时油门照旧归杆，不会把巡航锁进近速。
    ("thrCmd",  "airFly * thrPI + (1 - airFly) * (1 - gndIdle) * Throttle"),
    ("spdBrk",  "((airEver > 0.5) & (AltitudeAgl > 100) & (SD < 15000))"
                " ? clamp(0.08 * (IAS - VAPP - 12), 0, 0.4) : 0"),
    # ★自动反推（本轮新捞到的**唯一可达的停止手段**）：`PropellerAssemblyScript` 第 352 行
    #   `if (... || Data.PitchControlType != Auto || Data.ReversePitch <= 0f) return 0f;` —— 反推 IC
    #   只在 **Auto 恒桨**下被消费，本机 `pitchControlType="Auto" reversePitch="12"` ⇒ 有 12° 反推可用，
    #   而机体把这条 IC 接成 `input="Disabled"`（=关着）。轮刹不可达（直读控制轴）、低速时减速板又无效
    #   ⇒ **要"自动停住"只能走反推**。判据用地速+高度双门：AGL<5 且 IAS<50 才给反推，
    #   免得拉平阶段（还有 54 m/s）提前进反推；地面 AGL 传感器地板是 1.6~2.0，故阈值取 5 不取 1.5。
    ("revOn",   "((airEver > 0.5) & (AltitudeAgl < 5) & (IAS < 50)) ? 1 : 0"),
    # ★起落架/轮刹的**终审订正（2026-09-26 凌晨，用户实测 + 读对脚本类）**：
    #   腿件 `GearLeg-1` 的 IC#0 就是 "Extension Input"，消费者是 `AnimatorScript`：
    #     `InputTargetPercent = Mathf.Clamp01(_inputController.Value)` → `Percent = MoveTowards(..., dt/animationDuration)`
    #     → `GearLegScript.Extension => Percent`，且 `SuppressWheelPhysics = CanRetract && Percent < 0.4`（真收放，不是动画）。
    #   该 IC `min=1 max=0` 而 `UpdateValue()` 是 `num<0 ? |num|*min : num*max` ⇒ **可用量程=输入 [−1,0] → 伸出 [0,1]**
    #     （−1 全放、−0.5 半程、**0 与 +1 同为全收**——这就是本项目 v1.4~v1.7 极性冤案的根）。
    #   轮刹同理可达：`BaseWheelScript.UpdateWheel()` 里 `value = _brakeInput.Value;`
    #     `brakeInput = Clamp01(value + ParkingBrake)`、`value > 0 ? BrakeTorque = value * (ParkingBrake?5:1) * _weightOnWheel * WheelRadius * … : 0`
    #     ⇒ **0=free、1=抱死、只有正半轴有效**，且力矩 `∝ _weightOnWheel` ⇒ **物理自带接地门**，律不必自己判接地。
    #   （此前两版"只读控制轴/无人消费"都读错类：那句 `_wc.SteerAngle`/`_wc.BrakeInput = Controls.*` 属
    #     `LandingGearScript`，那是 `Wheel-1/2/3` **自带轮子**的起落架族，与本机 `GearLeg-1`+`JWheelAssembly-1` 无关。）
    # ★v2.9.4 找到"没用"的真身：旧式 `(... & (AltitudeAgl < 400)) | (AltitudeAgl < 3)` ⇒ **贴地就等于 1**，
    #   于是起飞滑跑/地面滑行时律把腿钉在放下，你按"收"当然按不动（也正是你最早那句"8 的持久存在使我无法正常从跑道起飞"）。
    #   改法：律的"要放"必须来自**真在进近**，不是"在走廊里/贴着地"。
    #   `appr` = 从入口前方 300 m~15 km、高度 25~400 m ⇒ 进近态；
    #   `downLock` = 轮下锁（真机逻辑）：接地累计、离地 30 m 以上倒带 ⇒ 落地后不会被轴弹回收、再起飞又能收。
    #   ★v2.9.5 复算上一局才看清旧式有两处垃圾：①没有下滑判据 ⇒ **爬升段(+1.2 m/s)也被判"进近"而把腿钉住**（你"起飞收不了轮"就是它）；
    #   ②`SD > 300` 让短五边(入口 300 m 内)反而松手 ⇒ 若轴在"收"位，律会在最后几百米**把轮子收回去**。
    #   正解=把"进近"定义成**在往入口方向下降**：`0 < SD < 15 km` & `25 < agl < 400` & `vs < 0`；
    #   `gearHold`=已进近过就保持（复飞不至于当场收轮），爬到 100 m 以上且仍在上升才解除；
    #   `downLock`=轮下锁（接地累加、离地 30 m 倒带）。
    #   ★不设高度下限（v2.9.9）：原来 `agl > 25` 让 **25~3 m 这段"已在下降、尚未接地"没人请求放轮**
    #   ⇒ 键在收位就会收着腿进拉平（我自己真值表里抓到的洞）。地面那一档由 `gndBit` 负责，两者无缝隙。
    ("appr",     "(((SD > 0) & (SD < 15000)) & ((AltitudeAgl < 400) & (vs < 0))) ? 1 : 0"),
    # ★v2.9.6 按用户的规则重写（"7 开 + 处于降落中 ⇒ 律接管；其余 ⇒ 人接管"）：
    #   `landLatch` = 本局进过近就一直记住（clamp01 饱和）。它的解除条件**就是字面上的"把 7 关掉"**，
    #   不需要"先爬升到某高度"才放行 —— 上一版两把锁就是因为解除条件在地面/低空永远走不到，才吞掉了你的权限。
    #   落地后腿保持放下也是靠这条（轴在"收"位时律仍钉住），你要交还给人随时按 7 关。
    # （v2.9.5b 删掉 gearHold / downLock 两把记忆锁：它们的唯一解除条件是"爬到 100/30 m 以上且在上升"，
    #   而他在地面/低空测试时永远走不到那个分支 ⇒ **一旦 sum 累满 1（1 秒就够），律就把腿无限期钉住 = 他"对起落架毫无权限"**。
    #   不需要这两把锁的根据在源码里：`AircraftControls` 构造 `LandingGearDown = true` ⇒ **轴本身就是带记忆的下放请求**，
    #   落地后没人碰 G 键，腿就该继续待在放下位——轴已经替我们记住了，不该再造一个锁去抢人的权限。）
    # （downLock 同删，理由同上）
    # ★v2.9.7 **删掉一切记忆**：上一版 `landLatch=clamp01(sum(appr?1:0))` 只要 1 秒就把腿永久钉住，
    #   而他 7 是按着的 ⇒ 按 G 毫无反应。律对腿的权限从此只有"当前这一帧的条件"，条件一消失立刻全额交还轴。
    ("appr",     "((((SD > 0) & (SD < 15000)) & ((AltitudeAgl > 25) & (AltitudeAgl < 400))) & (vs < 0)) ? 1 : 0"),
    # ★v2.9.6 按用户的规则重写（"7 开 + 处于降落中 ⇒ 律接管；其余 ⇒ 人接管"）：
    #   `landLatch` = 本局进过近就一直记住（clamp01 饱和）。它的解除条件**就是字面上的"把 7 关掉"**，
    #   不需要"先爬升到某高度"才放行 —— 上一版两把锁就是因为解除条件在地面/低空永远走不到，才吞掉了你的权限。
    #   落地后腿保持放下也是靠这条（轴在"收"位时律仍钉住），你要交还给人随时按 7 关。
    # （v2.9.5b 删掉 gearHold / downLock 两把记忆锁：它们的唯一解除条件是"爬到 100/30 m 以上且在上升"，
    #   而他在地面/低空测试时永远走不到那个分支 ⇒ **一旦 sum 累满 1（1 秒就够），律就把腿无限期钉住 = 他"对起落架毫无权限"**。
    #   不需要这两把锁的根据在源码里：`AircraftControls` 构造 `LandingGearDown = true` ⇒ **轴本身就是带记忆的下放请求**，
    #   落地后没人碰 G 键，腿就该继续待在放下位——轴已经替我们记住了，不该再造一个锁去抢人的权限。）
    # （downLock 同删，理由同上）
    # ★v2.9.6 用户规则：`7 开 且 正在降落` ⇒ 律接管；`7 关` ⇒ 人接管。降落=正在朝入口下降；
    #   `landLatch` 让它一旦开始降落就负责到底（落地后不把轮子当"降落结束"当场弹收），
    #   **解除条件是"把 7 关掉"（人在任何时候都够得着），不是"必须先爬升"** —— 上一版两把锁就栽在这。
    # "律要放轮"= 在地面（轮子本就该在下面，也不违反"收轮只归人"：没有航空器在跑道上收轮）
    #   或正在朝入口下降（进近）。**两个条件都是当帧量，没有任何状态**。7 一关或条件一消失 ⇒ 全额交还你的键。
    ("gndBit",  "(AltitudeAgl < 3) ? 1 : 0"),
    ("gearCmd", "max(gndBit, appr)"),
    # 滑跑刹车：只在离地过一次、且贴地时给（`_weightOnWheel` 是第二道保险）；25 m/s 起步、上限 0.85 防抱死拖胎
    #   用户 2026-09-26："轮刹持续时间太短，保持 5s"——旧式在 IAS 掉到 25 就把刹车淡光，
    #   而 25 m/s(90 kph) 还在高速滑跑；现用 `sum()` 当累计刹车秒表（帧率无关的 ∫dt）：
    #   **接地且 IAS>30 期间累计不满 5 s ⇒ 顶格 0.85**；5 s 之后才让速度淡出接手。
    #   空中倒带：离地 20 m 以上每秒 −1 ⇒ 第二次着陆的 5 s 顶格照样有效（sum 无上限，不钳会一直攒）。
    ("brkT",    "clamp(sum(((airEver > 0.5) & (AltitudeAgl < 3) & (IAS > 30)) ? 1 : (((airEver > 0.5) & (AltitudeAgl > 20)) ? -1 : 0)), 0, 60)"),
    ("brkLvl",  "(brkT < 5) ? 0.85 : clamp((IAS - 25) * 0.04, 0, 0.85)"),
    ("brkCmd",  "((airEver > 0.5) & (AltitudeAgl < 3)) ? brkLvl : 0"),
    # **放轮提醒**（手控那一路仍然要提醒：`GearDown` 轴在面板可读，Stormvark 就把它当 `GearCycle` 的源）
    ("gearUp",  "(GearDown > 0.5) ? 0 : 1"),
    # ★放轮请求最高优先（v2.9.2）：**一条表达式里只放一个三元、绝不嵌套**（app89 判决：
    #   嵌套三元 `(A) ? ((B) ? -1 : -gearCmd) : LandingGear` 报 `Unary operator not supported: Equal`
    #   ⇒ 整条式失能、Value 恒 0=全收 ⇒ 他"操作不了起落架"。嵌套是法典明令禁用的形态，我又踩了一遍。）
    # ★v2.9.3 起落架优先级定死成一条规则：**任何"放轮"请求都赢；"收轮"只有飞行员按得出来**。
    #   轴空间（文档 §教程 + AircraftControls.LandingGearLegacyFloat 双重印证）：`LandingGear = +1` 已收起、`−1/0` 已放下。
    #   律这边 `gearCmd` 只在进近走廊内=1 ⇒ `0 - gearCmd` 要么 −1(要放) 要么 0(不表态)：**律没有"收轮"这个动作**。
    #   `min()` 取更负的那个 ⇒ 你放=放、律放=放；只有你按"收"且律不要求放，才 0=收。
    #   （v2.9.1~2 我用 `GearDown ? -1 : -gearCmd` 把这条逻辑写成"仅降落模式内"，方向对但形状错：
    #     非降落模式那条式子退成裸轴，读起来像"优先级只在 7 里"——现在两态同一规则，一眼看得懂。）
    # 混合式（无嵌套三元）：进过近 ⇒ 恒 −1(放)；否则 ⇒ 完全等于你的轴（`min(0,轴)` 与本件 Value 语义等价）。
    # ★实测语义（app90，用户读出）：**表达式里的 `LandingGear` 是 0/1 的"收起标志"（1=收起、0=放下），
    #   与出厂接线 `input="LandingGear"` 走的 ±1 轴查找是两回事**（我把两者混用，才把"放下"算成 Value 0=收轮）。
    #   所以这里换算成伸出量：`1 - LandingGear` = 你想要的伸出(0/1)；与律的请求取 max；再取负喂 IC
    #   （该 IC min=1 max=0 ⇒ Value=max(0,-num) ⇒ num=-1 伸出、num=0 收上）。全程 max/减法，无 & |、无三元、无记忆。
    # ★★真凶（v2.10）：在**表达式**里 `LandingGear` 是 0/1 收起标志（app90 实测 L 随 G 键 0↔1），
    #   而腿 IC 是 `min=1 max=0` ⇒ `Value = num<0 ? |num| : num*0` ⇒ **num=0 与 num=1 都得 Value 0 = 收上**。
    #   我把出厂接线照搬成 `... : LandingGear`，等于把腿永久钉在收起位 ⇒ 你说的"操作不了起落架"。
    #   正确换算是 `LandingGear - 1`（放下 0→−1→Value 1 伸出；收起 1→0→Value 0 收上）。
    ("gearAx",  "min(0 - gearCmd, LandingGear - 1)"),    ("lgWarn",  "((SD < 15000) & (AltitudeAgl < 400) & (gearUp > 0.5)) ? 1 : 0"),
]

# ── 执行器（每零件一行；模式开关在**零件上下文**读 ActivateN，app62/63 已证）────────
# 【铁律】一条表达式里**只允许一个三元、绝不嵌套**（app89：`A ? (B ? x : y) : z` 报
#   `Unary operator not supported: Equal` ⇒ 整条失能=该执行器恒 0）。要"按模式选指令 + 按门放行"
#   就写成**加权混合** `G*律 + (1-G)*原生`，G=`(Activate8 ? boot : 0)`——顺带把软启动从硬切变淡入。
# 姿态内环增益**取自已飞验证过的两处**，不新猜：
#   滚转 0.010 / 0.004 = SC-3b 着陆律内环原文（app76 全松杆保持中线 5.7 km 那一套）；
#   俯仰 0.040 / 0.007 ≈ FT-Lite 松杆落地用的 -0.045/-0.007（同量级，略软）。
# 符号按 t31 标定（Roll 轴正→坡度负；Pitch 轴正=推杆→低头；PitchRate 正=低头）：
# 轴 = k·(当前姿态 − 期望姿态) + d·角速率，静止时轴=0 ⇔ 姿态=期望。
# 【门】8 号激活组=**持存稳定模式**（app88 结案：组 8 上电即 true，用户"8 的持久存在"实证）；
#       7 号激活组=**降落模式**（人工按）——构型/油门/刹车/道线全在 7 后面，按 7 才武装。
# 同时串上 `boot`（clamp01(Time*0.25)=2 s 后过半）避免第 0 帧抢杆——软启动原语终于用上。
# 失效安全：面板整块死 ⇒ boot=0 ⇒ 律不接杆，退回原生手动（比"姿态压 0"更好）。
GATE = "(Activate8 & (boot > 0.5))"
AIL = ("(Activate8 ? boot : 0) * clamp(0.010 * (RollAngle - (phiCmdF + (phiCmd - phiCmdF) * ((Activate7 ? 1 : 0) * clamp01(rwyOk))))"
       " + 0.004 * RollRate, -1, 1) + (1 - (Activate8 ? boot : 0)) * Roll")
ELE = ("(Activate8 ? boot : 0) * clamp(0.040 * (PitchAngle - (cmdTheF + (cmdThe - cmdTheF) * ((Activate7 ? 1 : 0) * clamp01(rwyOk))))"
       " - 0.007 * PitchRate, -1, 1) + (1 - (Activate8 ? boot : 0)) * clamp(Trim + Pitch, -1, 1)")
# 方向舵（用户点名"Yaw 得参与航向稳定"）——**app20 试 0.10 被用户判"相当抖"，已回滚到原厂值**：
# 阻尼加大后出现明显抖振 ⇒ 该通道不是"加大增益就行"的事，符号与权限都得先标定。
# 标定办法（待办）：临时把方向舵写成 `GATE ? (Time > 30 ? 0.4 : 0) : 原式`（已知恒定舵步），
# 从 TEL 的 yr/hr/aos 一次读出"正舵=左/右偏"与"舵量→偏航率权限 (°/s per stick)"，
# 再按实测数字写阻尼/协调项。**在此之前不动这条通道。**
RUD = "clamp(Yaw - 0.04 * YawRate, -1, 1)"   # = 原厂式，两个分支同形（等于没改）
RUD_PARTS = ["21"]              # 方向舵
# ── 构型 / 能量通道（2026-09-25 深夜：全部换成**源码级**结论，不再靠观测反推）──────
# 【反编译判决表】每条都标"谁消费这个 IC"，别再凭直觉写：
#   · 起落架腿 `GearLeg-1` IC#0 = **"Extension Input"**，消费者 `AnimatorScript` ⇒ **可达**：
#       `InputTargetPercent = Clamp01(_inputController.Value)` → `Percent = MoveTowards(Percent, Target, dt/animationDuration)`
#       → `GearLegScript`：`Extension => Percent`、`SuppressWheelPhysics = CanRetract && Percent < 0.4`（真收放）
#     量程由 min/max 的**乘子语义**定：`UpdateValue()` = `num<0 ? |num|*min : num*max`，本机 `min=1 max=0`
#       ⇒ **输入 [−1,0] → 伸出 [1,0]**；**0 与 +1 同为全收**（v1.2~v1.7 极性冤案的根，app 系列四版误读的结案）
#   · 轮刹 `JWheelAssembly-1` IC#1（"Brake"）消费者 `BaseWheelScript.UpdateWheel()` ⇒ **可达**：
#       `value = _brakeInput.Value; brakeInput = Clamp01(value + ParkingBrake);`
#       `value > 0 ? BrakeTorque = value * (ParkingBrake?5:1) * _weightOnWheel * WheelRadius * BrakeTorqueMultiplier * 2 : 0`
#     ⇒ **0=free、1=抱死、只吃正半轴**；力矩 `∝ _weightOnWheel` ⇒ **接地判据物理自带**，律侧只需限幅与地面门
#   · （旧判语"只读控制轴/无人消费"全部作废：那是 `LandingGearScript`——`Wheel-1/2/3` 自带轮子起落架族的脚本，
#     本机用的是 `GearLeg-1` + `JWheelAssembly-1`，**同名脚本不等于同族零件**，判可达性必须先按 PartTypes.xml 找对类）
#   · 螺旋桨 `propPitch`（defaultInput=VTOL）：`BladedEngineScript.SetupInput`
#       `if (PitchControlType != Manual) _bladePitchInput.Disabled = true;`
#     本机 = `pitchControlType="Auto"` ⇒ **这条 IC 被 Disabled** ⇒ SC-5"推力阀门在螺旋桨 IC"对本机不成立，
#     顺带把"VTOL 旋钮会不会改推力"这个疑点也一并消掉（不会）。
#   · 发动机 `throttle` IC：`base.ThrottleInput = inputController` ⇒ **油门权限在这里，可达** ✓（用户授权）
#   · 减速板：本局坠海反证它吃 IC（全开 12 s 吃掉 20 m/s）⇒ **可达** ✓（用户授权）
# ⇒ 结论：**四个执行器全可达**——油门（补能量）、减速板（泄能量）、轮刹（滑跑刹车）、腿（自动放轮）；
#   再加反推，停止链齐了，不需要 Lua。
# ★负=放（该 IC min=1 max=0 ⇒ Value=|num| 只吃负输入：−1 全放、0/+1 全收）。
# 优先级（用户 2026-09-26 定）：**非降落模式 = 飞行员的 `LandingGear` 输入绝对最高**（整条式退成裸轴，律一点不掺）；
#   降落模式里也不许跟飞行员抢"放轮"——只要 `GearDown` 为真（他按下来的），律就不得收轮，其余时刻律自己做主。
#   `GearDown` 用官方机体在用的那个布尔轴名（Stormvark 面板 `smooth(GearDown?1:0,0.25)` 同一条），
#   不取 `LandingGear` 的符号：轴符号我们从原厂接线反推是"−1=放下"，但那是推论，别押在安全逻辑上。
# ★统一"降落模式门"（v2.9.8）：**不用 `&`/`|`**。引擎里 And/Or 被强制成 bool+AndAlso（`type = typeof(bool)`），
#   而 bool↔数值转换是 true→1 / **false→−1**、数值→bool 是 `v > 0` ⇒ 拿 `Activate7` 做乘减或用 1−x 都会错一位。
#   所以：`clamp01(Activate7)` 把 −1/1 变成 0/1；`clamp01(boot * 2 - 1)` 让软启动在 2 s 处才过 0.5；两者乘完再 `> 0.5` 得一个干净的 bool 条件。
APP_GATE = "(clamp01(Activate7) * clamp01(boot * 2 - 1) * clamp01(rwyOk) > 0.5)"   # v2.22 M1b：×rwyOk ⇒ 前向无合法跑道时构型/能量/刹车通道全部退出
# 默认=出厂原接法（诊断态）。`--gearprobe` 时改成"t<30 s ⇒ −1 / t≥30 s ⇒ +1"的常量台阶：
#   出厂态下 t=0 腿本来就是放下(−1)，所以 30 s 那一刻如果腿**自己折起来** ⇒ 腿 IC 确实在驱动收放（=我写的东西在拦你）；
#   如果 30 s 前后毫无变化 ⇒ 腿 IC 根本不是收放的驱动者，我此前所有关于"腿可控"的判断全部作废，得回去重读 GearLegScript。
GEAR_EXPR_FACTORY = "LandingGear"
GEAR_EXPR_PROBE = "(Activate7 & (boot > 0.5)) ? LandingGear : LandingGear"   # 只加门、逻辑与出厂完全相同：动=门没事，不动=Activate7/boot 让整条式子失效
# 单条式子、单个三元、无 & |：伸出量 ext = max(律请求, 你想要的伸出)，num = 0 - ext。
GEAR_EXPR = "0 - max((" + APP_GATE + " ? gearCmd : 0), 1 - LandingGear)"
# ★轮刹：轴语义已在 §339-342 源码级确认（IC Value 只吃正半轴：0=free、1=抱死、力矩∝weightOnWheel）。
#   max(Brake, brkCmd) 对 `Brake`-在表达式里的两种可能取值域（±1 或 0/1）都单调安全：
#   飞行员踩深 → 取 Brake（律不抢）；不踩 → 取 brkCmd（律自动刹）。且用 APP_GATE 限定只在 7 号降落模式出手，
#   巡航/正常起飞滑跑（未 arm 7）不掺和 —— 这正是"轮刹时间变短"的根：诊断期曾退回出厂裸轴、忘了重新接上。
BRAKE_EXPR = APP_GATE + " ? max(Brake, brkCmd) : Brake"
THR_EXPR = APP_GATE + " ? thrCmd : Throttle"
# 实际施加到发动机的油门（进 7 时=自动油门 thrCmd，否则=油门杆）——做成一条 setter，
#   引擎通道与座舱 TH 读数**都读它** ⇒ 显示的永远是真值，与杆位/是否接管无关。
PANEL.append(("thrNow", THR_EXPR))
# max(spdBrk, Brake)：律只能"加"减速板，飞行员随时能压更深 ⇒ 结构上不可能抢走手动权限
BRK_EXPR = APP_GATE + " ? max(spdBrk, Brake) : Brake"
# 反推：else 支给**常数 0**，不能写 `Disabled`（那是 IC 的"无输入"哨兵，当变量名引用可能未定义 ⇒ 整式编译失败）
REV_EXPR = APP_GATE + " ? revOn : 0"
# (partType 前缀, IC 序号, 该通道的裸轴名, 要写的值)；序号定位 + 旧值守卫见 main()
IC_CHANNELS = [
    ("GearLeg",           0, "LandingGear", GEAR_EXPR),    # ★腿的伸出量（前缀收窄：别连 GearBay 门一起改）
    ("GearBay",           0, "LandingGear", GEAR_EXPR),    # 前轮舱门跟着腿同步（`min=1 max=0` 同形，"Door Input"）
    ("JPropEngineRadial", 0, "Throttle",    "(thrNow)"),
    ("PropellerAssembly", 0, "VTOL",        "VTOL"),       # BladeAngle：Manual 才被消费，本机 Auto ⇒ 保持原厂
    ("PropellerAssembly", 1, "Disabled",    REV_EXPR),     # ★ReverseThrust：Auto 下才被消费 ⇒ 自动反推
    ("JWheelAssembly",    1, "Brake",       BRAKE_EXPR),   # ★轮刹（#0 是 "Turn"=转向，序号错位=打舵）
    ("AirBrake",          0, "Brake",       BRK_EXPR),     # ★能量环下行执行器
]
# 铁律：**"保持原厂"也必须显式写裸轴名**——只把它从通道表里删掉，上一次试验的式子会原样赖在盘上（真踩）。
# 通道用 **IC 序号**定位 + 旧值守卫（守卫只拦"另一个裸轴名"=序号错位，例如轮的 #0 是 Yaw 转向）。
# 【v2.0 飞行卡】① 油门接管：进近超速时该自动收油、掉速时该自动推——看 Label 39 `thr` 是否随 IAS 动；
#   ② 减速板：只在 IAS > VAPP+12 且 AGL > 100 m 才张开（顶格 40%），拉平段绝不许动；
#   ③ 自动放轮：进走廊(<400 m)腿应自己伸出、离地爬升出了走廊就收回（第 6 只 Label `g1/g0`）；
#   ④ 滑跑刹车：接地且 IAS>25 起自动加刹（上限 0.85），空中因 `_weightOnWheel`≈0 自然无效（同一只 Label `k…`）。
#   判可达性的形式规矩：**先在 `analysis/decomp/PartTypes.xml` 里按 partType 找到 modifier 名，再反编译那个 *Script**；
#   `LandingGearScript`(`Wheel-1/2/3` 族) ≠ `GearLegScript`+`AnimatorScript`(本机腿) ≠ `BaseWheelScript`(本机轮)。

AIL_PARTS = ["11", "30"]        # 副翼（右/左，位置 x=±4.6）
ELE_PARTS = ["12", "17"]        # 升降舵（左/右，位置 z≈−4.07）
# 方向舵 21 保持原生 clamp(Yaw - 0.04*YawRate, -1, 1)，本版不动。

# ── 座舱读数（Label，学 Droplet：designText 里的 {表达式} 由 FT 求值）─────────
# 用户在**设计器里手加了两只 Label**（TextL/TextR，位置在面板前、看得见）⇒ 读数写进他那两只：
# 只改 designText，**不动他设的位置/旋转/字号**；只有一只时用合并行；一只都没有才新建。
# 格式后缀 `;0` 只有编辑器 README 提过、游戏内未证，统一用 round()。
# ── 2026-09-26 v2.18：按用户要求**为长航线飞行重排八只 Label**（去重复、去诊断态）────────
#   两只宽行放"最常瞥"的：速度 / 高度；六只窄行给导航与状态。**诊断用的 C/P/I 全撤**。
#   取量原则：只放"飞的时候真的要看"的——速度、高度、升降率、目标高、航向/航迹差、到跑道距离/横偏、
#   风的反演、油量/油门、构型与模式。**每只 ≤16 字符**（窄框 w≈0.8 约容 13，宽框 1.2 约容 20）。
TXT_LEFT  = "IAS{round(IAS)} GS{round(GS)} m/s"                       # 36 宽行：空速/地速（失速与能量）
TXT_RIGHT = "ALT{round(AltitudeAgl)}m VS{round(vs * 10) / 10} m/s"    # 37 宽行：离地高/升降率（长飞核心）
#   其余六只（19/38/39/40/41/42）按 L 列导航、R 列状态铺：
TXT_LIST = [
    TXT_LEFT, TXT_RIGHT,
    # 19：**当前生效层的目标高**（7 开=道线目标 altTgt，7 关=旋钮 altTgtH）+ 放轮告警
    "TGT{round(((Activate7 > 0) & (rwyOk > 0.5)) ? altTgt : altTgtH)}m{(lgWarn > 0.5) ? &quot; LGUP!&quot; : &quot;&quot;}",
    # 38：航向 vs 航迹（两者之差=偏流角，长飞看风、落地看蟹角）
    "HDG{round(Heading)} TRK{round(trkUse)}",
    # 39：到选中跑道入口的距离(km) + 横偏(m)（长飞末段接管用）
    # 39：到选中跑道入口的距离(km) + 横偏(m) + **选场态**（Ok=有候选 / P=指向优先命中，验 M1 两级制）
    "D{round(SD / 1000)}k XT{round(xtrk)} O{round(rwyOk)} E{round(htExcess)}",
    # 40：风的反演——侧风/顺逆风（IAS·sin/cos 蟹角 − GS），落地可落地性判据
    "XW{round(XW)} HW{round(HW)}",
    # 41：油量% + **实际发动机油门 thrNow**（进 7=自动油门值，否则=油门杆）——真值，非杆位
    "FU{round(Fuel)} TH{round(thrNow * 100)}",
    # 42：构型与模式——起落架(1 收/0 放) + 8=持存稳定(应 1) + 7=降落模式(手动)
    "G{round(LandingGear)} 8{round(clamp01(Activate8))} 7{round(clamp01(Activate7))}",
]
TXT_ONE = ("T2 v0.2 {round(IAS)}m/s {round(AltitudeAgl)}m {round(vsCmd)}/{round(vs)} A7{round(Activate7)}")
LABEL_POS = "0,3.88,2.86"      # 仅在“一只都没有、需要新建”时使用
LABEL_ROT = "270,0,0"
LABEL_FONT = "0.3"        # 用户那只默认 0.5；app5 授权压字号换容量，取 0.3 兼顾可读
# app6 实锤：容量**与 fontSize 无关**（0.5→0.15 显示内容不变，只变小）⇒ 杠杆是框宽 width。
# 做对照实验：id 36 加宽、id 37 保持原样，一局判定。
LABEL_BOX = {"36": ("1.2", "0.3"), "37": ("1.2", "0.3")}

# ── 词法闸（源=反编译 OperatorToken case 表；相等是单 = ；bool→数 False=−1）──
_OPS = {'+', '-', '*', '/', '&', '|', '!', '>', '<', '>=', '<=', '=', '!=', '?', ':', '%'}
_CHARS = set(" \t(),;")


def _ternary_nested(expr):
    """返回 True = 该表达式里有**嵌套**的三元 `a ? x : b`（三元的一个分支里又出现 `?`）。
    平台明令未证且实测会编译失败：app89 的 `Unary operator not supported: Equal` 就是它。
    同级并排的两个三元（如 `min(A ? x : y, B ? p : q)`）是合法的，不算。"""
    depth = 0
    pend = 0            # 当前括号层里已见过的 '?'
    stack = []
    for ch in expr:
        if ch == '(':
            stack.append((depth, pend)); pend = 0
        elif ch == ')':
            d, pp = stack.pop() if stack else (0, 0)
            depth = d; pend = pp
        elif ch == '?':
            if depth > 0:
                return True
            depth += 1
        elif ch == ':' and depth > 0:
            depth -= 1
    return False



def lint(expr, name):
    if _ternary_nested(expr):
        raise ValueError("setter/式 %s 含嵌套三元（平台禁用，编译会整条失能）：%s" % (name, expr[:90]))
    if "==" in expr or "&&" in expr or "||" in expr:
        raise ValueError("%s: 含 ==/&&/|| —— Jundroo 相等是单 = 、与是单 &" % name)
    if re.search(r"\d[eE][+-]?\d", expr):
        raise ValueError("%s: 科学计数法未证实" % name)
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch in _CHARS: i += 1; continue
        if re.match(r"\d", ch):
            i = re.match(r"\d+\.?\d*", expr[i:]).end() + i; continue
        if re.match(r"[A-Za-z_]", ch):
            i = re.match(r"[A-Za-z_]\w*", expr[i:]).end() + i; continue
        m = next((o for o in ('>=', '<=', '!=') if expr.startswith(o, i)), None)
        if m: i += len(m); continue
        if ch in _OPS: i += 1; continue
        raise ValueError("%s: 非法字符 %r @%d" % (name, ch, i))
    if expr.count('(') != expr.count(')'):
        raise ValueError("%s: 括号不配平" % name)

# ── 引用闸：面板 setter 只能引用内置量或**排在它前面**的定义（app59 死法）─────
BUILTIN = set("""Activate1 Activate2 Activate3 Activate4 Activate5 Activate6 Activate7 Activate8
Altitude AltitudeAgl AngleOfAttack AngleOfSlip Brake FireGuns FireWeapons Flaps Fuel GForce GS
GearDown Heading IAS LandingGear Latitude Longitude Pitch PitchAngle PitchRate Roll RollAngle
RollRate TAS TargetDistance TargetElevation TargetHeading TargetSelected Throttle Time Trim VTOL
VerticalG Yaw YawRate
abs acos asin atan atan2 ceil clamp clamp01 cos deltaangle floor lerp lerpangle max min
NumberToBool PID pow rate repeat round sign sin smooth sqrt sum tan""".split())
# 显式放行的自参照 setter（2026-09-26 v2.17）：唯一合法用途 = 给 sum() 积分器加"退绕/清零"支，
# 即 `sum(gate ? err : -self*k)` —— FT 没有内置抗饱和，自参照是"把积分按时间常数拉回 0"的唯一写法。
# 除这个白名单外，自参照一律仍当错误（防手滑写出无定义的环）。
ALLOW_SELFREF = {"cmdTheF_I"}
def check_refs(setters):
    defined = []
    for name, expr in setters:
        for tok in re.findall(r"[A-Za-z_]\w*", expr):
            if tok in BUILTIN or re.match(r"(?i)^activate\d+$", tok) or tok in defined:
                continue
            if tok == name and name in ALLOW_SELFREF:
                continue
            if tok == name:
                raise ValueError("setter %s 自参照" % name)
            raise ValueError("setter %s 引用未定义名 %s" % (name, tok))
        defined.append(name)
    return len(defined)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def esc_label(s):
    """Label 文本专用：先按属性规则转义，再把显式写的 `&quot;` 还原成实体（属性内引号）。"""
    return esc(s).replace("&amp;quot;", "&quot;")


def patch_panel(xml):
    block = "<Variables>\n" + "".join(
        '    <Setter variable="%s" function="%s" priority="0" />\n' % (n, esc(e)) for n, e in PANEL
    ) + "  </Variables>"
    xml, n = re.subn(r"<Variables>.*?</Variables>", lambda m: block, xml, count=1, flags=re.S)
    if n != 1:
        raise RuntimeError("面板替换次数=%d，期望 1" % n)
    return xml


def patch_surface(xml, pid, expr):
    """按**零件 id** 定位（结构锚，不用 input 文本当指纹——规范 36）。"""
    pat = re.compile(r'(<Part id="%s"[^>]*>)(.*?)(</Part>)' % re.escape(pid), re.S)
    hit = [0]
    def one(m):
        body, k = re.subn(r'(<InputController\.State[^>]*input=")[^"]*(")',
                          lambda mm: mm.group(1) + esc(expr) + mm.group(2), m.group(2), count=1)
        hit[0] += k
        return m.group(1) + body + m.group(3)
    xml = pat.sub(one, xml)
    if hit[0] != 1:
        raise RuntimeError("零件 %s 的 IC 替换次数=%d，期望 1" % (pid, hit[0]))
    return xml


def strip_mfd(xml):
    """摘掉 MFD-1 零件及其连接。
    为什么：游戏级 Lua addon（telemetry-addon.lua，打进 resources.assets）是按"机体里有
    MFD 零件的实例"逐架挂钩的——AP 高度环、着陆律、按键回调都挂在那上面。本机改用**纯 FT**
    自持之后，那套 Lua 与 FT 重复，且会 OverrideInput 抢 Pitch/Throttle 轴（与 FT 打架），
    因此**这架机不装 MFD**（别的机体如 TESTaircraft 不受影响，SC-3b 那套原样保留）。
    ⚠ 用户已否决本方案（"移除MFD是什么脑瘫办法"）⇒ 默认不摘。**正解在 addon 侧**：
    把 telemetry-addon.lua 编成 `FT_ONLY = true`（只留遥测、律全停），见该文件顶部说明。
    本函数只在显式 `--nomfd` 时执行。"""
    ids = re.findall(r'<Part id="(\d+)"[^>]*partType="MFD-1"', xml)
    for pid in ids:
        xml = re.sub(r'[ \t]*<Part id="%s"[^>]*partType="MFD-1".*?</Part>\n?' % pid, '',
                     xml, count=1, flags=re.S)
        xml = re.sub(r'[ \t]*<Connection[^>]*part[AB]="%s"[^>]*/>\n?' % pid, '', xml)
    return xml, ids


def write_readouts(xml):
    """把读数写进 Label（designText 的 {表达式}）。
    有 ≥2 只：按 id 顺序前两只分别写 左/右 行；只有 1 只：写合并行；0 只：新建一只。
    对**已存在**的 Label 只改 designText，不动用户设的位置/旋转/字号（那两只他自己摆的）。
    返回 (xml, 说明串)。"""
    pat = re.compile(r'<Part id="(\d+)"[^>]*partType="Label-1".*?</Part>', re.S)
    hits = list(pat.finditer(xml))
    if not hits:
        ids = [int(m) for m in re.findall(r'<Part id="(\d+)"', xml)]
        nid = max(ids) + 1
        lbl = ('    <Part id="%d" partType="Label-1" position="%s" rotation="%s" '
               'drag="0,0,0,0,0,0" dragArea="0,0,0,0,0,0" materials="12,12,12" symmetryDisabled="true" '
               'dragType="None" health="1E+09" partCollisionResponse="None">\n'
               '      <Label.State designText="%s" fontName="Default" fontSize="2.5" '
               'horizontalAlignment="Center" verticalAlignment="Middle" width="0.8" height="1.45" '
               'outlineWidth="0" emissionDay="2" emissionNight="2" offset="0,0.006,0" '
               'rotation="90,0,0" gradient="None" curvature="0" curvatureDirection="Horizontal" />\n'
               '    </Part>\n  </Parts>' % (nid, LABEL_POS, LABEL_ROT, esc(TXT_ONE)))
        xml, n = re.subn(r"  </Parts>", lambda m: lbl, xml, count=1)
        if n != 1:
            raise RuntimeError("</Parts> 定位失败")
        conn = ('    <Connection partA="%d" partB="15" attachPointsA="0" attachPointsB="0" />\n'
                '  </Connections>' % nid)
        xml, n2 = re.subn(r"  </Connections>", lambda m: conn, xml, count=1)
        if n2 != 1:
            raise RuntimeError("</Connections> 定位失败")
        return xml, "新建 id=%d（合并行）" % nid
    texts = list(TXT_LIST) + [""] * 8   # 不足则补空串（不写）
    done = []
    for k, m in enumerate(hits):
        tid = m.group(1)
        blk = re.sub(r'(designText=")[^"]*(")',
                     lambda x, t=texts[k]: x.group(1) + esc_label(t) + x.group(2), m.group(0), count=1)
        # 用户授权：字号压到 0.15（≈原 0.5 的 30%）以容纳更多字；位置与框尺寸不动
        blk = re.sub(r'(fontSize=")[^"]*(")', lambda x: x.group(1) + LABEL_FONT + x.group(2), blk, count=1)
        if tid in LABEL_BOX:
            w, h = LABEL_BOX[tid]
            blk = re.sub(r'(width=")[^"]*(")', lambda x: x.group(1) + w + x.group(2), blk, count=1)
            blk = re.sub(r'(height=")[^"]*(")', lambda x: x.group(1) + h + x.group(2), blk, count=1)
        xml = xml.replace(m.group(0), blk, 1)
        done.append(tid)
    return xml, "写入 %d 只：%s（%s）" % (len(hits), ",".join(done),
                                        "左/右分栏" if len(hits) > 1 else "合并行")



def _sha(path):
    if not os.path.exists(path):
        return None
    return hashlib.sha1(io.open(path, "rb").read()).hexdigest()[:12]


def _check_disk_fingerprint():
    """设计器存盘会把整个机体（含我们 patch 进去的 FT 层）覆盖掉。
    每次 apply 前对一次指纹，被覆盖就当场吼——别再拿"没效果"去猜律。"""
    if not os.path.exists(FINGERPRINT):
        print("指纹：无留档（首次在本目录 apply 前无从比对，跳过）")
        return
    import json
    fp = json.loads(io.open(FINGERPRINT, encoding="utf-8").read())
    bad = []
    for key, path in (("named", CRAFT), ("editor", os.path.join(os.path.dirname(CRAFT), "__editor__.xml"))):
        want = fp.get(key)
        if want is None:
            continue
        got = _sha(path)
        if got != want:
            bad.append("%s：盘上 %s ≠ 上次 apply 的 %s" % (os.path.basename(path), got, want))
    # 字节不等 **不等于**"飞的是旧版"：游戏存盘会把自己的机体重新序列化一遍（字节必变、内容还是那一版）。
    # 所以再按语义核一遍：面板名册 + 执行器通道表达式在不在盘上。
    if bad:
        import re as _r
        missing = []
        for path in (CRAFT, os.path.join(os.path.dirname(CRAFT), "__editor__.xml")):
            if not os.path.exists(path):
                continue
            try:
                cur = io.open(path, encoding="utf-8-sig").read()
            except OSError:
                continue
            lack = [n for n, _ in PANEL if ('variable="%s"' % n) not in cur]
            chan = ["%s#%d" % (pt, ix) for pt, ix, _b, val in IC_CHANNELS
                    if _r.search(r'partType="%s[^"]*"' % pt, cur) and esc(val) not in cur]
            if lack or chan:
                missing.append("%s：缺面板 %s / 通道 %s" % (
                    os.path.basename(path), (",".join(lack[:6]) + ("…" if len(lack) > 6 else "")) or "无",
                    ",".join(chan) or "无"))
        # 只缺"本次要新加的那些名字"=盘上是上一版（正常迭代），不是被刷回旧版 ⇒ 降成提示
        fresh = set(n for n, _ in PANEL)
        only_new = True
        for msg in missing:
            pass
        lack_all = set()
        for path in (CRAFT, os.path.join(os.path.dirname(CRAFT), "__editor__.xml")):
            if os.path.exists(path):
                cur = io.open(path, encoding="utf-8-sig").read()
                lack_all |= set(n for n, _ in PANEL if ('variable="%s"' % n) not in cur)
        if fp.get("setters") and len(lack_all) and lack_all <= fresh and fresh and            (len(PANEL) - len(lack_all)) == fp.get("setters"):
            missing = []
            print("提示：盘上是上一版（%d 条），本次要加 %d 条新面板量（不是被刷回旧版）"
                  % (fp["setters"], len(lack_all)))
        if missing:
            print("⚠ 盘上 FT 层被**刷回旧版**（设计器存盘/手改）：" + "；".join(missing))
            print("⚠ ⇒ 上一架次飞的不是最新律。本次 apply 会重新覆写；要生效就**从机库出击**，"
                  "或至少别再从设计器存盘（一存盘就又慢一版）。")
        else:
            print("指纹：盘上字节变了但**内容等价**（游戏重新序列化过，面板与通道都在）⇒ 同一版律，只是别信字节哈希")
    else:
        print("指纹核对：盘上两份都是上次 apply 的那两份 ✓（setters=%d @ %s）"
              % (fp.get("setters", -1), time.strftime("%m-%d %H:%M", time.localtime(fp.get("t", 0)))))
def main():
    # 盘上这两份还是不是我上次写的那两份？（设计器存盘=整机覆盖外部改动；dry-run 也要报，诊断时靠它）
    _check_disk_fingerprint()
    xml = io.open(CRAFT, encoding="utf-8-sig").read()
    orig = xml
    check_refs(PANEL)
    print("引用闸过：面板 %d 条全部只用内置或先前定义" % len(PANEL))
    for n, e in PANEL:
        lint(e, "panel." + n)
    for tag, e in (("AIL", AIL), ("ELE", ELE), ("RUD", RUD), ("GEAR", GEAR_EXPR), ("BRAKE", BRAKE_EXPR),
                   ("THR", THR_EXPR), ("BRK", BRK_EXPR), ("REV", REV_EXPR)):
        lint(e, tag)
    print("词法闸过：面板 %d 条 + 8 条执行器式均在白名单内" % len(PANEL))
    xml = patch_panel(xml)
    for pid in AIL_PARTS:
        xml = patch_surface(xml, pid, AIL)
    for pid in ELE_PARTS:
        xml = patch_surface(xml, pid, ELE)
    for pid in RUD_PARTS:
        xml = patch_surface(xml, pid, RUD)
    # 构型/能量通道：全部按 (partType, IC 序号) 定位（见 IC_CHANNELS 的源码判决表）
    import re as _re
    _SETTERS = {n for n, _ in PANEL}   # 我们自己定义的 setter 名：盘上 IC 现值是它们 ⇒ 是本工具的上一版，合法
    for _pt, _idx, _bare, _val in IC_CHANNELS:
        _hit = [0]
        def _ic(m, _idx=_idx, _bare=_bare, _val=_val, _hit=_hit):
            blk = m.group(0)
            ics = list(_re.finditer(r'<InputController\.State[^>]*input="([^"]*)"[^>]*/>', blk))
            if _idx >= len(ics):
                raise RuntimeError("%s 的第 %d 个 IC 不存在（只有 %d 个）" % (_pt, _idx, len(ics)))
            ic = ics[_idx]
            old = ic.group(1)
            # 守卫 = "裸轴名（且就是该通道那个）或任何表达式"。为什么要放行**任意**表达式：
            # 本工具迭代过十几版式子，每一版都可能是盘上的旧值；只认"当前这一版"的守卫会在改版时
            # 把自己的上一版当成"外来物"拒改（本轮差点又踩）。而真正要拦的是**序号错位**——
            # 那必然表现为"一个别的裸轴名"（轮件 #0 的 `Yaw`/`-Yaw`），它是不含运算符的纯标识符。
            if _re.match(r"^[A-Za-z_]\w*$", old) and old != _bare and old not in _SETTERS:
                raise RuntimeError("%s 第 %d 个 IC 现值是裸轴名 %r（期望 %r）⇒ 序号错位，拒改"
                                   "（防把能量式写到转向通道）" % (_pt, _idx, old, _bare))
            new_ic = ic.group(0).replace('input="%s"' % old, 'input="%s"' % esc(_val), 1)
            _hit[0] += 1
            return blk[:ic.start()] + new_ic + blk[ic.end():]
        xml = _re.sub(r'<Part\b[^>]*partType="%s[^"]*"[^>]*>.*?</Part>' % _pt, _ic, xml, flags=_re.S)
        assert _hit[0] >= 1, "通道件未找到（partType=%s*）" % _pt
        print("通道 %-18s IC#%d x%d → %s" % (_pt, _idx, _hit[0],
              (_val if len(_val) < 46 else _val[:43] + "...")))
    xml, lmsg = write_readouts(xml)
    if NOMFD:      # 默认保留 MFD；要"这架机不挂 Lua"请改用 addon 的 FT_ONLY 编译开关
        xml, mfd_ids = strip_mfd(xml)
        print("摘掉 MFD 零件：%s（--nomfd 显式要求）"
              % (",".join(mfd_ids) if mfd_ids else "无"))
    import xml.etree.ElementTree as ET
    ET.fromstring(xml)
    print("XML 良构；面板 %d 条；执行器 %d 件；Label %s"
          % (len(PANEL), len(AIL_PARTS) + len(ELE_PARTS), lmsg))
    if "--apply" not in sys.argv:
        print("dry-run（加 --apply 落盘）")
        return
    bk = CRAFT + ".pre-ft-v01.bak"
    if not os.path.exists(bk):
        io.open(bk, "w", encoding="utf-8").write(orig)
        print("backup ->", bk)
    io.open(CRAFT, "w", encoding="utf-8").write(xml)
    print("APPLIED ->", CRAFT)
    # 法典 §30：**设计器试飞读的是 __editor__.xml**（他只改命名机体=用户永远慢一版，
    # app67 踩过；SC-6 app3 我又把这条丢了——他只看到自己写的 TextL/TextR 就是这个原因）。
    # 两份必须同时写：从机库出击读命名机体、从设计器试飞读 __editor__。
    ed = os.path.join(os.path.dirname(CRAFT), "__editor__.xml")
    if os.path.exists(ed):
        io.open(ed, "w", encoding="utf-8").write(xml)
        print("同步 -> __editor__.xml（设计器试飞读这份）")
    # 指纹留档：下次一跑就知道盘上这份是不是我们上次写的那份（设计器存盘会整机覆盖）
    import hashlib, json
    # **必须按文件字节做指纹**（机体带 BOM，`xml.encode()` 的哈希永远不等于盘上那份 ⇒ 假警报）
    _fp = {"named": _sha(CRAFT),
           "editor": _sha(ed) if os.path.exists(ed) else None,
           "setters": len(PANEL), "gear": GEAR_EXPR[:24], "t": time.time()}
    io.open(FINGERPRINT, "w", encoding="utf-8").write(json.dumps(_fp))
    print("指纹留档 ->", os.path.basename(FINGERPRINT), _fp["named"], _fp["editor"])
    for f in ([CRAFT, ed] if os.path.exists(ed) else [CRAFT]):
        c2 = io.open(f, encoding="utf-8-sig").read()
        for n, _ in PANEL:
            assert ('variable="%s"' % n) in c2, "%s 缺面板 %s" % (f, n)
        assert esc(AIL) in c2 and esc(ELE) in c2 and "{round(" in c2, "%s 缺律或读数" % f
    print("两文件（命名机体 + __editor__）回读核对一致 ✓")
    chk = io.open(CRAFT, encoding="utf-8-sig").read()
    for n, _ in PANEL:
        assert ('variable="%s"' % n) in chk, "面板缺 %s" % n
    assert chk.count(esc(AIL).replace("&amp;", "&amp;")) >= 1
    for pid in AIL_PARTS + ELE_PARTS:
        seg = re.search(r'<Part id="%s"[^>]*>.*?</Part>' % pid, chk, re.S).group(0)
        assert esc(AIL) in seg or esc(ELE) in seg, "零件 %s 未替换" % pid
    assert chk.count('partType="Label-1"') >= 1, "Label 丢失"
    assert esc(AIL) in chk and esc(ELE) in chk   # 自校验：拿律本身当指纹，避免字面量过期（app12 连踩三次）
    # 起落架/刹车：拿**式本身**当指纹回读（app67 教训——只在内存里改对不算数，盘上那份才算）
    for _pt, _idx, _bare, _val in IC_CHANNELS:
        _bad = []
        for m in _re.finditer(r'<Part\b[^>]*partType="%s[^"]*"[^>]*>.*?</Part>' % _pt, chk, _re.S):
            ics = list(_re.finditer(r'<InputController\.State[^>]*input="([^"]*)"[^>]*/>', m.group(0)))
            if _idx >= len(ics) or ics[_idx].group(1) != esc(_val):
                _bad.append(m)
        assert not _bad, "盘上 %s 的第 %d 个 IC 不是 %r" % (_pt, _idx, _val)
    assert 'variable="airEver"' in chk, "盘上缺 airEver（减速板的升空锁）"
    for _n2 in ("VAPP", "thrCmd", "spdBrk", "airFly", "revOn", "thrRet", "gearUp", "lgWarn", "gearCmd", "brkCmd"):
        assert 'variable="%s"' % _n2 in chk, "盘上缺能量环 setter %s" % _n2
    print("磁盘回读核对：面板 %d 条 / 执行器 4 件 / 通道 %s / Label %d 只  ✓"
          % (len(PANEL),
             " ".join("%s#%d" % (p, i) for p, i, b, v in IC_CHANNELS),
             chk.count('partType="Label-1"')))


if __name__ == "__main__":
    main()
