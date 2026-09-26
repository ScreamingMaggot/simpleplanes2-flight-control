#!/usr/bin/env python3
"""Extract per-modifier input-consumption & output-production facts from Game.decompiled.cs.

For every PartType in PartTypes.xml:
  - locate its Data and Script class blocks in the decompiled source
  - flag: how InputController.Value is read, clamps/mapping applied, VariableOutput
    properties (with getter bodies), rate limiters (MoveTowards/SmoothDamp/Lerp)
Outputs JSON: analysis/data/parts_io_facts.json
"""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_XML = ROOT / "analysis" / "decomp" / "PartTypes.xml"
CS = (ROOT / "tools" / "ilspycmd" / "full" / "Game.decompiled.cs").read_text(encoding="utf-8")
OUT = ROOT / "analysis" / "data" / "parts_io_facts.json"

# Manual mapping for tags whose Script class doesn't follow <Tag>Script
SCRIPT_ALIAS = {
    "Engine": ["EngineScript", "BladedEngineScript", "PropEngineScript", "JetEngineScript",
               "JetEngineAfterburningScript", "JEngineScript", "PowertrainModifierScript"],
    "Switch": ["CockpitSwitchScript"],
    "Button": ["CockpitButtonScript"],
    "AttitudeBall": ["AttitudeBallBehaviour"],
    "Wing": ["WingScript"],
    "LandingGear": ["LandingGearScript"],
    "GearLeg": ["GearLegScript"],
    "ResizableWheel": ["ResizableWheelScript"],
    "Wheel": ["BaseWheelScript", "WheelScript"],
}

# tags whose Data class doesn't follow <Tag>Data
DATA_ALIAS = {
    "Switch": "CockpitSwitchData",
    "Button": "CockpitButtonData",
}
# tags with no runtime Script class (pure physics/design data)
DATA_ONLY = {"FloatingPart"}

lines = CS.split("\n")

def find_class_block(name):
    """Find top-level (tab-indented) class block. Returns (start,end,code) or None."""
    pat = re.compile(rf"^\t(?:public|internal|private|protected)?\s*(?:abstract |sealed |static |partial )*class {re.escape(name)}\b")
    for i, ln in enumerate(lines):
        if pat.match(ln):
            # find closing '\t}'
            for j in range(i + 1, len(lines)):
                if lines[j] == "\t}":
                    return i, j, "\n".join(lines[i:j + 1])
            return None
    return None

FEATURE_PATTERNS = {
    "ic_by_name": r'GetInputController\(\s*"([^"]+)"\s*\)',
    "ic_first": r'GetModifiers<InputControllerScript>\(\)',
    "ic_component": r'GetComponent<InputControllerScript>',
    "value_use": r'([A-Za-z_][\w.]*)\.(Value|value)\b',
    "clamp01": r'Clamp01\(([^;]{0,120})',
    "clamp": r'Mathf\.Clamp\(([^;]{0,160})',
    "clamp_signed": r'ClampSigned\(([^;]{0,120})',
    "movetowards": r'MoveTowards\(([^;]{0,160})',
    "smoothdamp": r'SmoothDamp\(([^;]{0,160})',
    "disabled": r'\.Disabled\s*=',
}

def scan_block(code):
    feats = {}
    for key, pat in FEATURE_PATTERNS.items():
        ms = re.findall(pat, code)
        if ms:
            feats[key] = list(dict.fromkeys([m if isinstance(m, str) else "|".join(m) for m in ms]))[:12]
    # VariableOutput attributes with the property following
    vo = []
    for m in re.finditer(r'\[VariableOutput\("([^"]+)"(?:,\s*"([^"]+)",\s*(\d+))?\)\]\s*\n\s*public float (\w+)[^\n]*\n\s*\{([^}]*)\}', code):
        vo.append({"display": m.group(1), "defaultVar": m.group(2), "priority": m.group(3),
                   "prop": m.group(4), "getter": m.group(5).strip()})
    if vo:
        feats["variable_outputs"] = vo
    # which input names are compared (Name == "throttle" style dispatch)
    names = re.findall(r'Name\s*==\s*"([^"]+)"', code)
    if names:
        feats["ic_name_dispatch"] = sorted(set(names))
    return feats

tree = ET.fromstring(SRC_XML.read_text(encoding="utf-8-sig"))
block_cache = {}

def get_feats(class_name):
    if class_name in block_cache:
        return block_cache[class_name]
    blk = find_class_block(class_name)
    res = scan_block(blk[2]) if blk else {"missing_class": True}
    block_cache[class_name] = res
    return res

result = []
for pt in tree.findall("PartType"):
    pid = pt.get("id")
    mods = pt.find("Modifiers")
    if mods is None:
        continue
    has_ic = any(m.tag == "InputController" for m in mods)
    entry = {"partType": pid, "name": pt.get("name"), "hasIC": has_ic, "modifiers": []}
    for mod in mods:
        tag = mod.tag
        if tag == "InputController":
            entry["modifiers"].append({"tag": tag, "attrs": dict(mod.attrib)})
            continue
        data_cls = DATA_ALIAS.get(tag, tag + "Data")
        script_clss = [] if tag in DATA_ONLY else SCRIPT_ALIAS.get(tag, [tag + "Script"])
        m = {"tag": tag, "attrs": dict(mod.attrib)}
        m["data"] = get_feats(data_cls)
        m["scripts"] = {c: get_feats(c) for c in script_clss}
        entry["modifiers"].append(m)
    result.append(entry)

OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")

# console summary
n_ic = sum(1 for e in result if e["hasIC"])
missing = set()
for e in result:
    for m in e["modifiers"]:
        for k, v in list(m.get("data", {}).items()) + [(kk, vv) for s in m.get("scripts", {}).values() for kk, vv in s.items()]:
            if v == {"missing_class": True} or k == "missing_class":
                missing.add(m["tag"])
print(f"parts: {len(result)}, with IC: {n_ic}")
print("tags whose Data/Script class not found:", sorted(missing))
print(f"wrote {OUT}")
