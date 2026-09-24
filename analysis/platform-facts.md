# SP2 平台法典（源码级事实，2026-09-21）

反编译工具链：ilspycmd 9.1（nupkg 直解，`dotnet ilspycmd.dll`）。全量反编译源码在
`%TEMP%\decomp`(Game.dll) / `%TEMP%\decomp-common`(Jundroo.Common.dll)，关键文件已拷入本目录 `decomp/`。

## 一、表达式引擎（Jundroo.Common.Expressions.SpecialFunctions，源码实锤）

| 函数 | 实现 | 含义 |
|---|---|---|
| `sum(x)` | `value += x * Time.deltaTime` | **按秒积分，时间归一** |
| `rate(x)` | `(x - last) / Time.deltaTime` | 按秒微分；首帧返回 0 |
| `smooth(x,t)` | `MoveTowards(last, x, t*dt)` | 限速跟踪器，首帧=x |
| `PID(T,C,p,i,d)` | `p·e + i·Σe·dt + d·(C_last−C)/dt`，e=T−C | **无输出限幅、无抗饱和**；D 作用在测量值上 |

**我此前"增益按拍÷50"的推断作废**：一切按秒。E3 连环爆炸的真实主因见下。

## 二、求值时机（AircraftScript.cs:556/1796 实锤）

- 表达式在 **渲染帧**求值（`Controls.Update(Time.deltaTime)`，`GetDeltaTime = Time.deltaTime`）；
- 机体状态在**物理拍**更新 → 对一个阶跃变化的量求微分会出现采样错位尖峰；
- **推论**：`rate(AltitudeAgl)` 类写法噪声大且随帧率变化；官方为此提供 `PitchRate/YawRate/RollRate` 原生变量（wrap 感知 + 机体坐标系）。**PID 的 d 参数在本平台慎用**，阻尼一律用原生速率变量显式写。

## 三、Setter 语义（VariableSetter.cs 实锤）

- `activator` 编译为 **bool 表达式**（`Parser.Process<bool>`）；填 `3` 这类非零数大概率恒真 → **Setter 常开、PID 积分器在"断开"期间照常累积**，接通瞬间输出旧账——E3"接通即满舵"的头号嫌疑。规范写法：`Activate3`；
- 编译失败静默降级为常量 0，**错误只写进 Player.log**（`Invalid expression on part {id}`）→ 每轮实验后 `tail` 日志是标配调试手段；
- 同名多 Setter 按 priority 仲裁；面板顺序=求值顺序。

## 四、变量符号约定（CraftProxy.cs + 行为对照）

| 变量 | 代码定义 | 符号 |
|---|---|---|
| `PitchAngle` | `asin(cockpit.forward.y)·deg` | **抬头为正** ✓ |
| `PitchRate` | 机体角速度 x 分量·deg | **待实测**（Unity 左手系 +x 旋转=低头方向，与 PitchAngle 可能反号！） |
| `Heading` | 社区确认 −180..180 | 用 `deltaangle` |
| 表达式→舵面 | `StandardFlap: controls[0]·MaxDeflection`，副翼镜像用 `WingFlipped` | **待 C1 地面测试**：常数 0.3 上电看抬头/低头 |

角度/速率符号不统一是本次所有"方向反了"的最可能根源，两个 30 秒测试即可结案（见 §六）。

## 五、机体参数与气动（Wings.Physics 模块结构）

- 气动=**升力线求解器**（`LiftingLineSolver` + `GeneratePolarsJob`），翼型极曲线来自 Drela 风格数表（`SampleFig39a/39b/6111_40`…），失速曲线 `StallCurve`，逐展向切片计算——**没有一张"本机 CLα"表可查**，参数在运行时按你的 XML 几何生成；
- 但游戏把关键气动力做成了**零件变量**（`[VariableOutput]`）：`Lift Force / Drag Force / Current Angle / RPM / N1 / InputTorque / Grounded / Heading Angle`…——这就是官方给的**在线传感器**，接 Gauge 或表达式即可读出实飞升力，做离线辨识不用黑盒猜；
- 设计器设置里有 **`Overload XML Editor`**（GameplaySettings.xml `Designer` 节），开启后疑似可直接编辑飞机 XML——待验证，若可用则"改参数不用点 UI"。

## 六、结案用的两个地面测试（各 30 秒，不飞）

**T-A 执行器符号**：升降舵 = `Activate3 ? 0.3 : 手动基线`。按 A3 看舵面：后缘向下(抬头力)= 正输出抬头。
**T-B 速率符号**：平飞轻拉杆抬头，升降舵临时 = `clamp(0.5*PitchRate,-1,1)`：若舵面向"抑制"你拉杆的方向打 = PitchRate 抬头为正；同向 = 反号（则所有阻尼律符号都要修正——E1 的 `-0.06*PitchRate` 有效这一事实已经暗示它反号，T-B 只是确认）。

## 八、MFD Lua：游戏内置的脚本通道（2026-09-21 晚发现，本项目最重要的基础设施）

**证据链**（全部源码级）：`MFD-1` 是零件库正式零件 → `MfdScript.OnPreStart` 加载资源
`Craft/Mfd/MfdProgram`（XML）→ `MfdProgram.LoadXml` 支持 `<Script>` **内联 Lua**（无 file 属性时取节点文本）→
MoonSharp 沙箱，回调契约 `initialize() / update()（RoundRobin 每帧）/ onPageSelected(id) / onMfdButtonPressed(id)`。

- **注入全局**：`craft`（CraftProxy：Altitude/AltitudeAgl/IAS/TAS/GS/PitchAngle/PitchRate/YawRate/RollAngle/RollRate/Heading/AoA/AoS/GForce/VerticalG/Fuel/Time/Lat/Lon/AngularVelocity）、`craft.Controls`（Pitch/Roll/Yaw/Throttle/Trim/Brake/Flaps/Vtol 实时输入）、`mfd`（屏幕 widget）；
- **输出通道**：Lua `print()` → `Debug.Log` → **Player.log**（遥测 CSV 免费到手）；
- **控制通道**：`craft.Controls:OverrideInput(轴名, 值)` / `ReleaseInput(轴名)` —— **每帧任意改写输入轴 = 完整自动驾驶仪**，有真变量、状态机、积分器，绕开 Funky Trees 一切限制；
- 官方自带程序 `DefaultProgram.lua`（已 dump 到 `analysis/mfd-lua/`）9.9KB，本身就是 OverrideInput 用法教材（目标舱摇杆控制）。

**工具链**（`analysis/` 下）：
- `mfd-lua/build_patch.py`：官方脚本+`telemetry-addon.lua` 内联合成 → UnityPy 写入 `resources.assets` 的 MfdProgram TextAsset（自动备份 `.orig`；还原=Steam 验证完整性或拷回备份）；
- `mfd-lua/telemetry-addon.lua`：2 分频采样 → `TEL,...` CSV 行；预留 `ap_enable` 的 Lua 姿态 PID 钩子；
- `parse_telemetry.py`：Player.log → 按架次切分的 CSV + 采样率统计。

**注意**：MFD 被相机剔除/座舱外视角时 update 可能停摆——采样时间戳以每行 `craft.Time` 为准；
改的是游戏本体文件，仅限单机使用；Steam 云同步/游戏更新会覆盖补丁（重跑 build_patch 即可）。

## 九、其它探明通道（备用）

- 官方 Mod 格式 `.sp2-mod`（AssetBundle+ModManifest.xml，需 Unity 打包，重）；Steam 启动参数可直载 mod 文件；
- 游戏内置 **Developer Console**（`SimplePlanesDevConsoleScript`，Rewired 动作 DeveloperConsole 触发，
  支持 `/ > . ..` 层级检视 GameObject 与组件字段；ModTools API `IDevConsole` 可注册自定义命令）——进游戏试着按 F12/`~ 开不开得出；
- 表达式编译错误只写 Player.log（`Invalid expression on part N`）→ 每轮实验后 tail 日志为标配。

## 十、符号法典（终版：代码+行为互证，2026-09-21 深夜）

| 量 | 正方向 | 证据 |
|---|---|---|
| Pitch/Roll/Yaw 输入轴 | 推杆/右杆/右舵 | 官方 AI 爬升输出**负值**直送 Pitch 轴，消费端无翻转（AiControlledAircraftScript.cs:583） |
| PitchAngle | 抬头 | AircraftScript.cs:249 `[Exposed] asin(forward.y)` |
| PitchRate | **低头** | Unity 左手系 ω_x；E1 的 `-0.06*PitchRate` 有效互证 |
| 高度误差→俯仰指令 | 负增益=爬升 | 实测 -0.003 收敛 + 官方 AI 同向 |

**推论（重要）**：形如 `+K*PitchAngle` 的姿态律是**正反馈**。E2 原版 `PID(0,PitchAngle,+0.05,…)` 理论上发散，
当时"手感好"疑似被 Trim 前馈与机体静稳掩盖 → **待复测**：改 `PID(0,PitchAngle,-0.05,-0.002,-0.05)` 对比。
E1 阻尼律符号正确（PitchRate 反号抵消）。高度环负增益正确。

## 十一、官方 AI 控制律（本物理引擎的出厂调参，可移植）

`AiCfMaintainAltitude`（全文已读）：
```
err = T - h
|err|<100 → ∫ += err·dt·0.001        （条件积分=抗饱和）
否则 err = clamp(err,±100)
desired = normalize((0, err+∫, 0) + forward_horiz·100)   （100 m 前瞻=轨迹整形）
pitch_cmd = -dot(desired, bodyUp)                          （几何俯仰误差）
```
`AiCfLevelWings`: `roll_cmd = dot(Rotate(up, θcmd, forward), right)`。
二者经 `SetInputOverride` 走与表达式/Lua **同一轴系** → 官方增益=本平台最佳初值参考。

## 十二、气动模型规格（L2 离线建模原料）

- 翼型预设：`Symmetric=NACA0012`、`Semi-Symmetric=NACA3412`、`Flat Bottom=NACA3311`；
  任意 NACA 4/5 位 + 双凸解析（`NACAFoils.ParseNACA`）。TESTaircraft 主翼=NACA3412。
- 升力线求解 + 逐切片极曲线；舵面增量：
  `δ·Fig39a(cf,t/c)·Fig39b(cf,升力梯度修正(Re))·Fig6111_40(cf,|δ|)·coverage`，ΔCLmax 同族；
  **含雷诺数修正**（reynoldsPerMeter）。公式全在 `StandardPhysicsFunctions.cs`（已反编译在档）。
- 离线复现两条路：逐公式抄写（重）；或飞 CSV 辨识低阶模型再与公式版对照（推荐，即 L2）。

## 十三、Lua 沙箱边界（MoonSharp 构造器源码）

`new Script()` = `CoreModules.Preset_Default` → **无 io/os 库，不能直接写文件**；
唯一输出通道 = `print`→Debug.Log→Player.log（parse_telemetry.py 为正解）。
`FileSystemScriptLoader` 允许 require 磁盘模块（路径待实测）。

## 十四、杂项终裁

- `overloadXMLEditor`：全代码零引用 = **死设置**，改了无效（收回上轮期待）；
- 物理拍 = Unity 默认 50 Hz（Manifold 原生步长不暴露）；设计器场景 0.1 s；表达式=渲染帧（本机 120 Hz）。
  三时基错位 = rate()/PID-d 噪声根源；
- MFD `update()` 走 RoundRobinUpdateManager 组调度，**不保证每帧** → 遥测一律以 craft.Time 为准。

## 十五、飞机装载通道（推翻"XML 直写不生效"的旧结论）

`Constants.cs:324` `EditorAircraftId = "__editor__.xml"`；`Game.SelectedCraftId` 默认同值；
`Designer.cs:928` 保存时把设计器内容写回 `__editor__.xml`。→ **两条装载通道**：

| 入口 | 实际加载的文件 |
|---|---|
| 设计师→试飞按钮 | `Crafts\__editor__.xml`（工作副本，每次保存覆盖） |
| 机库→选命名机→起飞 | `Crafts\TESTaircraft.xml` |

推论：2026-09-21 那次"直写 TESTaircraft.xml 表达式不生效"= 改了试飞不读的文件，**非编译缓存**。
**复测清单**（通过后 XML 直写解禁，脚本改参通道打开）：
1. 改 `TESTaircraft.xml` 某零件 `deadMassKg` +50 → 机库起飞 → 空重 1154→1204？
2. 改升降舵 `maxDeflection` 30→10 → 满杆幅度肉眼可辨？
3. 改 `input="..."` 表达式 → 是否同样生效（表达式与参数可能不同路径，最后单独验）。

SP1 时代的 overload 全局零件库改参在 SP2 无对应物（`DesignerParts.xml` 只是设计器展示模板，
零件基础参数在代码/资源内）；但**已装机零件的全部 State 属性都是 XML 明文**，脚本化改参=可做。

## 十六、帧延迟定律（session 3/4/5 抖动机因结案，裸杆对照实验裁决）

**实验链**：统一律（q 阻尼在 AP_Out setter 内）→ 全模式 2 采样振铃（pr 逐样本翻符号、pa 不动）；
把 q 项挪回升降舵表达式（同帧）的版本 → 手动段在 53Hz 采样下干净。
**结论**：Setter 输出被舵面表达式读取时**晚一帧**（渲染帧求值链）。速率反馈（q 阻尼）经这一帧延迟，
在高频段相位滞后 ≥180° → 阻尼变激励 → 奈奎斯特极限环。
**设计规则**：
1. `-K*PitchRate` 类快反馈必须与舵面同帧（写在舵面表达式里）；
2. Setter 只放慢动力学（姿态 P 环尚可，速率环不行；外环高度/航向天然慢，安全）；
3. 之前"PID 的 d 参数禁用"是本定律的一个特例（d 即帧内微分+帧间延迟的最坏组合）。
**定型架构**：FT 同帧快内环（Trim 前馈 + 姿态 P + q 阻尼）+ Lua 慢外环（OverrideInput，真 dt、抗饱和积分）。

## 十七、Targeting/敌机数据通道（任务1 终审，2026-09-22，反编译+实机探针双重验证）
- **Lua 可见面（TargetingSystemProxy/TargetProxy/WeaponSystemProxy 全量反编译）**：
  - `craft.Targeting.Mode` 可读可写，枚举 `{Off, AirToAir, AirToGround, Chad}`；
  - `craft.Targeting.Target`：有被跟踪目标时非 nil，**只暴露 `Distance`(m) 与 `Name`**；
  - `NextTarget()/PreviousTarget()` 循环切换、`SelectWeapon(i)/GetWeaponSystem(i)`（Ammo/Name/Selected）、`TgpActive/TgpDistance`（吊舱）、`CountermeasureAmmo`；
  - 锁定锥角 `TargetingAngle` 来自当前选中武器系统（每武器一个锥）。
- **CLR 后门判死**：实机探针 14 连测——`craft.MainCockpit`（原生 PartScript）报 `cannot convert clr type`，MoonSharp 拒绝未注册类型转换，`MainCockpit.Aircraft.TargetingSystem...Target.Position` 整条链全部不可达。目标位置/速度/离轴角 **Lua 拿不到**。
- **敌机系统真实存在**：`WorldObjects.Combat.*`（EnemyPlaceholderScript、FlakCannon、MissileDefense）+  multiplayer `BomberInterceptActivityScript.AIBomber`；AI 行为函数 `AiCfEngageWithGuns/AiCfFlyToLocation` 在 AI 侧（非玩家 FT）。武器零件清单（PartTypes.xml）：Wing Gun、Minigun、Rocket Pod、Boom25/50 炸弹、**Interceptor（空空导弹）**、Guardian、Inferno/Cleaver（地弹）、Countermeasure Dispenser、Targeting Pod Lite(50kg/8km) / Targeting Pod(227kg/16km)。
- **导引架构裁定**：目标方位不可观测 → 采用**锁定锥=信标**的导引头逻辑：`Target~=nil` 即"目标在机头锥内"的布尔方位信息；导引律=丢失搜索、保持锁定、dD/dt<0 收距。距离是唯一连续量，用 0.5Hz LPF 后微分得接近率。
- **用户证词修正（2026-09-22 上午）**：Targeting Pod 实际**只锁地面目标**；空中目标识别**不依赖吊舱**（机体原生即有 AirToAir 能力，推测由武器系统提供锥角）。吊舱在空战构型中非必需，其 TgpDistance 通道归地面任务线。

## 十八、FT 表达式变量全清单（2026-09-22 反编译终审）
- 注册机制：`Context(true, AircraftScript)` 反射扫描，属性标 `[Exposed]`（含 private）即成 FT 变量；控件轴由 AircraftControls.SetupContext 注册（Trim/Pitch/Roll/Yaw/Throttle/Flaps/Vtol/Brake/Activate1-8/FireGuns/FireWeapons/LaunchCountermeasures/ParkingBrake/LandingGear*）；零件级另有 [VariableOutput]（RPM/Thrust/Torque/Suspension…）。
- AircraftScript [Exposed] 全集：Altitude, AltitudeAgl, AngleOfAttack, AngleOfSlip, FuelProportion, GForce, GS, Heading, IAS, Latitude, Longitude, PitchAngle, PitchRate, RollAngle, RollRate, TAS, Time(注册名，属性 TimeSinceStart), VerticalG, YawRate, Rpm1-4, GetAmmoForWeapon, SelectedWeaponName, **TargetDistance, TargetElevation, TargetHeading, TargetLocked, TargetLocking, TargetSelected**。
- **重大含义**：目标方位角/仰角/距离在 FT 表达式直接可读（Lua 侧仍拿不到，CraftProxy 无这些成员）→ Task4 导引律从"信标盲猜"升级为"真方位 PN"，且可写成无记忆 P 律放舵面表达式（同帧，无帧延迟问题）；Lua↔FT 无变量桥（单向：Lua→轴→FT），导引归 FT、模式机/积分/能量归 Lua。
- **CG 读取判死**：CraftProxy/FT 变量/XML 均无机体 CG 坐标；`DrawCenterOfMass`（红球）是无人调用的调试死代码；XML 只有 5 块主翼的局域 centerOfMass 与逐件惯量，整架质量分布需复刻体积×密度模型才可离线算 CG（暂不做，静稳度以实飞包络为准）。
- 实测教训（telemetry25）：用 TimeSinceStart 报 `Name not defined` → **表达式任一符号编译失败=该舵面整条失能（输出 0）**，报错进 Player.log "Invalid expression on part N"；变量注册名以 [Exposed(Name=...)] 为准。
- 工具链注记：ilspycmd 全量反编译产物在 tools/ilspycmd/full/Game.decompiled.cs（20 万+行，grep 直达）；Jundroo.Common.dll 含表达式引擎本体（Context/Parser/SpecialFunctions）。

## 十九、零件表达式轴变量白名单（telemetry26 事故补录）
- `Vtol` 在副翼零件表达式报 `Name not defined: Vtol` → AddProp 注册的轴变量名以输入系统 Id 为准，**并非所有物理轴都进了零件上下文**。
- **实测可用白名单**：Roll / Pitch / Yaw / Trim / Throttle（SC-1 舵面律多年验证）+ Flaps（襟翼件编译通过）。
- **规程**：未验证的变量名一律先挂到一个无害 Setter 上试编译（Player.log 无 Invalid expression 才算存在），再进舵面律。导引武装开关最终方案=**Flaps>0.5 作 master arm**（战斗机不需用襟翼，征用；IAS>80 门保证着陆速度下自动失效）。

## 二十、Target 变量真值表（2026-09-22 v9"没效果"案终审，代码级）
- `TargetHeading` = **目标真实方位角**（atan2(target−self)，0..360 罗盘）——语义清白，wrap 处理正确；
- `TargetLocked` = TargetSelected **且 WarningState==Locked**（武器级锁定：需选武器+锥内驻留充 LockPercentage）——**普通跟踪下恒 false，v9 律拿它当门=恒零输出=“没效果”的全部真相**；
- `TargetSelected` = CurrentTarget≠null **且 TargetMatchesMode**——模式必须匹配目标类型：**战舰/地物要 AirToGround(2)，空目标要 AirToAir(1)**（枚举 Off=0/AirToAir=1/AirToGround=2/Chad=3）；
- Lua 的 `Targeting.Target~=nil`（跟踪档）≠ FT 的 TargetLocked（武器锁档），两口径不是一回事；
- 修正：导引门一律用 `TargetSelected`；Lua 按钮 5 改模式循环写入（1→2→off，int 写入已验证可行）；v9.1 待冷启动生效+副翼/LOS_E 门换名。

## 二十一、滚转极性标定终审（2026-09-22 深夜，telemetry31 标定局，76.6Hz）
- 实测：`Roll 轴+（右杆）⇒ RollAngle 减小`；Roll轴− ⇒ RollAngle 增（+78°/段）；
- 即 **RollAngle 正方向 = 左滚**，与直觉相反；CraftProxy/FT 的 RollRate(ωz) 与 dRollAngle/dt 同号；
- 由此定案：v7.1 滚筒振荡、t28 蛇振、t30 两次"武装即倒扣钻地"同一根因——**内环 `k(b_c − RollAngle)` 是正反馈**；
- 正确副翼内环：`a = k1·(RollAngle − b_c_R) − k2·RollRate`，其中 b_c 在 RollAngle 坐标下取 `−clamp(0.6·LOS_E)`（右转为负）；合式 `a = k1·(RollAngle + clamp(0.6·(LOS_E−1.5·LOS_D),±40)) − k2·RollRate`；
- deltaangle 采用 Mathf 惯例 (a,b)=norm(b−a)：LOS_E=deltaangle(Heading,TargetHeading)=目标方位−本机航向（正=目标在右）→ 需右转 → RollAngle 负 → 律输出负？不——`RollAngle + 0.6·(+d)`：d>0 → 项为正 → a>0=右杆 ✓（轴正即右杆，RollAngle 被压负）。

## 二十二、FT 官方文档订正 + v15 观测量落盘（2026-09-22，用户贴原文）
- 输入轴全集比实测白名单多：`Pitch Roll Yaw Throttle Brake Trim VTOL LandingGear FireGuns FireWeapons LaunchCountermeasures Activate1..8`——**FireGuns 是机体级标准轴**，机炮自动开火律应挂输入面板，不再喂枪零件输入；零件上下文仍按 §十九 白名单。
- 运算符：`==`/`!=` 合法（此前防御性绕写成 abs()>0.5 可省）；`&&` 非法确认（文档只有 `&`/`|`/`!`）。
- `ammo("武器名")` 函数存在（读备弹，可作开火证据观测）。
- `PID(target,current,p,i,d) = p·(target−current) + i·sum − d·rate(current)`：d 项是 **−d·rate(current)**，THD 律里 d=−0.015 给出 +0.015·θ̇（抑俯仰速率）符号正确。
- `smooth(x,t)`：状态化限速跟踪（MoveTowards），t=最大变化速率——抖源滤波的标准件。
- Latitude/Longitude=米制世界坐标（craft.Time=关卡加载时刻，全场面脚本共同时基）。
- **日志污染事实**：AI 机群每架都带 MFD→同一 Player.log 至少 9 条 TEL/SEEK 流交错（t36 局），之前"单架次"csv 实为混流；craft.Time 共享所以各流时间戳重叠不是异常。
- v15 补丁（已 apply，需冷启动）：所有 TEL/SEEK 加 `cid` 身份列（首帧位置派生）；新增 `POS,cid,t,lat,lon,alt`（4帧）与 `TGT,cid,t,px,py,pz,vx,vy,vz`（10帧，代理不暴露 Position 则 −99999）；wgdump 探针删除。parse_telemetry.py v2 按 cid 分流。下一局起可离线 1:1 重建 EPS/VPS/CHI/ECX/BANK，导引律定罪/脱罪从此有据。

## 二十三、FT 官方文档全集订正（2026-09-22，项目根 FunkyTrees_文档全集.txt）
- **调试控制台（重大）**：PC 反引号打开，`DebugExpression "表达式"` 实时读任意 FT 值（串内引号用 ## 替换）——"setter 面板不可读数"仅指 UI，控制台是正规观测通道，v15 自动流之前先用人眼通道。
- InputController.State 的 **min/max 是 [-1,1]→[min,max] 映射不是钳位**（input=1→部件收 max）；钳位要写进 input 表达式内部。
- activationGroup/activator 可写任意 FT 表达式（数字>0=激活）；同名变量 setter 按 priority 仲裁（默认0，可负），panel 顺序=求值顺序（XML `<Variables>` 内先后即游戏内顺序，官方确认）。
- **&/| 短路**：第二操作数被跳过时其中 rate()/sum() 不更新 → 三元门内 rate 在重入瞬间有陈旧跳变（LOS_R 抖源候选，修法=rate 移出分支）。
- 布尔数值语境 True→1/False→−1；`=`/!=/%/显式 * 规则成文；表达式**每物理 tick 求值**（SP2=服务器 tick 率，物理质量越高越快）——修正此前"渲染帧"说法。
- 部件变量输出含 Cockpit 系 PosX/PosY/PosZ/Heading…（机体位姿可自行注册输出）；Wheel/WheelAssembly 有 **Grounded** 接地标志（v6.3 地面判据旧痛点，SP2 若装轮件可用）。
- ammo("武器名") 查备弹；SelectedWeapon 未选武器返回空串。

## 二十四、传感器地板（2026-09-23，SC-3 滑跑不刹车案）
- **AltitudeAgl 地面读数下限 ≈1.6~2.0 m**（座舱量测点离地，非轮子）：一切"接地/低高"判据必须 >2.5 m（着陆 TOUCHDOWN 定 3 m；v6.3 地面告警门 agl>3 同理）；
- **螺旋桨机停车 IAS 是假数**：发动机一开车，桨滑流把静止 IAS 吹到 45+——凡地面态判定（停机/滑跑/捕获）禁用 IAS 阈值，只看 agl（v3.3 连坐：STANDBY 判定、AUTOCAP 都栽过）；
- 判据阈值必须先问传感器地板，再谈物理——两个案底同一形状：把阈值设在测量下限之下=逻辑死码。

## 二十五、craft.AngleOfAttack 符号反约定（2026-09-23，SC-3 前轮拍地案）
- **Lua `craft.AngleOfAttack` = γ−θ = −（空气动力学真迎角）**，与 FT 面板 `AngleOfAttack` 及直觉约定相反。实锤：两局着陆拉平窗 θ=−0.7°、下沉 5.6 m/s@GS55 → γ≈−5.8° → 真 α=+5.1°，而读数恒 −5.1°；
- **任何用 α 的判据/控制律必须先取负**（`local aoa_true = -craft.AngleOfAttack`），否则指令反号；v4.1 初版未翻号 = 拉平环自我饱和、满杆仍前轮先拍；
- 通用标定法（无现成结论的新量都适用）：用两个独立可测量做几何核算（θ、γ=asin(−vg/GS)、α=θ−γ），三者关系一比对符号即定。
