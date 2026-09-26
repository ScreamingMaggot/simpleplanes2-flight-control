# Steam Workshop / 官网 描述文案（三机体）

发布路径：SimplePlanes 2 → 设计器/机库 → 选中机体 → Share → 粘贴对应描述。
截图建议：机体三视图 + 一张 3D 航迹图（analysis/figures/ 里有现成的）。

---

## TESTaircraft "E1"（SC-1 / SC-3 平台）

**Title:** TESTaircraft E1 — Full-Autopilot Research Trainer (auto-land + go-around)

**Description (EN):**

> ⚠ NOTE: the inner control loops (Funky Trees) are embedded in this craft and work immediately. The outer autopilot suite (approach sequencing, energy management, telemetry) is an MFD Lua addon stored game-wide — grab the one-command patcher + script from the GitHub below (MIT), run it once, restart the game. Without it the aircraft flies normally, just not by itself.

A piston research aircraft (602 hp) built for a flight-control experiment series: it lands itself.
Equipped with an on-board autopilot suite (Funky Trees inner loops + MFD Lua outer loops) that performs the whole approach chain autonomously: runway selection from a static airfield database, pattern entry with tangent-circle altitude dissipation, final-course capture, 3.5° glideslope, flare, touchdown inside the first quarter of the runway — and a procedural go-around with racetrack re-join when approach gates are not established.

Controls: MFD button 9 = engage/disengage landing mode, button 10 = autopilot profile, 1/2/3/4 = master switch / altitude bug / target ±100 m. Flaps >0.5 = weapons master (SC-2 platform compatibility).

Built-in: elevator/aileron/rudder FT control laws, trim passthrough (you can out-steer the AP on pitch via trim wheel). The slow-loop Lua (energy management, sequencing, telemetry) is part of the companion project — see GitHub.

Telemetry, iteration ledger and three test reports (PDF):
https://github.com/ScreamingMaggot/simpleplanes2-flight-control

**描述（中文）：**

602 马力活塞研究机，为飞控实验系列而生：它能自己降落。⚠ 说明：舵面内环（FT 表达式）已随机体文件分发，订阅即用；外环自动驾驶套件（进近编排/能量管理/遥测）是 MFD Lua 脚本，存储于游戏全局资源，需从下方 GitHub 拉取仓库后运行一次 `python analysis/mfd-lua/build_patch.py --apply` 并重启游戏。未打补丁的飞机照常可飞，只是不会自主着陆。

---

## TESTfighter（SC-2 平台）

**Title:** TESTfighter — Autonomous BVR-lite Gunfighter (PN guidance demo)

**Description (EN):**

Twin-jet research fighter (TWR 1.79, 21.8 m² wing). Carries an autonomous gun engagement suite: target beacon acquisition beyond 16 km, proportional-navigation guidance (bank-to-target with LOS-rate damping), pitch "pull-through" shooting geometry (target held in the upper reticle sector, trigger squeeze as the nose sweeps through), energy-managed throttle and automatic gun keying inside the firing box.

Measured envelope: IAS peak 321 m/s, sustained roll 100–190°/s, pitch authority 35–55°/s, load factor p95 8.8 g @ 240 m/s.

Guidance laws live in the airframe's FT aileron/elevator expressions; sequencing and telemetry in the companion MFD Lua (GitHub below). First automated kill achieved in-flight; full forensics in report SC-2.

https://github.com/ScreamingMaggot/simpleplanes2-flight-control

**描述（中文）：**

双发喷气研究机（推重比 1.79）。自主机炮空战套件演示：16 km 级信标截获、比例导引（坡度对靶 + 视线角速率阻尼）、"拉杆穿透"射法（目标悬于准星上部扇区，机头扫过瞬间开火）、能量管理油门与射击窗自动开炮。实测：IAS 峰值 321 m/s、持续滚转 100~190°/s、过载 p95 8.8 g。已完成自主击落，全过程取证见报告 SC-2。导引律在机体 FT 表达式内，慢回路见 GitHub（MIT）。

---

## TESTaircraft2（SC-6 · 纯 FT 电传飞控，随机体自带、零脚本）

**Title:** FT Fly-by-Wire Autoland Trainer（FT 电传飞控 · 自动着陆教练机）

**Description (EN):**

Fly-by-wire whose control laws live **entirely inside the craft's Funky-Trees expressions** — ships with the plane, **no addon, no script**. One switch to stabilize & hold altitude, one to fly the approach and land, plus a 2-axis velocity-vector light on the nose.

Features:
- **AG8** — stabilization + altitude hold (hands-off stays level & holds height)
- **AG7** — autoland: approach-corridor capture → 3° glideslope → flare → gear down → touchdown retard → wheel brakes + auto reverse
- Autothrottle has **full** authority when AG7 is armed (lever can't override in flight)
- Nose **velocity-vector light**: horizontal = ground-track crab, vertical = flight-path angle — points where you're actually going
- 8 cockpit readouts: IAS·GS, AGL·vs, target alt, HDG·TRK, cross-track, wind, fuel·actual throttle, gear·modes
- Full pilot override at any time

Controls: **AG8** = FBW stabilization · **AG7** = landing mode · **VTOL dial** = target/cruise altitude. Turn off AG7 to reclaim the throttle lever.

How to land: fly near a field, roughly lined up (≤~15 km), switch **AG7** on — it captures the centerline, flies the 3° slope, drops gear, flares, retards, brakes. You fly to the field first; long-range auto-routing is WIP.

Source (FT flight-computer generator, design docs & this craft — reproducible, MIT):
https://github.com/ScreamingMaggot/simpleplanes2-flight-control

**描述（中文）：**

控制律 100% 写在机体 Funky-Trees 表达式里、随机体自带、**零模组零脚本**。一键增稳定高、一键进近自动着陆，机头还有一盏双轴"速度矢量"灯。
- **AG8** = 电传增稳 + 定高；**AG7** = 降落模式（进近走廊 → 3° 下滑 → 拉平 → 放轮 → 接地收油 → 刹车 + 反推）；按 7 后**油门完全交给自动油门**；全程可手动超控。
- **VTOL 旋钮** = 目标/巡航高度；关 AG7 即交还油门杆。
- 用法：飞到目标机场附近、大致对准跑道（约 15 km 内）→ 开 **AG7** 自动落地。需先飞到进近走廊附近，远处自动规划航线为开发中。
- 飞控生成器 + 设计文档 + 本机体（可复现，MIT）：https://github.com/ScreamingMaggot/simpleplanes2-flight-control
