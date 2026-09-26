# SimplePlanes 2 飞行控制实验项目 / SimplePlanes 2 Flight-Control Research

> 以游戏 *SimplePlanes 2*（Unity 物理仿真 + 可编写机载控制律）作为自由飞行试验场，完成的一组「建模 → 系统辨识 → 控制律设计 → 实飞验证」闭环实验。所有结论以机载遥测数据裁决，迭代账本与验证报告随仓库发布。
>
> A set of closed-loop experiments — *modelling → system identification → control-law design → flight validation* — carried out inside the game *SimplePlanes 2* (Unity physics + user-writable on-board control laws) as a free-flight testbed. Every conclusion is adjudicated by on-board telemetry; iteration ledgers and validation reports ship with the repository.

---

## 课题总览 / Topics

| 课题 / Topic | 内容 / Content | 状态 / Status | 报告 / Report |
|---|---|---|---|
| **SC-1** | 定高自动驾驶仪（纵向通道：姿态内环 + 高度/速度外环、坡度补偿）/ Altitude autopilot (pitch inner loop + altitude/speed outer loop, bank compensation) | v5.1 封版 / sealed | `analysis/report-sc3.pdf`（前史含 SC-1 / prehistory） |
| **SC-2** | 高性能验证机自主空战导引（截获—跟踪—穿越—机炮杀伤链，比例导引 + 挂点射法）/ Autonomous air-combat guidance (intercept–track–pass–gun kill chain, proportional navigation + deflection shooting) | 主链路验收通过 / main loop accepted | `analysis/report-sc2.pdf` |
| **SC-3 / 3b** | 远距机场自主选配、程序进场与切线消高、全自主着陆（含复飞重入）/ Long-range airport selection, procedural approach, tangent-circle descent, fully autonomous landing (incl. go-around rejoin) | v4.68 收口 / closed | `analysis/report-sc3b.pdf` |
| **SC-5** | FT-Lite：把控制律下沉进机体 Funky-Trees 表达式的早期验证（成果并入法典）/ Early proof of pushing control laws into the craft's Funky-Trees expressions | 已结案 / concluded（机体归档 / craft archived） | `designs/SC-5-ft-autoland.md` |
| **SC-6** | **纯 Funky-Trees 机载飞控**：不依赖任何外部脚本，整套增稳 / 定高 / 自动进近着陆电传律直接内嵌于机体 XML —— **本仓库的核心工程成果** / **Pure Funky-Trees on-board fly-by-wire**: the entire stabilization / altitude-hold / approach-landing law lives inside the craft XML with no external script — **the flagship artifact of this repo** | 进行中 / in progress | `designs/SC-6-autoland.md`、`designs/SC-6-ft-flightcontrol.md` |

---

## 控制架构 / Control architecture

项目存在两代架构：

- **SC-1 … SC-3b（混合式）**：快回路（舵面内环、导引律）运行于机载表达式引擎 **Funky Trees（FT）**，每个物理拍做位置式求值；慢回路（能量管理、模式仲裁、遥测记录）由 MFD 的 **Lua** 脚本以真时间步长实现（`analysis/mfd-lua/telemetry-addon.lua`）。补丁工具 `analysis/mfd-lua/build_patch.py`：Lua 语法门禁 → 注入 `resources.assets`（需冷启动加载）。
- **SC-5 / SC-6（纯 FT 式）**：控制律**全部**以 FT 表达式内嵌于机体 XML，**随机体分发、不依赖任何全局 Lua/MFD**。飞控的唯一真源是生成脚本 `analysis/scripts/ft_ta2_patch.py`，它把面板（一列带依赖顺序的 `Setter` 表达式）与执行器接线写进机体文件。

Two generations of architecture coexist:

- **SC-1 … SC-3b (hybrid)**: the fast loop (control-surface inner loop, guidance) runs in the on-board expression engine **Funky Trees (FT)**, evaluated positionally every physics tick; the slow loop (energy management, mode arbitration, telemetry recording) is a **Lua** MFD script at true-time step (`analysis/mfd-lua/telemetry-addon.lua`). The patcher `analysis/mfd-lua/build_patch.py` runs a Lua syntax gate, then injects into `resources.assets` (requires a cold start).
- **SC-5 / SC-6 (pure FT)**: the control laws live **entirely** as FT expressions embedded in the craft XML — they ship **with the craft**, with **no** external Lua/MFD dependency. The single source of truth for the flight computer is the generator `analysis/scripts/ft_ta2_patch.py`, which writes the panel (an ordered list of `Setter` expressions) and the actuator wiring into the craft file.

### SC-6 运行模式 / SC-6 modes

- **Activate8 = 持存增稳 + 定高** / persistent stabilization + altitude hold;
- **Activate7 = 降落模式**（进近走廊 + 3° 下滑 + 拉平 + 自动放轮 + 滑跑刹车 + 反推）/ landing mode (approach corridor + 3° glideslope + flare + auto gear + rollout braking + thrust reversal);
- 座舱内 8 块 Label 为长航时读数（空速/地速、无线电高/升降率、目标高、航向/航迹、横偏/选场态、风、油量/油门、构型/模式）。/ Eight cockpit labels serve long-duration readouts (IAS/GS, AGL/vs, target altitude, heading/track, cross-track/selection state, wind, fuel/throttle, config/modes).

---

## 复现 FT 飞控 / Reproducing the FT flight computer

```bash
# 唯一真源 = analysis/scripts/ft_ta2_patch.py；跑道静态表 = analysis/data/runway-locations.json
# Single source of truth = ft_ta2_patch.py; static runway table = runway-locations.json
python analysis/scripts/ft_ta2_patch.py            # dry-run：报差异与三道闸门（引用/嵌套三元/词法）
python analysis/scripts/ft_ta2_patch.py --apply    # 写入游戏 Craft 目录下的 TESTaircraft2.xml
```

生成器带三道编译前闸门，对应 Funky-Trees 引擎的已知失败模式：**面板只能引用排在其之前的名字（前向引用会整块静默失能）**、**禁止嵌套三元**、**函数/变量白名单词法校验**。改完须**从机库出击**（而非从设计器存盘）才生效。

The generator enforces three pre-compile gates that mirror known FT engine failure modes: **a panel may only reference names defined earlier (forward references silently disable the whole block)**, **nested ternaries are forbidden**, and a **function/variable lexical whitelist**. After applying, the craft must be dispatched **from the hangar** (not re-saved from the designer) for the new law to take effect.

现成机体已随仓库入库：`crafts/TESTaircraft2.xml`（SC-6，FT 面板内嵌）。/ A ready craft ships in-repo: `crafts/TESTaircraft2.xml` (SC-6, FT panel embedded).

---

## 观测与评估方法 / Observation & evaluation

- 机载多流遥测（TEL 12 Hz / POS / APP / LAND），逐流实例身份列（`cid`）分离同场多机；/ multi-stream on-board telemetry, per-stream instance id (`cid`) to separate multiple aircraft in one session;
- 以几何距离残差唯一配对「本机—所追目标」，防止归因张冠李戴；/ unique self–target pairing via geometric range residual, to prevent mis-attribution;
- 离线 1:1 重建全部制导量（指令—执行—收敛三环分别可裁决）；/ offline 1:1 reconstruction of every guidance quantity (command / execution / convergence adjudicated separately);
- **FT 选择律离线复算器** `analysis/scripts/ft_sel_probe.py`：逐字复刻面板跑道选择闸门，用历史日志验证「选了哪条跑道、为何没选」；/ `ft_sel_probe.py` replays the panel's runway-selection gates verbatim against historical logs to audit *which* runway was picked and *why not*;
- 抖振诊断规程：≥50 Hz 采样（低频采样会把振荡折叠藏身）；极限环判据：振峰锁步跟随帧率。/ buffet diagnosis needs ≥50 Hz sampling (low rates alias the oscillation away); limit-cycle test: spectral peak locked to frame rate.

---

## 仓库结构 / Repository layout

```
crafts/                 课题机体 XML（TESTaircraft 活塞 / TESTfighter 喷气 / TESTaircraft2 纯 FT 飞控；
                        FT 舵面律与参数面板内嵌于机体文件，复现必需）
analysis/
  scripts/              FT 生成器与离线分析/复算/绘图工具
                        ft_ta2_patch.py（SC-6 飞控唯一真源）· ft_autoland_patch.py ·
                        ta2_flight.py · ft_sel_probe.py · parse_telemetry.py · craft_model.py ·
                        plot_track3d.py / make_track_html.py · fighter_id.py / fighter_stats.py · …
  mfd-lua/              机载 Lua 律与补丁工具（telemetry-addon.lua · build_patch.py）
  data/                 跑道静态表 runway-locations.json（必需，随库）；原始遥测日志不随库
  matlab/               闭环频率响应辨识（sp_id*.m）
  figures/ *.pdf/*.tex  报告成品、源文件与图表
designs/                迭代账本与规格（SC-1…SC-6、控制律与标定；modules/ 为可复用 FT 律片段）
publish/                社区帖与工作坊说明
```

---

## 分发与版权 / Distribution & licensing

- 为控制体积与隐私，**原始遥测日志（约 90 MB）与游戏反编译产物（专有代码，仅个人研究）不随仓库分发**；报告中的统计与图表可对自采日志用 `analysis/scripts/` 重跑复现。`make_track_html.py` 生成的 3D 航迹查看器为自包含 HTML（内嵌 plotly.js，离线可用）。
  Raw telemetry logs (~90 MB) and the game's decompiled binaries (proprietary; personal study only) are **excluded** for size and privacy. Report statistics/figures are reproducible by re-running `analysis/scripts/` on your own logs; the 3D track viewer from `make_track_html.py` is self-contained HTML (plotly.js embedded, works offline).
- 游戏与引擎版权归 **Jundroo** 所有；本仓库仅含自研脚本、数据与文档，不含任何游戏二进制。/ Game and engine are © **Jundroo**; this repository contains only self-authored scripts, data, and documentation — no game binaries.
- 自研代码与文档以 **MIT License** 发布。/ Self-authored code and documentation are released under the **MIT License**.
