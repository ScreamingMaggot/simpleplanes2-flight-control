# simpleplanes.com 社区帖（英文正文，可直接粘贴）

发布位置建议：simpleplanes.com 的 Groups/Forums 里 SimplePlanes 2 相关板块，或 Jundroo 官方 Discord（同一文案）。
配图：1) TESTfighter 飞行照；2) SC-3b 3D 航迹图（sortieB 那张含复飞全链）；3) 一张遥测重建图 v15-axial-report.png。

---

**Title:** I treated SimplePlanes 2 as a free flight-test campaign — 300+ sorties, three sealed control-law suites, full autoland with go-around

**Body:**

Hi all — over the past months I used SimplePlanes 2 as a personal "flight test range" for applied control theory (I'm an aviation undergrad). Not build-and-show, but design-identify-validate loops with real telemetry forensics. Three task packages are now sealed:

**SC-1 — Altitude-hold autopilot (pitch channel).** FT inner loop + Lua outer loop, bank-compensated, sealed after PIO and structural-resonance hunts. Fun fact: the "elevator buzz" I chased for weeks turned out to be a sampling limit cycle — the vibration peak sat at frameRate/6 and moved when the framerate did. Lesson: any jitter diagnosis needs ≥50 Hz telemetry.

**SC-2 — Autonomous gun engagement.** A twin-jet testbed (TWR 1.79) with proportional-navigation guidance in the FT aileron/elevator laws, a "pull-through" shooting geometry (hold the target in the upper reticle sector, squeeze as the nose sweeps through), energy-managed throttle and automatic gun keying. First automated kill logged at 7 m closest approach from a 22 km intercept.

**SC-3b — Full autonomous landing.** Runway selection from the game's static airfield table, pattern entry with tangent-circle altitude dissipation, FAF gates, 3.5° glideslope, flare, touchdown inside the first quarter — plus procedural go-around with racetrack re-join. Verified end-to-end on a mountain airfield with a 1,524 m high takeover, three orbit laps, one glide abort and a second approach to a full stop, zero manual input.

Everything is decided by onboard telemetry (multi-stream, per-aircraft cid, geometric target pairing), and every version has a post-mortem ledger — 20 iterations of SC-3b alone, each one convicted by flight data (including one sign error of mine that made the aircraft perfectly track the centerline extension... away from the runway, 19 km of it).

Craft files, control-law source, Python/MATLAB tooling and three formal reports (PDF):
https://github.com/ScreamingMaggot/simpleplanes2-flight-control (MIT)

Happy to answer control-theory or FT-architecture questions. If you try the autoland craft: the FT laws live inside the craft file; the Lua slow loop is applied with the one-command patcher in the repo (game must be restarted after patching).

---

# 中文版（bilibili 动态/233乐园/贴吧用）

**标题：** 把 SimplePlanes 2 当试飞场：三百个架次，三套封版控制律，全自主着陆带复飞

正文口径同上，落点放 GitHub 链接与仓库 MIT 声明；建议配 sortieB 那张"三圈消高→复飞→重入→着陆"的 3D 航迹图，最有说服力。
