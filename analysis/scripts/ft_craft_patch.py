#!/usr/bin/env python3
"""v14.2 控制律直接写入 TESTfighter.xml（唯一真源=本脚本）。
用法: python ft_craft_patch.py [--apply]   默认 dry-run 只报差异。
规则: 首次 apply 前自动备份 .pre-ft.bak；替换 Variables 块 + 副翼/升降舵表达式 + 机炮注入开火 State。"""
import os, re, sys, io

CRAFT = os.path.expandvars(r"%USERPROFILE%\AppData\LocalLow\Jundroo\SimplePlanes 2\Crafts\TESTfighter.xml")

# ── Setter 面板（面板顺序=求值顺序，勿调换）──
SETTERS = [
    ("ARM",   "IAS > 80 & Flaps > 0.5"),
    ("TGT",   "ARM & TargetSelected"),
    ("EPS",   "TGT ? (deltaangle(Heading, TargetHeading) < 180 ? deltaangle(Heading, TargetHeading) : deltaangle(Heading, TargetHeading) - 360) : 0"),
    ("TRV",   "TGT & abs(EPS) < 4"),
    ("LOS_R", "clamp(rate(EPS) + clamp(rate(Heading), -30, 30), -25, 25)"),
    ("VPS",   "TGT ? (TargetElevation + AngleOfAttack - PitchAngle) : 0"),
    ("THD",   "TGT ? max(TargetElevation + AngleOfAttack - (TRV ? 0 : 1), AltitudeAgl < 400 ? 5 : -90) : PitchAngle"),
    ("BANK",  "TGT ? clamp(6 * EPS + 4 * LOS_R, AltitudeAgl < 400 ? -30 : -85, AltitudeAgl < 400 ? 30 : 85) : 0"),
]
# ── 舵面/武器律 ──
AIL = "clamp(Roll + (TGT ? clamp(0.10*(RollAngle + BANK) + 0.004*RollRate, -1, 1) : 0), -1, 1)"
ELE = "clamp(Trim + PID(THD - 10 * Pitch, PitchAngle, -0.35, 0, -0.008), -1, 1)"
FIRE = "FireGuns | (TRV & TargetDistance < 2000 & abs(VPS) < 0.5)"

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def main():
    apply = "--apply" in sys.argv
    xml = io.open(CRAFT, encoding="utf-8").read()
    orig = xml

    # 1) Variables 块整体重建
    block = "  <Variables>\n" + "".join(
        '    <Setter variable="%s" function="%s" priority="0" />\n' % (n, esc(f))
        for n, f in SETTERS) + "  </Variables>"
    xml, n = re.subn(r"  <Variables>.*?</Variables>", lambda m: block, xml, flags=re.S)
    assert n == 1, "Variables 块替换次数=%d" % n

    # 2) 副翼（input 含 clamp(Roll + …）
    xml, n = re.subn(r'input="clamp\(Roll \+ [^"]*"', 'input="%s"' % esc(AIL), xml)
    assert n >= 1, "未找到副翼表达式"
    n_ail = n
    # 3) 升降舵（input 含 clamp(Trim + PID( …）
    xml, n = re.subn(r'input="clamp\(Trim \+ PID\([^"]*"', 'input="%s"' % esc(ELE), xml)
    assert n >= 1, "未找到升降舵表达式"
    n_ele = n
    # 4) 机炮开火 State：在每个 <Gun.State …/> 后插入（幂等：已插则跳过）
    # 4) 机炮开火 State：先删历史插入行（防重复），再在每个 <Gun.State …/> 后插入
    xml = re.sub(r"[ \t]*<InputController\.State [^>]*input=\"FireGuns \| \([^>]*\" ?/>\n", "", xml)
    xml = re.sub(r"[ \t]*<InputController\.State [^>]*input=\"TRV &amp;[^>]*\" ?/>\n", "", xml)
    gun_line = ('<InputController.State activationGroup="0" invert="false" min="0" max="1" '
                'input="%s" zeroOnDeactivate="false" />') % esc(FIRE)
    xml, n = re.subn(r"([ \t]*)(<Gun\.State [^>]*/>)", r"\1\2\n\1" + gun_line.replace("\\", "\\\\"), xml)
    n_gun = n

    assert 'clamp(' in xml and '</Aircraft>' in xml
    import xml.etree.ElementTree as ET
    ET.fromstring(io.StringIO(xml).read() if False else xml)  # 良构校验，失败即抛

    print("setters=%d aileron=%d elevator=%d gun_insert=%d len %d->%d" %
          (len(SETTERS), n_ail, n_ele, n_gun, len(orig), len(xml)))
    if apply:
        bak = CRAFT + ".pre-ft.bak"
        if not os.path.exists(bak):
            io.open(bak, "w", encoding="utf-8").write(orig)
            print("backup ->", bak)
        io.open(CRAFT, "w", encoding="utf-8").write(xml)
        print("APPLIED ->", CRAFT)
    else:
        print("dry-run only; use --apply")

if __name__ == "__main__":
    main()
