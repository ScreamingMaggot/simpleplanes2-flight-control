# Steam Workshop 描述文案（两机体）

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
