#!/usr/bin/env python3
"""把 telemetry-addon.lua 注入游戏 MFD 程序（替换 resources.assets 里的 MfdProgram TextAsset）。

用法:
  python build_patch.py            # 只生成 patched XML，不动游戏文件
  python build_patch.py --apply    # 备份并写回游戏（首次会生成 .orig 备份）

原理（源码级）: MfdProgram.LoadXml 支持 <Script> 无 file 属性时取节点内联文本
(Game.dll Assets.Scripts.Craft.Parts.Modifiers.Mfd/MfdProgram.cs:96-99)。
"""
import io, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GAME_ASSETS = r"D:/Entertainments/steam2/steamapps/common/SimplePlanes 2/SimplePlanes 2_Data/resources.assets"
STOCK_LUA = os.path.join(HERE, "DefaultProgram.lua")
ADDON_LUA = os.path.join(HERE, "telemetry-addon.lua")
UI_REF = "UI/Xml/Mfd/DefaultMfdUI"

def build_xml():
    stock = io.open(STOCK_LUA, encoding="utf-8").read()
    addon = io.open(ADDON_LUA, encoding="utf-8").read()
    script = stock + "\n\n" + addon
    # 语法门禁：MoonSharp 加载失败=整个 MFD 静默瘫痪（v7 教训），离线先 parse
    try:
        from luaparser import ast as _ast
        _ast.parse(script)
        print("lua syntax OK")
    except ImportError:
        print("WARN: luaparser 未安装，跳过语法门禁")
    except Exception as e:
        sys.exit("LUA SYNTAX ERROR, 拒绝 apply: %s" % e)
    # 内联脚本不能含会破坏 XML 的裸 & <；用 CDATA 包裹
    xml = (
        '<MfdProgram id="Default">\n'
        f'   <UI file="{UI_REF}" />\n'
        f'   <Script><![CDATA[{script}]]></Script>\n'
        '   <Pages>\n'
        '      <Page id="page-menu" name="MENU" />\n'
        '      <Page id="page-tgp" name="TGP" />\n'
        '      <Page id="page-act" name="ACT" />\n'
        '      <Page id="page-wpn" name="WPN" />\n'
        '      <Page id="page-flt" name="FLT" />\n'
        '   </Pages>\n'
        '</MfdProgram>'
    )
    out = os.path.join(HERE, "MfdProgram.patched.xml")
    io.open(out, "w", encoding="utf-8").write(xml)
    print("XML written:", out, len(xml), "bytes")
    return xml

def apply_to_game(xml):
    import UnityPy
    backup = GAME_ASSETS + ".orig"
    if not os.path.exists(backup):
        print("Backing up original resources.assets ->", backup, "(one-time, ~1GB)")
        shutil.copy2(GAME_ASSETS, backup)
    target = GAME_ASSETS if os.access(GAME_ASSETS, os.W_OK) else None
    if target is None:
        sys.exit("game file not writable; run me from a terminal with permissions")
    env = UnityPy.load(backup)
    patched = 0
    for obj in env.objects:
        if obj.type.name == "TextAsset" and obj.peek_name() == "MfdProgram":
            t = obj.read_typetree()
            t["m_Script"] = xml
            obj.save_typetree(t)
            patched += 1
    if patched != 1:
        sys.exit(f"expected 1 MfdProgram TextAsset, patched {patched}")
    staging = tempfile.mkdtemp(prefix="sp2patch_")
    env.save(out_path=staging)
    staged = os.path.join(staging, os.path.basename(backup))  # env 保留源文件名(resources.assets.orig)
    shutil.move(staged, target)
    shutil.rmtree(staging, ignore_errors=True)
    print("Patched ->", target)

def verify():
    import UnityPy
    env = UnityPy.load(GAME_ASSETS)
    for obj in env.objects:
        if obj.type.name == "TextAsset":
            d = obj.read()
            if d.m_Name == "MfdProgram":
                s = d.m_Script
                s = s.decode("utf-8", "ignore") if isinstance(s, bytes) else str(s)
                print("in-game MfdProgram:", len(s), "bytes; telemetry present:", "TELHDR" in s)
                return
    print("MfdProgram not found!")

if __name__ == "__main__":
    xml = build_xml()
    if "--apply" in sys.argv:
        apply_to_game(xml)
    elif "--verify" in sys.argv:
        verify()
    else:
        print("dry-run only; use --apply to write into the game (makes one-time backup .orig)")
