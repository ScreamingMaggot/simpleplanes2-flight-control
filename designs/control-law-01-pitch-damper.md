# 控制律 01 · 俯仰阻尼 → 姿态保持 → 定高（Funky Trees 表达式版）

> 2026-09-21 依据 Funky Trees 官方社区文档全面修订（语言=游戏 UI 里明示的 "Funky Trees"，
> 文档站 https://snowflake0s.github.io/funkytrees ，社区维护，对应 Jundroo 两代游戏）。
> 探针步骤作废——变量与函数已实锤，不需要游戏内试错。

## 已确认的语言能力

- **状态变量**（只读）：`PitchAngle`(°，抬头为正)、`PitchRate`(°/s)、`RollAngle/RollRate`、`Heading`、
  `IAS/TAS/GS`、`Altitude/AltitudeAgl`、`AngleOfAttack/AngleOfSlip`、`GForce/VerticalG`、`Fuel`、`Time` …
- **输入变量**：`Pitch/Roll/Yaw/Throttle/Trim/VTOL/Brake/Flaps/Activate1-8`（杆量/轴，非姿态）
- **函数**：`PID(target,current,p,i,d)`（**内置完整 PID，积分器有持久状态**）、`rate(x)`（d/dt）、
  `smooth(x,rate)`（**限速器**，非低通！）、`clamp/clamp01/lerp/inverselerp/lerpangle/deltaangle`、
  `sin/cos/tan/…`、`sum/min/max/abs/sign/pow/exp/log` 、`ammo()`
- **Variable Setter**（自定义全局变量，设计器里"变量"面板添加）：
  `Name = <表达式>`，可选 activator（布尔门控）与 priority（多写入者仲裁，高者优先）；
  表达式**自引用即上一拍值** → 可实现锁存/状态机。每物理拍求值一次。

## E1 · 俯仰阻尼器（先做这个，10 分钟）

升降舵两片零件的 Custom Input Expression 都改为：

```
clamp(Pitch - Kq*PitchRate, -1, 1)
```

- 注意单位：PitchRate 是 **°/s**，配平试飞里杆阶跃大概激起 10~30 °/s →
  **Kq 扫 0.01 / 0.02 / 0.04** 三档（不是之前写的 0.2~1.0，那个量级会直接把舵打死）
- 复飞 C2 拉杆阶跃，每档记：最大过冲角、摆动来回数、收敛时间
- 教学点：q 负反馈 = 特征方程二阶项加阻尼 → ζ↑、超调↓；Kq 过大→杆效迟钝

## E2 · 姿态保持（本项目第一个"自动驾驶仪"）

**第 1 步** 设计器"变量"面板添加两个 Setter：

```
AP_Capture   表达式: Activate1 ? PitchAngle : AP_Capture        （按住 A1 锁定当前姿态，松开保持）
AP_Engaged   表达式: Activate1 ? 1 : (Activate2 ? 0 : AP_Engaged) （A1 接通 / A2 断开）
```

**第 2 步** 升降舵表达式：

```
clamp(AP_Engaged ? PID(AP_Capture, PitchAngle, Kp, Ki, Kd) : Pitch + Trim, -1, 1)
```

- 起步增益：`Kp=0.05, Ki=0.005, Kd=0.5`（输出是 ±1 杆量，误差是度；30° 偏差 → 1.5·Kp 已饱和，合理）
- 试验：配平 → 按 A1 → **全程松手**，对比手动时代的 C1（20°/5s 下坠应被压制为小幅回中）
- 变量自检：把 `AP_Capture` 或 `PID(...)` 临时接到一个 Gauge 零件上读数（零件库有 `Gauge.State`），
  或在表达式里加 `*0` 接到副翼看舵面是否乱动

## E3 · 定高（把 PID 换到高度回路）

升降舵改：`clamp(AP_Engaged ? PID(AP_Alt, AltitudeAgl, p, i, d) : Pitch + Trim, -1, 1)`，
`AP_Alt = Activate1 ? AltitudeAgl : AP_Alt`。
- 文档官方例：`PID(10, AltitudeAgl, 1, 0.5, 2)`（悬停定高 10 m）可作增益参照
- 体会两个事实：① 高度是姿态的积分 → Ki 稍大就低频振荡（回路耦合的实感）；
  ② 正确做法是 E2 姿态环 + 外环高度环级联（串级 PID）——这正是下一课的入口

## 积分饱和实验（自控实验班的保留节目，5 分钟）

E3 里把目标高度猛改 +100 m 并保持油门 50%：观察 `AltitudeAgl` 追不上时超调加剧（windup）。
对策自己试：给 PID 输出套 `clamp` 已经做了 → 不够；用 activator 在误差 >30 m 时切 Ki=0：
`PID(AP_Alt, AltitudeAgl, 1, (abs(AP_Alt-AltitudeAgl)<30 ? 0.5 : 0), 2)` —— 条件积分，抗饱和。

## 与官方 Gyroscope 的对照（保留）

同一 E2 律 vs 装 Gyroscope(autoOrient) vs 纯手动，三行对比表：过冲/收敛时间/稳态误差。

## 风险与备注

- 社区文档以 SP1 为主、SP2 页面在逐步补——个别变量在 SP2 可能改名或缺失；
  若编辑器报编译错误，先按文档站在游戏 UI 的变量列表里找同名项，再回来报告
- Setter 自引用是否保留上一拍值未在文档例句中明说（示例只有 `function="1"` 常数型），
  E2 若行为异常（AP_Capture 每拍跟着姿态跑），告诉我现象，改用 activator+priority 的
  双 Setter 仲裁写法（文档 Priority Ranking 例已证明该机制存在）
- 变量每物理拍更新 → 采样滞后在低增益下可忽略，别把 Kd 推到舵面"哒哒哒"为止
