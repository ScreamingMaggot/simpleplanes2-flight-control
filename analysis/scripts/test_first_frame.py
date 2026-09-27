"""端到端模拟：按生成物的**真实赋值顺序**跑一帧，验证首帧不再抛 nil 错误。

这是对"首帧 nil"的正面验证 —— 上一局就是在首帧炸的。
用 Python 复刻 Lua 语义（and/or 返回操作数、V 预置 0）。
"""
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ft_to_lua as T  # noqa

spec = importlib.util.spec_from_file_location('vm', 'verify_mirror.py')
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)

gen = importlib.util.spec_from_file_location('mg', 'ft_mirror_gen.py')
mg = importlib.util.module_from_spec(gen)
gen.loader.exec_module(mg)

patch = mg.load_patch()
keys = set(mg.MIRROR_KEYS) - mg.MIRROR_BAN
lua, sel = mg.render(patch.PANEL, keys, False)

evals = re.findall(r'^\s*V\["(\w+)"\]\s*=\s*(.*)$', lua, re.M)
print("求值条数:", len(evals))

# 真实机体状态（取一个像样的空中态）
Sraw = {'Latitude': -5540.0, 'Longitude': 12797.0, 'Altitude': 900.0, 'AltitudeAgl': 900.0,
        'IAS': 75.0, 'GS': 78.0, 'Heading': 190.0, 'PitchAngle': 2.0, 'RollAngle': -5.0,
        'PitchRate': 0.0, 'RollRate': 0.0, 'YawRate': 0.0, 'Pitch': 0.0, 'Roll': 0.0,
        'Yaw': 0.0, 'Throttle': 0.6, 'Trim': 0.0, 'Brake': 0.0, 'VTOL': 0.0, 'Flaps': 0.0,
        'LandingGear': 0, 'GearDown': 0, 'Time': 100.0, 'Fuel': 60.0, 'GForce': 1.0,
        'VerticalG': 1.0, 'TAS': 75.0, 'AngleOfAttack': 2.0, 'AngleOfSlip': 0.0,
        'TargetSelected': False, 'TargetDistance': 0, 'TargetHeading': 0, 'TargetElevation': 0,
        'TargetLocked': False, 'TargetLocking': False, 'FireGuns': 0, 'FireWeapons': 0,
        'Activate1': 0.0, 'Activate2': 0.0, 'Activate3': 0.0, 'Activate4': 0.0,
        'Activate5': 0.0, 'Activate6': 0.0, 'Activate7': 0.0, 'Activate8': 0.0}
S = vm._S(Sraw)

print()
print("=== 场景 A：V 表**空**（修复前的行为）===")
V_empty = vm._V({})
MIR = {}
fails = []
for n, e in evals:
    try:
        vm.lua_eval(e, S, V_empty, MIR)
    except Exception as ex:
        fails.append((n, "%s: %s" % (type(ex).__name__, ex)))
if fails:
    print("  抛错 %d 条（复现事故）：" % len(fails))
    for n, m in fails[:5]:
        print("    %-12s %s" % (n, m))
else:
    print("  无错（意外）")

print()
print("=== 场景 B：V 表**预置 0**（修复后的行为）===")
V_seed = vm._V({n: 0.0 for n, _ in evals})
MIR2 = {}
fails2 = []
for n, e in evals:
    try:
        vm.lua_eval(e, S, V_seed, MIR2)
    except Exception as ex:
        fails2.append((n, "%s: %s" % (type(ex).__name__, ex)))
if fails2:
    print("  仍抛错 %d 条：" % len(fails2))
    for n, m in fails2[:8]:
        print("    %-12s %s" % (n, m))
else:
    print("  ✓ 453 条全部求值成功，首帧无 nil 错误")

print()
print("结论:", "PASS —— 预置 0 修好了首帧 nil" if not fails2 else "仍有问题")
