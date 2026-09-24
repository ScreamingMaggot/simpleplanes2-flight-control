# SC-3 自动降落 — 实况账本【已封版 v4.17，2026-09-23】

封版报告：`analysis/report-sc3.pdf`（四页，xelatex，图=sc3-landing-report.png）。封版记分卡（接地前判读）：TD 56 m/s、pa@接地 +2.0°、sink 2.8 m/s、主轮先触、前轮 ~0.3 s 柔和跟随、零接管。**α≥6 验收线作废**（中间量：航迹收平后 α=θ−γ 自然回落，以结果量为准）。遗留记账不修：能量环 ±4 m/s/7 s 极限环。延伸课题=SC-3b 远距进近（可行性已论证，见 designs/SC-3b-approach-planning.md）。

机体：TESTaircraft（前三点、轴→升降舵系数 v4.14 起 1.0，AP 用 profile 1）。旧五阶段设计已废，现行 **v4 两状态律**（用户钦定："别搞那么多阶段，按 9 立刻进滑降，agl<4 收油门+满刷"）。

## 现行律（telemetry-addon.lua land_nav，v4.14）

按钮 9 切换。跑道坐标无 API——出生即 AGL<5 时 `RWY AUTOCAP` 自标定（lat/lon/hdg/地面高）。

**v4.14 机体侧改刀**：升降舵律 p −0.05→−0.10（轴→舵面 0.5→1.0，两份 XML 同改）——v4.13 实锤"满舵 α 平台 4.5°@56 m/s、pr≈0"是 0.5 系数偏转上限墙，×2 杆量在 ±1 钳位下是空操作；Lua 侧 KAP_P 0.12→0.06 保环路总增益（v21.4 跨侧联动教训）。拉平窗 v4.13 起 45→15 m。

| 通道 | 律 | 备注 |
|---|---|---|
| 起落架 | 模式一进即 `OverrideInput("LandingGear", +1)` | 零件映射 min=1/max=0：轴+1=放下 |
| 横向 | εh = wrapd(hdg_rwy − 0.02°/m·l − ψ)；Roll = clamp(0.010·εh, ±0.45) | l=右偏距，符号已校（v2 初版反号=发散） |
| 下滑 | 下沉率环 path=2.2·(−GS·tan3.5°−lg_vg)+坡度补偿；拉平 flare=1.0·(8°−α_true)+fint·wa+坡度补偿（fint ±6° 抗饱和、进窗才涨）；cmd=(1−wa)·path+wa·flare，**wa 45→15 m 线性**（v4.13） | α_true=−craft.AngleOfAttack（§25）；v4.3 弃幻影标高线 |
| 速度 | 包络分工禁互搏：加油门 <51 或（能量债且<55）；收油门 >58；板 >56 开 64 满（比例+开慢收快）；能量债=下沉超目标 1 m/s | v4.11 拧紧（55~63 三不管带漏能 61 m/s 触地定罪）；LG_SPEED=55 用户裁定 |
| 触地 | v4.26 签名验证：agl<4 或（|agl̇|<1 持续 0.6s+max\|θ̇\|>5 且 agl<7）触发；日志带 sig=[stable,jerk,rwy] 三验（位置包线 \|l\|<90, −300<s<3400），缺项打 TD-SIG MISMATCH（app8 河面接地教训：agl 判据不挑地面）；油门 0 + Brake+1；**Pitch 保持 1.5 s 后 Release+trim −0.2 接力**；IAS<5 或 40 s 交还 | 判据阈值先问传感器地板（agl 底噪 1.6）；即松杆=机头掉前轮拍（v4.1 定罪） |

## 首着陆记录（2026-09-23 凌晨，cid 55556）

TOUCHDOWN→ROLLOUT COMPLETE 全自动：117 m 进入 → 620 m 处接地（触地 55 m/s）→ 刹车 5.6 s 停稳，全场 |l|≤0 m、|εh|≤0.0°。图：`analysis/figures/sc3-landing-report.png`（脚本 `scripts/plot_landing.py`，日志归档 `data/Player.landing-sc3.log`）。

**遗留缺陷（v4.1 已对症）**：下滑段纯跟轨迹，接地瞬间 α=−5.0°、θ=−1.5°——负迎角平拍，前轮先触、弹跳振荡 4 s。α-hold 项把 30 m 内垂环从"跟轨迹"渐变到"跟机头"，目标 α=8°（LG_ALPHA，待实测调 8~10）。

## 待办

- v4.1 验证局：主轮先触 + α@接地 ≥6°；LAND 行新增 aoa 列可直接读数。
- 合格后的自然延伸：连续起落（touch-and-go）、复飞分支（用户点头才做）。
