# -*- coding: utf-8 -*-
"""一次性机理实验（不碰在用机体）：把原厂 GearLeg-1 三条腿换成 HingeRotator-1，
看"起落架收放=旋转器转角"这条路在纯 FT 里是否真的走得通。

依据（用户机库里的官方/下载机体实读，2026-09-25）：能自动收放轮的机体 **一个 GearLeg-1 都没有**，
腿是"旋转器 + 构件 + 轮子"拼出来的运动链，旋转器 IC 直接吃表达式：
  Competitor.xml   part 146  HingeRotator-1  input="clamp01(LandingGear)"  JointRotator.State range="90" speed="0.25"
  Stormvark.xml    part 122/124/125         input="GearPosition"（= smooth(GearDown?1:0,.25) 面板量）
反编译侧并不冲突：原厂 GearLeg 的收放动画只读 aircraft.Controls.LandingGearDown（轴），
所以"不可达"的范围是 **原厂轮腿件**，不是"自动起落架"这件事本身。

跑法：python ft_ta2_rotgear.py            → 只写副本 Crafts/TESTaircraft2-RT.xml
设计器里看三件事：① 轮子还挂在臂上吗 ② 按 G（起落架键）臂转不转、往哪转 ③ 落地滑跑正常吗
"""
import re
import sys
import os
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(errors="replace")

CRAFT_DIR = r"C:\Users\Administrator\AppData\LocalLow\Jundroo\SimplePlanes 2\Crafts"
SRC = os.path.join(CRAFT_DIR, "TESTaircraft2.xml")
DST = os.path.join(CRAFT_DIR, "TESTaircraft2-RT.xml")
NEW_NAME = "TESTaircraft2-RT"

# 换件时保留 id / position / Connections（附件点索引不用改：轮件挂在原厂腿的 1 号点上，
# 官方旋转器同样只用 0、1 号点），只换 partType + 换 body 里的 State 块。
LEG_IDS = ("22", "25", "32")          # 前轮 / 右主轮 / 左主轮
ROT = ('<InputController.State activationGroup="0" invert="false" min="-1" max="1" '
       'input="clamp01(LandingGear)" />\n'
       '<JointRotator.State range="90" speed="0.3" disableBaseMesh="true">\n'
       '<Variables />\n</JointRotator.State>')


def swap_leg(xml):
    n = [0]

    def _repl(m):
        head, body = m.group(1), m.group(2)
        pid = re.search(r'\bid="(\d+)"', head).group(1)
        if pid not in LEG_IDS:
            return m.group(0)
        head = head.replace('partType="GearLeg-1"', 'partType="HingeRotator-1"', 1)
        # 官方旋转器：不与机身自碰撞（收进轮舱时臂会穿过结构件）
        if 'partCollisionResponse=' in head:
            head = re.sub(r'partCollisionResponse="[^"]*"', 'partCollisionResponse="None"', head)
        else:
            head = head.rstrip("> ") + ' partCollisionResponse="None">'
        if 'disableAircraftCollisions=' not in head:
            head = head.rstrip("> ") + ' disableAircraftCollisions="true">'
        n[0] += 1
        return head + ROT + "</Part>"

    return re.sub(r'(<Part id="(?:%s)"[ \t]*[^>]*>)(.*?)</Part>' % "|".join(LEG_IDS),
                  _repl, xml, flags=re.S), n[0]


def main():
    xml = open(SRC, encoding="utf-8").read()
    out, k = swap_leg(xml)
    assert k == len(LEG_IDS), "只换到 %d 条腿，期望 %d" % (k, len(LEG_IDS))
    # 新机体名（避免与在用机体撞车；hangar 里一眼认得出是实验机）
    out = re.sub(r'(<Aircraft\b[^>]*\bname=")[^"]*(")', r"\g<1>%s\g<2>" % NEW_NAME, out, count=1)
    # 不许再有任何 GearLeg 残留
    assert "partType=\"GearLeg-1\"" not in out, "仍有 GearLeg 残留"
    assert out.count("HingeRotator-1") == len(LEG_IDS), "旋转器数量不对"
    root = ET.fromstring(out)                      # 良构闸
    assert root is not None
    # 连接表必须原样（轮件仍指向同一个 id）
    for pid in LEG_IDS:
        assert re.search(r'<Connection partA="(?:%s)" partB="\d+" attachPointsA="1"' % pid, xml) is None or \
               re.search(r'part[AB]="%s"' % pid, out) is not None, pid
    open(DST, "w", encoding="utf-8", newline="").write(out)
    back = open(DST, encoding="utf-8").read()
    assert back == out, "回读不一致"
    print("OK 已写副本：%s（%d 字节，%d 条腿换成 HingeRotator，IC=clamp01(LandingGear)）"
          % (DST, len(out.encode("utf-8")), k))
    print("在用机体 TESTaircraft2.xml / __editor__.xml 未改动。删除该文件即可撤销本实验。")


if __name__ == "__main__":
    main()
