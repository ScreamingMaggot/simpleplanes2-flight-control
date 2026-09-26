#!/usr/bin/env python3
"""Dump full part-type + InputController inventory from analysis/decomp/PartTypes.xml.

Outputs:
  analysis/data/parts_inventory.csv   - one row per (PartType, modifier, attr-of-interest)
  analysis/data/parts_ic_channels.csv - one row per InputController channel
  analysis/data/modifier_classes.txt  - unique modifier class names (decompile targets)
"""
import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # project root
SRC = ROOT / "analysis" / "decomp" / "PartTypes.xml"
OUT = ROOT / "analysis" / "data"

tree = ET.parse(SRC)
types = tree.getroot()

inventory = []
ic_rows = []
classes = {}

for pt in types.findall("PartType"):
    pid = pt.get("id")
    pname = pt.get("name")
    mass = pt.get("mass")
    mods = pt.find("Modifiers")
    if mods is None:
        continue
    for idx, mod in enumerate(mods):
        cls = mod.tag
        classes[cls] = classes.get(cls, 0) + 1
        for k, v in sorted(mod.attrib.items()):
            inventory.append([pid, pname, mass, idx, cls, k, v])
        if cls == "InputController":
            ic_rows.append([pid, pname, idx, mod.get("name", ""),
                            mod.get("propertyEditorDesc", ""),
                            mod.get("defaultInput", ""),
                            mod.get("defaultMin", ""), mod.get("defaultMax", ""),
                            mod.get("defaultActivationGroup", ""),
                            mod.get("zeroOnDeactivate", "")])

def dump(rows, path, header):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"{path.name}: {len(rows)} rows")

dump(inventory, OUT / "parts_inventory.csv",
     ["partType", "partName", "mass", "modIndex", "modifier", "attr", "value"])
dump(ic_rows, OUT / "parts_ic_channels.csv",
     ["partType", "partName", "modIndexInPart", "icName", "desc",
      "defaultInput", "defaultMin", "defaultMax", "actGroup", "zeroOnDeactivate"])

with open(OUT / "modifier_classes.txt", "w", encoding="utf-8") as f:
    for c in sorted(classes):
        f.write(f"{c}\t{classes[c]}\n")
print(f"unique modifiers: {len(classes)}")

# summary of IC channel count
print(f"IC channels: {len(ic_rows)} across {len(set(r[0] for r in ic_rows))} part types")
inputs = {}
for r in ic_rows:
    inputs[r[5]] = inputs.get(r[5], 0) + 1
print("defaultInput usage:", dict(sorted(inputs.items(), key=lambda x: -x[1])))
