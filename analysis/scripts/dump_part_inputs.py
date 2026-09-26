#!/usr/bin/env python3
"""机体零件输入通道清单（跨机体搬信号前必跑）。

为什么需要它：SC-5 照搬战斗机 TESTfighter 的 `Flaps > 0.5` 当主电，被用户当场驳回
（"这架飞机就没装襟翼"）；本机 TESTaircraft2 的螺旋桨吃的还是 `VTOL` 轴、挂在激活组 8 下——
这类"输入通道长什么样"的事只写式子不看清单，一定踩。

用法: python dump_part_inputs.py [机体.xml]   默认 TESTaircraft2.xml
输出每件零件：partType / id / 各 InputController.State 的**序号**（#0、#1…）、input 值、激活组。
**序号是重点**：ft_ta2_patch.py 的刹车通道按序号定位（轮 #0=Yaw、#1=Brake），改结构前先看这里。
"""
import io, os, re, sys, collections

DEF = os.path.expandvars(
    r"%USERPROFILE%\AppData\LocalLow\Jundroo\SimplePlanes 2\Crafts\TESTaircraft2.xml")
path = sys.argv[1] if len(sys.argv) > 1 else DEF

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

data = io.open(path, encoding="utf-8-sig").read()
print("%s  (%d 字符)" % (os.path.basename(path), len(data)))
print("=" * 96)

groups = collections.Counter()
for m in re.finditer(r'<Part\b([^>]*)>(.*?)</Part>', data, flags=re.S):
    attrs, body = m.group(1), m.group(2)
    pt = re.search(r'partType="([^"]*)"', attrs)
    pid = re.search(r'\bid="(\d+)"', attrs)
    if not pt:
        continue
    ics = re.findall(r'<InputController\.State\b([^>]*)/>', body)
    key = (pt.group(1), len(ics))
    groups[key] += 1
    print("%-26s id=%-4s" % (pt.group(1), pid.group(1) if pid else "?"))
    for i, a in enumerate(ics):
        inp = re.search(r'input="([^"]*)"', a)
        ag = re.search(r'activationGroup="([^"]*)"', a)
        mn = re.search(r'\bmin="([^"]*)"', a)
        mx = re.search(r'\bmax="([^"]*)"', a)
        inv = re.search(r'invert="([^"]*)"', a)
        print("    #%d input=%-58s grp=%s rng=[%s,%s]%s"
              % (i, (inp.group(1) if inp else "?")[:58],
                 ag.group(1) if ag else "?", mn.group(1) if mn else "?",
                 mx.group(1) if mx else "?",
                 " invert" if inv and inv.group(1) == "true" else ""))
print("=" * 96)
for (pt, n), c in sorted(groups.items()):
    print("%-26s IC数=%d  件数=%d" % (pt, n, c))
