# TESTfighter 飞控律实况（v21.2）— 与 ft_craft_patch.py 严格同步

唯一真源 = `analysis/scripts/ft_craft_patch.py`（`--apply` 直写机体 XML；Lua 走 `build_patch.py`，改后须重启游戏进程）。

## Setter 面板（8 个，顺序=求值顺序）

```
ARM   = IAS > 80 & Flaps > 0.5
TGT   = ARM & TargetSelected
EPS   = TGT ? (deltaangle(Heading, TargetHeading) < 180 ? deltaangle(Heading, TargetHeading) : deltaangle(Heading, TargetHeading) - 360) : 0
TRV   = TGT & abs(EPS) < 4                                   ← 捕获门：无距离项（用户钦定）
LOS_R = clamp(rate(EPS) + clamp(rate(Heading), -30, 30), -25, 25)
VPS   = TGT ? (TargetElevation + AngleOfAttack - PitchAngle) : 0
THD   = TGT ? max(TargetElevation + AngleOfAttack - (TRV ? 0 : 1), AltitudeAgl < 400 ? 5 : -90) : PitchAngle
BANK  = TGT ? clamp(6*EPS + 4*LOS_R, agl<400 ? ±30 : ±85) : 0  ← 全距离全角度小角度索敌（用户钦定 v21）
```

**纪律条款**：BANK 结构以用户指令为准。v22 曾擅改 λ̇-PN atan 版（远距侧向目标 λ̇≈0 → 坡度≈0，恰是"前半截慢"元凶），被驳回回滚——导引结构不自行发挥，只按指令实现+修执行层。

## 舵面/武器律

```
副翼   clamp(Roll + (TGT ? clamp(0.10*(RollAngle + BANK) + 0.004*RollRate, -1, 1) : 0), -1, 1)   ← 内环 v21.1：阻尼 0.014→0.004（旧值在压坡时吃掉 2 杆量，指令 85° 执行 25° 的元凶）
升降舵 clamp(Trim + PID(THD - 10 * Pitch, PitchAngle, -0.35, 0, -0.008), -1, 1)
机炮   FireGuns | (TRV & TargetDistance < 2000 & abs(VPS) < 0.5)
油门   (Lua v16.4) 武装=恒满油；IAS>250 收到 0.5 尖峰、跌回立即推满——旧版 150~240 死区致 thr 卡 0.5，中段闭率被砍半（PN 局数据实锤），须重启进程生效
```

## 通道账本

| 通道 | 律 | 验证状态 |
|---|---|---|
| 滚转 | 6ε+4λ̇ 全距硬追；内环 0.10/0.004 | ε>15° 即满坡 85°；上局 ra 只到 25~40°=内环阻尼案，已修待复飞 |
| 俯仰 | θ_cmd=ELEV+AoA−挂点(1/TRV:0)；agl<400 钳 5° | ✅ 零 CFIT、无振荡（v19 局 580s） |
| 油门 | 恒满油+超速尖峰 | ⏳ v16.4 待重启验收 |
| 开火 | TRV & D<2km & \|VPS\|<0.5 ∪ 手动 | ⚠️ 无提前量（唯一记账缺口） |

## 试飞规程

机体律重出击即生效；Lua 改动须重启游戏；敌机带 MFD 全程存活；`DebugExpression "EPS"` 实时读数；读日志先切局（时钟跨局重置，同 cid 会混流）。

## 历史一行版

v11 PN 首通 → v12 pull-through → v13 扇形挂点 → v14 重构+TRV → v15 观测流 → v16 atan2 悬崖/能量双案 → v17 碰撞几何(22km→7m 首拦截) → v19 俯仰重写 → v20 ε 钳值案 → v21 全距小角度索敌(钦定) + 内环阻尼案 → v21.2 油门陷阱案+PN 越权回滚（现行）。
