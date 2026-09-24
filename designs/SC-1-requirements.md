# SC-1 飞控试验机的设计需求单

目的：得到一架**纵向（俯仰）开环稳定、响应慢、易配平**的教练型测试机，
让第一个 Lua PID 实验（定高保持）的曲线干净、好归因。
刻意牺牲性能换可控性——它不需要飞得快，需要飞得"教科书"。

## 一、总体构型（强制）

| 项目 | 要求 | 控制理论理由 |
|---|---|---|
| 布局 | 常规布局：单发螺旋桨（拉进式）+ 下单翼/中单翼 + 尾翼在机身最后端 | 静稳裕度天然为正；避免鸭式布局的静不稳定 |
| 机翼 | **矩形直翼，零后掠**，上反角 2~3°（小量） | 无展向攻角变化，滚转-偏航耦合弱，单输入单输出近似成立 |
| 翼型 | 主翼用 Symmetric 或 Semi-Symmetric，安装角设 0° | 配平点可解析计算，俯仰力矩不随速度剧烈变化 |
| 平尾 | 全翼展后缘为升降舵，安装在机身尾部尽量靠后 | 尾容量 V̄ 取大（≈0.8~1.0），短周期阻尼充足 |
| 垂尾 | 带方向舵，面积 ≈ 主翼的 1/5 | 保证航向稳定，滚转实验中不出现荷兰式干扰观察 |
| 禁止 | 鸭翼、翼刀、翼梢小翼、襟翼、V 尾、双发 | 一切非线性/耦合源都不要 |

## 二、尺寸与重量（参考量级）

- 翼展 ≈ 6 m，主翼面积 ≈ 6 m²（MAC ≈ 1.1 m）
- 机身长 ≈ 8~9 m，平尾面积 ≈ 主翼/3.5
- 空重 300~500 kg：**不装武器、装甲、货舱**，能少装就少装
- 重心：让指示器显示重心在主翼前缘后约 **25~30% MAC**（把发动机、座舱、电池都往前压，电池别放尾部）。装不上就挪零件，**重心位置是本需求单里最硬的指标**
- 起落架：前三点式，只为起飞落地，收放机构不要

## 三、动力

- 单个活塞类发动机（零件表里有 `Engine-Prop-5` / `JPropEngine*` + `PropellerAssembly-1`，按游戏内可选的来）
- 功率取"能 5 m/s 爬升率"即可，**不要推力过剩**：油门要能作为精细配平量，而不是一开就窜

## 四、控制链与航电（2026-09-20 逆向 XML 后修正）

实际信号链（从出厂/玩家机 XML 实证的架构，与"飞行计算机"零件无关）：

```
杆量/油门等标准轴、Lua 或表达式  →  InputController 命名通道（虚拟轴）
                                 →  舵面 ControlSurface.inputId 表达式  →  偏转
```

- `FlightComputer-1`：查实就是座舱类零件（`Cockpit.State primaryCockpit="True"`），只做零件附着根，**不是控制器**，当普通主座舱用；
- `Gyroscope-1`：真货，内置增稳系统（SAS），参数 `stability / speed / yawPower / pitchRange / rollRange / autoOrient`，是 attitude 通道的限幅-回中器，参数本身可写表达式 → 对照组实验素材；
- **InputController**（本项目的正主）：每机可挂多个，每个有 `input="<表达式>"`、`min/max/invert/activationGroup/zeroOnDeactivate`，可自定义输出通道名（玩家机里如 `VTOL`）。已实证表达式可用变量：`IAS、AltitudeAgl、AngleOfSlip、YawRate、RotorRPM、Pitch、Roll、Yaw、Throttle、Brake、Trim、Activate1~8`；函数：`rate()（微分）、smooth()、clamp()、clamp01()、lerp()、abs()、min/max`、三元运算符。游戏类名表里还有 `LuaScript / InputControllerScript / ProcessorScript`，即存在"脚本版输入控制器"；
- 游戏自带 `PIDController`（油门调速器）、`Autopilot`、`_wingLeveler`（自动展平）——官方辅助与玩家控制走同一条链，可开关做 A/B 对比。

SC-1 装机要求：

- `FlightComputer-1` 或任意 `Cockpit-*` 做主座舱 × 1（附着根）
- 1 台 InputController 先不用表达式、直接透传标准轴，观察信号链；第二台留作以后 Lua/PID 输出，通道命名如 `AP_Pitch`
- `Gyroscope-1` × 1 装上但**默认关**（activationGroup 绑一个空闲 Activate 键），做"官方增稳 vs 自己写的 PID"对比实验
- 第一版纯手动飞，以上全部不接入

## 五、完工后的验收试验（都在关掉 Lua 控制、纯手动下做）

1. **松杆滑翔**：配平后松杆 10 秒，姿态应基本保持、缓慢下沉 → 静稳合格；若俯仰发散，重心再往前调
2. **短周期激励**：稳住平飞后猛拉杆 0.5 秒回中，俯仰角应 1~2 个来回内收敛 → 阻尼合格
3. **长周期观测**：推油门 50% 保持住，记录高度随时间的缓慢振荡（升降模态），目测周期即可——这是我们第一个要建模的环节
4. 每一步的结果记到本目录，附时间戳描述（哪个操作、现象、大概数值）

## 六、交付给我什么

- 造好后游戏自动存档在
  `%APPDATA%\..\AppData\LocalLow\Jundroo\SimplePlanes 2\AircraftDesigns\SC-1.xml`
  （改完名会生成对应 XML），把它复制一份到本 `designs/` 目录
- 我解析 XML 提取几何/质量/舵面配置，估算配平点和 PID 初始增益，写第一版 Lua 定高控制器

## 已知零件名速查（来自 DesignerParts.xml，游戏内 UI 名称可能不同）

`Wing-2` `Wing-3`（可调翼型/后缘铰链 `allowControlSurfaces`） ·
`ControlSurface-Flap-1~3`（舵面件） · `Fuselage-Body-1` `Fuselage-Hollow-1` `Fuselage-Cone-1` ·
`Cockpit-Canopy-1` · `Gyroscope-1` · `FlightComputer-1` · `Wheel-Resizable-1` `GearLeg-1`
