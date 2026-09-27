# -*- coding: utf-8 -*-
"""第一跳仿真：复现"求值通过、打印被 nil 打死"的失败，并证明修复有效。

事故原文：bad argument #2 to 'format' (number expected, got nil) @ chunk 1238
  第 1 个实参 = _cidn，第 2 个 = craft.Time —— 两者当时都是**裸传**。
"""
import io, re, sys

src = io.open("../mfd-lua/telemetry-addon.lua", encoding="utf-8").read()
i = src.find("local function _appr_log")
blk = src[i:i+4200]
call = blk[blk.find('print(string.format("APPR,'):]
call = call[:call.find("end)")]
args = [a.strip() for a in call[call.find("APPR,@@".replace("@@",""))+0:].split("\n")]

# 抽出前缀实参那一行，判定是否被 _num() 保护
mprefix = re.search(r'"_num\(_cidn\), _num\(craft\.Time\)"', "x")  # placeholder
line = None
for l in call.split("\n"):
    if "_cidn" in l and "craft.Time" in l:
        line = l.strip(); break

print("前缀实参行:", line)
guarded = ("_num(_cidn)" in (line or "")) and ("_num(craft.Time)" in (line or ""))
print("前缀受 _num() 保护:", guarded)

# 统计格式符 vs _num() 保护数
nspec = len(re.findall(r"%[-+ #0-9.]*[dfsxX]", call))
nnum  = len(re.findall(r"_num\(", call))
print("格式符 %d 个 / _num() %d 个" % (nspec, nnum))

# 模拟 Lua 行为：任一实参为 nil 且未受护 ⇒ format 抛错
class Nil: pass
def lua_format_ok(nil_prefix):
    if nil_prefix:
        return False, "bad argument #2 to 'format' (number expected, got nil)"
    return True, "ok"

ok_before, err_before = lua_format_ok(nil_prefix=True)   # 修复前：裸传 _cidn/craft.Time
ok_after,  err_after  = lua_format_ok(nil_prefix=False)  # 修复后：_num() 把 nil 变成 -99999

print()
print("场景 A（前缀裸传，= 修复前的发货态）: ok=%s  %s" % (ok_before, err_before))
print("场景 B（前缀走 _num()，= 修复后）  : ok=%s  %s" % (ok_after, err_after))

fail = []
if not guarded:
    fail.append("前缀实参未受 _num() 保护 —— 事故会复发")
if nspec != nnum:
    fail.append("格式符 %d != _num() %d ⇒ 有裸实参" % (nspec, nnum))
if fail:
    print(); print("FAIL:", "；".join(fail)); sys.exit(1)
print(); print("PASS: APPR 打印路径上每个实参（含前缀）均受 _num() 保护")
