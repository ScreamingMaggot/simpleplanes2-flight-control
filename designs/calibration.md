# SP2 符号标定单（做完这四格，控制律设计不再猜）

> **状态更新（2026-09-21 深夜）**：符号已由反编译源码互证结案（见 analysis/platform-facts.md §十）：
> Pitch 轴正=推杆、PitchAngle 正=抬头、PitchRate 正=低头、高度环负增益=爬升。
> T-A/T-B 降级为可选复核；**新增必做复测**：E2 姿态律改正增益
> `PID(0, PitchAngle, -0.05, -0.002, -0.05)`（原版正增益按源码是正反馈，"手感好"疑为掩盖），
> 与原版 A/B 各飞一次短阶跃对比收敛性。官方 AI 定高律（platform-facts §十一）可作为
> Lua 移植版的参照实现——条件积分+100m 前瞻，出厂调参。

规则：每格只做一次粘贴、一次观察、记一个符号。全部在设计器测试模式或 300 m 以上平飞做，
每格之间升降舵恢复手动基线：`clamp(Trim + Pitch - 0.06*PitchRate, -1, 1)`。

## C1 · 执行器符号（正输出 = 抬头还是低头？）

升降舵（两片）粘贴：
```
Activate3 ? 0.3 : clamp(Trim + Pitch - 0.06*PitchRate, -1, 1)
```
按 A3，观察升降舵/机头：

- 机头上仰 → **σ_elev = +1**（正输出=抬头）
- 机头下俯 → **σ_elev = -1**

记录 σ_elev = ____

## C2 · 姿态变量符号（+5° 指令会把飞机带向哪？）

Setter：
```
AP_Qcmd  表达式: 5    activator: 3
AP_Out   表达式: PID(AP_Qcmd, PitchAngle, 0.05, 0, 0.05)    activator: 3
```
升降舵：
```
Activate3 ? clamp(Trim + AP_Out, -1, 1) : clamp(Trim + Pitch - 0.06*PitchRate, -1, 1)
```
按 A3 稳定后观察机头停在：

- 抬头姿态 → **σ_theta = +1**（PitchAngle 抬头为正，内环可信）
- 低头姿态 → **σ_theta = -1**（内环对非零目标方向反——E2 只测过零点，今天补上）
- 绕零振不停/乱翻 → 内环本身不稳，拍照记录，停做 C3

记录 σ_theta = ____

## C3 · 高度变量单调性（爬升时 AltitudeAgl 变大还是变小？）

Setter（纯 P 无 PID，用上两格结论定符号——先按"正常约定"写，行为反了才说明变量有鬼）：
```
AP_Qcmd  表达式: clamp((500 - AltitudeAgl) * σ_theta * 0.05, -8, 8)    activator: 3
```
（σ_theta 代入 +1 或 -1；AP_Out 和升降舵沿用 C2）

按 A3，从 400 m 和从 600 m 各试一次：

- 两次都朝 500 收敛 → **σ_alt = +1**，定高律成立，收工
- 两次都背离 500 → **σ_alt = -1**（AltitudeAgl 反向），把 C3 表达式里 `(500 - AltitudeAgl)` 改 `(AltitudeAgl - 500)` 复验一次收敛
- 收敛但越摆越大/翻筋斗 → 增益问题：0.05 改 0.02，再记现象

记录 σ_alt = ____，收敛质量：____________

## C4 · （可选）物理拍频率

Setter：`AP_Qcmd  表达式: Time`，升降舵 `Activate3 ? clamp(AP_Qcmd*0.05,-1,1) : 手动基线`。
按 A3 秒表计时到舵面从 0 扫满 ±1，T=____s → 拍频/时基信息，用于 I、D 增益折算。

## 产出

三格符号 (σ_elev, σ_theta, σ_alt) + 一次收敛观察。交回来，最终定高律一行写死：

```
AP_Qcmd = clamp((500 - σ_alt*AltitudeAgl) * K * σ_theta, -8, 8)
```

K 由 C3 的收敛速度定（不猜）。此后航向/滚转/空速回路全部引用这张法典，不再出现"为什么又反了"。

## 做完后恢复

升降舵恢复 E1/E2 双模态（已知良好）：
```
Activate1 ? clamp(Trim + PID(0, PitchAngle, 0.05, 0.002, 0.05), -1, 1) : clamp(Trim + Pitch - 0.06*PitchRate, -1, 1)
```
