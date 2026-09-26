# SimplePlanes 2 零件输入/输出法典（全量解包档案）

生成日期：2026-09-26。方法=全量解包 + 逐类源码实读，不是抽样。

**数据底座（三份可复跑产物，均在 `analysis/data/`）**
- `parts_ic_channels.csv` — 87 条 IC 通道（61 零件型）：通道名、defaultInput、defaultMin/Max、zeroOnDeactivate；
- `parts_inventory.csv` — 178 零件型 × 93 修饰符的全部 XML 属性；
- `parts_io_facts.json` — 每个修饰符对应的 Data/Script 类自动特征（IC 读法、钳位、VariableOutput）；
- 重跑：`python analysis/scripts/dump_parttypes.py`、`python analysis/scripts/extract_parts_io.py`。
- 本篇覆盖**零件+引擎语义**；**FT 内置变量（Time/IAS/TargetHeading…）的接收面**在 `platform-facts.md` 符号法典与 `FunkyTrees_文档全集.txt`，不在本篇范围。

**证据分级**
- `[G§n]` = `tools/ilspycmd/full/Game.decompiled.cs` 第 n 行（2026-09-22 反编译，对 Game.dll 2026-09-20 版）；
- `[J§n]` = `tools/ilspycmd/full/jundroo/Jundroo.Common.decompiled.cs` 第 n 行（**本次新增**：FT 表达式引擎本体在 `Jundroo.Common.dll`，Game.dll 里没有 Parser）；
- `[XML]` = `analysis/decomp/PartTypes.xml`；`[实测]` = 本项目架次（platform-facts / ft-part-matrix / SC 验尸账）。

**modifier 标签→类名规律**：`<Tag>` → `<Tag>Data` + `<Tag>Script`；例外：`Switch→CockpitSwitch*`、`Button→CockpitButton*`、`AttitudeBall→AttitudeBallBehaviour`、`FloatingPart=纯数据`（浮力参数）、`Engine→EngineScript 族`。已按此对 93/93 类全数定位成功。

---

## 一、FT 表达式引擎的数值语义（一切"精度"的源头）

### 1.1 类型系统：只有 float / bool / string 三型
- 数字常量按 `float.Parse` 后进 `ConstantToken<float>` `[J§26558-26561]`；**全程 float32，无 double 提升**；加减乘除取模的 token 一律实例化为 `BinaryOperationToken<float>` `[J§26252-26257]`，比较/逻辑实例化为 `<bool>` `[J§26241-26251]`。
- 表达式最终编译为 **LINQ ExpressionTree** 再编译成委托 `[J§26318 起]`——求值就是原生 CLR float 运算，无自定义舍入。
- **浮点比较没有 epsilon**：`=`/`!=` 直接映射 `ExpressionType.Equal/NotEqual` `[J§26346-26348]`——对 float 是**精确位比较**。写 `x=0.3` 判等几乎必然永假；一切相等判断要用区间（`abs(x−0.3)<0.001`）或整数格点（`abs(x−i)<0.5`，面板已定式 `[实测§26]`）。

### 1.2 词法（TokenDefs 正则表 `[J§26236-26266]`）
| 事实 | 正则 | 后果 |
|---|---|---|
| 数字 | `\G[0-9\.]{2,}` 或 `\G[0-9]+` | **科学计数法 `1e9` 不可用**（`e9` 会被切成变量名）——[实测] "写全数字"纪律的源码依据 |
| 名字 | `\G(?:v:)?[A-z_][A-z_0-9]*` | 支持 `v:` 前缀（变量命名空间访问）；`[A-z]` 是宽松区间，`[\]^_` 也算名字头 |
| 运算 | `\G(?:(?:[<>!]=?)|[\+\-/*&\|=:?%])` | **`==` 不在表内**→切两个 `=`→`Unary operator not supported: Equal`→面板全灭 `[实测 app56]`；`>= <= !=` 合法 |
| 成员 | `\G\??\.(?!\d)` | `.x` 访问向量分量、`?.` 空安全 |

### 1.3 优先级（OrderOfOperations `[J§25607-25634]`，越靠前越高）
1. `*` `/` 2. `%` 3. `+` `-` 4. **比较六个**（`> < >= <= = !=`） 5. `&` `|`
- **比较低于加减**：`a+1>b` 天然成立；但 `a&b>c` 解析为先 `a&…`？不——`&` 最低，`b>c` 先结合。真正的坑是同层的 `=` 与 `>` 混用，**一律加括号**（面板纪律 `[实测§26]` 维持）。
- 三元 `?:` 不在此表（归约在优先级之外），**嵌套三元行为未证，继续禁用** `[实测 ft-part-matrix]`。

### 1.4 布尔↔数值互转（引擎级，Converters `[J§25488-25498]`）
- `BoolToNumber`：true→**1f**，false→**−1f**——§23 "False→−1" 法典的源码正身。
- `NumberToBool`：`v>0f` 才为真——**0 是假**；配合 min/max 映射，`0` 输入=假、任何负=假。
- 转换发生在需要时（`ConvertIfNecessary`），例：`clamp(Activate7,…)` 里 Activate7 的 bool 会先变 1/−1 再进 clamp（**不是 1/0**）。

### 1.5 求值时机与顺序（Game.dll 侧）
- **Setter 面板**：`VariableSystemScript.FixedUpdate`（挂在飞机 GameObject 的普通 MonoBehaviour，Unity 默认序）按 **XML 列表顺序串行**求值：StartFrame→零件输出变量先写→`foreach (Setters)` `[G§210203/210358-210401]`。**面板行序=执行序**（列表来自存盘 XML 序 `[G§198133-198143]`，编辑器按行重建 `[G§171348]`）；后条读到前条**本帧新值**，无拓扑排序——前向引用编译期报 `Name not defined`、整面板全灭 `[实测§26]`。
- 单条写入条件 `setter.IsCompiled && setter.Activated`，否则该变量**保持上一帧值** `[G§210385-210389]`（未激活=冻结而非清零）。
- ⚠ **新出入点（源码 vs 实测）**：`Activated`=`_compiledActivator()`，activator 字段**为空才恒真** `[decomp/VariableSetter.cs:14-24]`——源码语义上非空 activator 是有门控的；但 [实测 session-1] 判"activator 无门控作用（恒真）"。两者未合拢，留待专门一飞裁决（写一个 `activator="Time>30"` 的 setter 看 30 s 前后行为）。**在此之前维持实测纪律：门控写函数体内三元。**
- ⚠ 新发现：机体加载有 **`Flaps`→`LegacyFlaps` 全局改名**（setter 名、函数体、零件 IC input 三处都替换）`[VariableSetter.cs:67-98]`——旧存档兼容逻辑；跨机体搬 `Flaps` 信号前先查该机体 xmlVersion。
- **IC**：`InputControllerScript` 注册在 CraftUpdateManager 的 FixedUpdate **order=−100**、flags=`FlightUnpaused` `[G§250991-250993]`。两套 FixedUpdate（VariableSystem 的 MonoBehaviour 序 vs CraftUpdateManager 内部序）**之间无显式排序声明**——setter 与 IC 同帧先后不保证（与 [实测]"同帧求值"历史观察并存，归因时勿当已证）。
- **暂停/时标**：IC 暂停即停更（FlightUnpaused 门）；setter 面板的 MonoBehaviour **无暂停门** `[G§210358-210363]`；慢放时 `fixedDeltaTime×=timeScale` `[G§111695-111699]`。`rate()` 分母=`Time.deltaTime`（缩放时基），timeScale=0 时**除零无保护**（rate/PID 的 d 项——印证 §d 恒 0 纪律的另一半成因）。

### 1.6 内置函数（Context.cs 反射绑定，float 签名）
- **度制**：sin/cos/tan 入参=度（`×π/180f`）、asin/acos/atan/atan2 出参=度（`×57.29578f`）`[decomp/Context.cs:287-320]`。
- `sum(x)`=矩形积分 `v+=x*dt`（帧率无关，实机 `sum(1)` 每秒 +1 吻合 `[实测 官方页]`）；`rate(x)`=`(v−last)/dt` 首帧 0；`smooth(x,r)`=`MoveTowards(last,v,r·dt)` **限速跟随**，rate=0 即冻结，首帧直通；PID=`p·e+i·sum−d·rate(current)`，**积分无抗饱和**。
- **状态按编译实例私有**：同一条文本在一处出现两次=两份独立记忆 `[Context.cs:37, SmoothFunction.cs:20-28]`。
- ⚠ **`e` 常量 = `Mathf.Log(1f)` = 0**（原文如此）`[Context.cs:334]`——FT 里的自然常数 e 是个游戏 bug，要 e 写 `2.718281828`。
- `round`=绑 `Mathf.Round`（Unity 实现不在本次反编译范围，**舍入模式未证**；要偶数舍入语义的判据别依赖 .5 平局）。
- `pi`=MathF.PI。其余反射绑定清单（ceil/clamp01/deltaangle/exp/floor/inverselerp/lerp/lerpangle/lerpunclamped/log10/pingpong/pow/repeat/round/sign/smoothstep/sqrt/abs/clamp/log/max/min）`[Context.cs:335-373]`。

### 1.7 控制轴的接收范围（写进表达式之前的上游钳位）
轴层钳位只作用于**物理输入**（键/手柄/增量），表达式型 input 不走这些钳：
| 轴 | 钳位（源码） |
|---|---|
| Roll/Pitch | `Clamp(−1,1)`（叠鼠标后）`[G§197725/197735]` |
| Yaw/Trim/Flaps/VTOL | `Clamp(−1,1)` `[G§197816/197843/197870]` |
| Throttle | `Clamp01` `[G§197887]` |
| FireGuns/FireWeapons/LaunchCountermeasures | **bool**，判定=`override 值 > 0f`（严格大于，无迟滞）`[G§197389-197396]` |
| Activate1-8 | bool[8]，**组 8 上电即 true** `[G§196888/197006]`；ActivateGroup 键取反 |
| Lua `OverrideInput`（raw 路） | **不截断**：多 override 取**算术平均**，可超 ±1 `[G§197515-197535/87360-87370]`；`SetInputOverride` 路才有 3 单位/秒斜坡 `[G§197494-197513]`；两路都 `Sanitize`（NaN/Inf→0） |
- 名字解析兜底：IC 的 `input` 字符串先查轴名，未命中→**当 FT 表达式编译**（`Parser.Process<float>`），编译失败/异常→**恒 0** `[G§197217/197240]`——"表达式写错名=舵面恒零"链路的源码正身。bool 版兜底→恒 false `[G§197363/197380]`。
- 内置比较轴语法：input 可写 `v>`/`v<`（对空速 mph 比较，系数 2.23694f）`[G§197192-197211]`。

### 1.8 InputController 映射与激活（连接两层的阀门）
`UpdateValue()` 全 float `[G§250953-250999]`：
1. 取轴/表达式值 num（NaN/Inf→0）；`Invert Axis`→`num=−num`；
2. **`num<0 ? (−num)·MinValue : num·MaxValue`**——min/max 是两条独立乘数（§0 法典维持）；**此处无 ±1 钳位**，表达式喂 |v|>1 会线性放大（下游消费方各自钳不钳见下文矩阵）；
3. `Invert Output`→取反 Value；
4. 未激活：`ZeroOnDeactivate=true` 才清 0，**否则 Value 锁存上一帧** `[G§250984-250987]`；
5. 激活组解析=`GetActivatorGetter` `[G§197072-197084]`：数字 0 或 >8→`valueIfZero`（**IC 传 true=组 0 恒激活** `[G§251001-251003]`；伞/脱离器/磁/钩传默认 false=组 0 永不）；1..8→组状态；**非数字→整个当轴名/FT 表达式编译**——activationGroup 字段本身就是可编程的（XML 下拉全标 `AllowFunkyInput=true`）。
6. 旧存档兼容：xmlVersion<5 时 LandingGear/FireGuns/FireWeapons 的 Min 或 Max 强制 0（布尔轴单边化）；xmlVersion<6 且 Invert 且 |min|≠|max| 时交换并清 Invert `[G§250884-250905]`。

---

## 二、执行器族矩阵（输入端：表达式 Value → 物理量）

### 2.1 新气动翼面（JWing-1 / JFuselage-1 上挂 `ControlSurface style=…`，舵面零件带 `controlsurface-N` IC）
链路：IC.Value → `_input.SetInputGetter(面序,通道序,()=>Value)` `[G§255245-255257]` → 翼按通道数取用。每面有**声明的输入通道数与量程对**（超序号的 IC 静默丢弃 `[G§217735-217743]`）；取用时 `GetInput(range)` 做**单边乘+硬钳位、无死区**：`v<0→v·(−range.x) else v·range.y` 再 clamp 到 `[range.x,range.y]` `[G§217601-217607]`。**这就是"IC 值超 ±1 会被翼面钳回"的下游客**。

| 面型 | 通道×量程 | 偏角公式 | 速率 | 关键默认值 |
|---|---|---|---|---|
| StandardFlap | 1×(−1,1) `[G§223463]` | `角度=controls[0]×maxDeflection`（单通道直乘）`[G§223484]` | **无限速** | `maxDeflection` 默认 **30°** `[G§223587]` |
| FowlerFlap | 1×(0,1) `[G§221928]` | 伸出=saturate(v/0.8)×maxExtension；偏角=saturate(unlerp(0.6,1,v))×maxDeflection `[G§221949-221951]` → **前 60% 输入只伸不偏** | 无 | maxDeflection 默认 40° `[G§222061]` |
| BrakeFlap | 2×[(−1,1),(0,1)] `[G§220918]` | 通道 0=襟翼偏角、通道 1=刹车偏折合成 `[G§220940-220947]` | ★唯一带限速：`BrakeDeflectionSpeed` 默认 **0.8/s**（≈1.25 s 满行程）`[G§221076-221079]` | flap 30°/brake 上下 80° |
| Slat | 1×(0,1) `[G§222288]` | `偏角=deflectionDegrees×v`、伸出=Extension×v `[G§222309-222313]` | 无 | 默认 30° `[G§222448]` |
| SplitFlap | (0,1) `[G§222704]` | 固定 `radians(−40°)×v` | 无 | 不可调 `[G§222799]` |
| Spoiler | (0,1) `[G§222996]` | 固定 `radians(50°)×v` | 无 | 不可调 `[G§223091]` |
- 精度：全链 float32（Value→NativeArray<float>→Burst）`[G§250934/217668]`，新路径**无量化**。
- `[实测]` 叠加发生在 IC 层（`clamp(Trim + 律, −1, 1)`），翼面不再读 Trim。

### 2.2 旧翼路径（`WingScript`/`ControlSurfaceScript`，prefabId=Wing 的老件）
- `ControlSurfaceTransitTime=0.3s` 一阶过渡 `[G§241786/241854]`；输入曲线 Linear；`Angle=v×MaxDeflectionDegree`，**MaxDeflectionDegree 是 int 度** `[G§241188/241207]`；几何网格按 **5° 一档**预建 keyframe + Lerp `[G§29085/29176]`——**全场唯一角度量化点**。
- Trim 参与叠加：`Trim×0.25`（方向随 Inverted）`[G§241936-241944]`；激活门失败→num=0 `[G§241949-241956]`。

### 2.3 发动机（油门通道）
| 件 | 消费式 | 钳位/动态 |
|---|---|---|
| Jet（EngineScript 族）| `ThrottleInput.Value×health`→`EngineThrottle`，**双向限速 `ThrottleResponse`（XML 属性，逐机型）**`[G§237211-237226, 255744]` | 无显式 [0,1] 钳（靠输入幅值）；`Clamp(,0.01,1)` 那处**只是音效音量** `[G§255871]`；加力点=`(throttle−0.9)/0.1` `[G§255563]` |
| JEngine（活塞/星型，本机）| `InputThrottle=_controller.Value`（**取第一个 IC**，保符号）`[G§287666]`；负值仅当 Gear<0 取 Abs；`Min(StepTowards(...,ThrottleResponse), EngineThrottleMax)` `[G§287687-287690]` | 油门上限=XML |
| Turboshaft | `Clamp01(InputThrottle)` **负值归 0** `[G§289922]`，再抬到 `Max(IdleGasGeneratorSpeed)`+governor 带 `[G§289935-289938]` | 输出 RPM/N1/N2/Spool |
| CarEngine | 同上族，且 **`EngineThrottleMax` 直接取 IC 的 MaxValue** `[G§238983]` | |
| Exhaust-Pipe | `Clamp01(|Value|)`，IC 非激活直接 0 `[G§293665-293669]` | 纯视觉 |
| Inlet | 脚本空壳（13 行）`[G§250693]` | 无输入 |

### 2.4 螺旋桨 PropellerAssembly（两条 IC，序号 0/1 不可错）
- **#0 BladeAngle（桨距）Manual 才读**：`Clamp(v,−1,1)` → `MoveTowards(pitch, v×maxPitch, **90°/s 硬常量**)` `[G§281289-281299, 281246, 279693]`；`maxPitch` XML 载入无钳（默认 40、设计器顶 90）`[G§279482-279487, 280021]`。Auto 恒桨时此 IC 被 `Disabled` `[实测 v2.5]`。
- **#1 ReverseThrust：只在 Auto + reversePitch>0 被消费**，`Clamp01` **单向钳**（负→0）`[G§280404-280408]`；0~1→`Lerp(零推力桨距, −reversePitch, β)`，**50°/s 硬编码**；`reversePitch` 载入 `Clamp(0,30)` 度 `[G§281163-281165, 280023]`。
- Auto governor 内部：输出 `Clamp(−10,10)·dt`、桨距 `Clamp(5,55)` `[G§281253-281255]`。
- 输出：PitchAngle(°)/RPM/Thrust(N)/Torque(N·m)。

### 2.5 旋翼（直升机）
- HeliMainRotor：cyclic **双通道相加无钳**：`v=_cyclicPitchInput.Value+_cyclicPitchAltInput.Value` →带滞后 10 → `×cyclicPitchMaxDeflection`（XML，默认 **15°**）=桨盘角 `[G§249927-249928, 249582]`。
- HeliTailRotor：`_tailInput.Value + _tailTrim.Value×TrimScale` **相加无钳** → `×TailSpeed`（推进速率量）`[G§250407/250526]`。
- 主输出 RPM="RotorRPM"。

### 2.6 传动
- JTransmission "shift" IC：**不是挡位索引**：`clutch=1−Clamp01(|v|)`，v 上/下沿穿越 **±0.1 阈值**触发 ±1 挡，须回落阈值内才 ReadyToShift `[G§288517-288543]`；挡表=[−1 倒, 空, NumGears 前进] `[G§288084-288106]`；输出 Gear/GearRatio/两端 Torque。
- JDifferential "bias"：`InverseLerp(−1,1,v)` **可外插出 [0,1] 无钳** `[G§286213-286220]`。

### 2.7 轮/刹车（序号即语义，写错=给轮打舵 `[实测]`）
- `BaseWheelScript`（JWheelAssembly 族）@L270577：**按名字取** `Turn`/`Brake` 两条 IC（`GetInputController("Brake")` `[G§271055]`）；刹车=`Clamp01(v+（手刹?1:0)）`，力矩=`v×(手刹?5:1)×weightOnWheel×WheelRadius×mult×2`（v≤0 → 力矩 0）`[G§271123-271133]`——**只认正半轴、∝轮载（物理自带接地门）**；转向=`StepTowards(当前角, TurningRate·dt, v×TurningAngle)`（TurningAngle≤0 时整段跳过）`[G§271136-271140]`。
- ResizableWheel："Turn" IC → `StepTowards(…, TurningRate·dt)`，`TurningRate` 默认 **150°/s** `[G§262934-262939, 262302]`。
- 输出：ForwardSlip/SidewaysSlip（滑移率）、Grounded、Offroad、RPM。

### 2.8 起落架（原厂腿=Animator 驱动，量程 [−1,0]→伸 0→1）
- GearLeg-1/GearBay-1 的 IC#0（`min=1 max=0`）→ `AnimatorScript`：`TargetPercent=Clamp01(Value)` `[G§301763]`，`Percent=MoveTowards(Percent,Target, dt/Duration)`——**Duration=XML animationDuration 全程秒数（本机 4 s）**，Value 是位置不是速度 `[G§301994-301995]`；
- `GearLegScript`：`Extension=>AnimatorData.Script.Percent` 输出；`Percent<0.4` 起轮子**连物理都没有**（真收放判据）`[实测 v2.5]`；腿伸缩动画另有 `MoveTowards(localScale.y, …, 3·dt)` `[G§292592]`。
- `LandingGearScript`（Wheel-1/2/3 自带轮族）：`_inputController.Value`→Clamp01→**转向角**（非收放）；收放读 `Controls.LandingGearDown` 轴、轮刹读 `Controls.Brake` 轴 `[实测 v2.5 读类定案]`。
- WingLandingGear（类 @L266741）：动画进度 `Clamp01(_time/_animationTime)` `[G§266805]`——时间驱动不吃 IC；RetractableLandingGear（Wheel-2/3 族，类 @L263055）同理走轴+计时。
- `[实测]` 腿/轮的 IC **只认表达式产出的数值**；控制轴本身不可被面板同名 setter 覆写（探针 A）。

### 2.9 减速板 AirBrake-1
`v=Value×health` → `_drag=v×Drag`、`_targetAngle=v×−65°`，角速率=**误差×dt×100**（≈1 s 内收敛的指数式）`[G§235055-235068]`。**权限极大**（满输入=−65° 板偏+全阻力），[实测坠海局] 已证 12 s 吃 20 m/s。

### 2.10 旋转器/直线作动（两条完全不同的路）
- **JointRotator/HingeRotator/SmallRotator（工坊主力）**：`targetAngle=Value×Range`（度；**无钳**，|v|>1 就超 Range）`[G§256300]`；`Range` XML `range=` 默认 90，>180 载入时**一次性砍到 180** `[G§255990/256267]`；步进 `每 FixedUpdate ±(Speed²×MaxSpeed)·dt`（Speed 滑块 0..1、maxSpeed 默认 20°/s）`[G§256351/256226]`；damaged→目标冻结；输出 CurrentAngle=`SignedAngle` ∈ **±180**（不随 Range 收窄）`[G§256142/256172]`。
- **老 UnityFS `Rotator`**（`<Rotator>` 修饰符）：`localEulerAngles += (x,y,z)×Value×DynamicSensitivity`——**Value=每固定帧的度增量（角速度型！）**，与 JointRotator 的"目标角"语义天差地别 `[G§263365-263392]`。官方机体两种都有，搬式子前先认标签。
- Piston：`v×Range×partScale` 米（Range 0.05~0.75 默认）；Extend=false 时 `1−v`（**v=0 是全缩还是全伸看该属性**）`[G§260670-260681]`；Cycle 模式变 `(cos+1)/2` 振荡；damaged 速率 ×0.25。
- Winch：**连续量**：`targetRange=v×(Range−MinRange)+MinRange`，米制无钳 `[G§266034]`。

### 2.11 姿态控制/喷嘴
- Gyroscope-1：三 IC（roll/pitch/yaw 各 ±1）→ `v×RollRange/PitchRange`（度目标）+ 偏航 `v×YawPower×health`（扭矩）；NaN→0 自带保护 `[G§249334-249341]`。
- EngineThrustPort（VTOL 喷嘴）：IC `primaryInput` **±90**（=喷嘴角度数，XML defaultMin/Max=∓90 `[XML§542]`）；RotatorScript 三轴消费同 2.10 老路。
- RCN：**不吃 IC**——直接 `GetAxisGetter(Roll|Pitch|Yaw 轴, −1..1)`；`|v|`=油门强度、符号×Reverse 决定推力方向（反向输入=无喷）`[G§261310/261330-261350]`。⇒ FT 想单独指挥每台 RCN **没有零件级通道**（只能 Lua 轴覆写）。
- TargetingPod：zoom 通道 `Clamp01`；激光指示读目标位置；activation 门 + Mode==AirToGround + 连驾驶舱 `[G§264401/197xxx]`。

### 2.12 武器（全是布尔门，无一吃连续 IC）
| 件 | 触发源 | 细节 |
|---|---|---|
| Gun（机炮）| **`Controls.FireGuns`（bool，>0 判定）** + 激活组门 | ★`TotalAmmo=int.MaxValue`——**XML ammoCount 对机枪无效=无限弹** `[G§274834/275037]`；射速=`roundsPerSecond`（间隔=1/它），burst 默认 10 发/组、间隔 2 s、初速默认 1000 `[G§274877-274881]`；全场限流 int.MaxValue（MP 有帧限）|
| Cannon | 激活组 `valueIfZero:true` + WeaponSystem 按 `FiringDelay` 发射 | 弹药=ammoCount 真值 `[G§273208]`；fuseInput 可绑轴（<0 解除）`[G§273512]` |
| Rocket/Missile/Bomb/Torpedo | 基类激活组（**valueIfZero:true**）；发射由 WeaponSystem/TargetingSystem `Fire()` | `CurrentAmmo=Launched?0:1` **一件一发** `[G§274259/274325]`；Bomb 挂在 Detacher 脱离时自动 `Fire` `[G§272439]`；Torpedo 无输入 |
| FireWeapons 轴 | **唯一消费者=TargetingSystem**：只打"当前选中武器" `[G§140996/141302]` | 表达式里 `ammo("名")` 读备弹与此一致 `[实测§二十二]` |
| CounterMeasure | `Controls.LaunchCountermeasures` 上升沿/间隔连发 `[G§273927]`；输出 Ammo | |
- 武器激活组语义：非数字 group 字段同样走 `GetActivatorGetter`→**可写 FT 表达式**（见 1.8）。

### 2.13 一次性机构（伞/脱离/钩/磁/弹射座）
全部 `GetActivatorGetter(group, valueIfZero:**false**)` = **组 0/空=永不触发**，纯布尔：
- Parachute：默认组 "1"，一次性 `_deployed` 不可逆，jam 门 `[G§258855/259059]`；
- Detacher：需按住 **>10 帧** + Enabled + Delay（XML 0~5 s 滑条 51 档）`[G§243163/242824]`；
- ArrestingHook/Magnet：`Active()`→抓取/磁力；CatapultConnector **无输入恒开** `[G§239064]`；
- RefuelDrogue：默认组 "7" `[G§261363]`。

### 2.14 仪表与座舱交互
- **Gauge/ADI**：输入**不是 IC**——`GetAxisGetter(Data.Input 字符串, −1..1)`，**能绑任意轴名或 setter 面板变量**（逐指针绑定 `[G§249077]`）；指针角=`Zero + v×Multiplier`（Multiplier 滑块 0~360 默认 360，Zero ±180）**无钳**——超量程指针物理溢出 `[G§249061/248225]`。ADI 不读输入，直接吃机体姿态 `[G§235345]`。⇒ **座舱指针仪表是现成的"面板量可视化"通道**（与 Label 互补，不用改零件式）。
- CockpitButton/Switch：输入=绑轴/表达式 getter（同一解析兜底链）`[G§239753/240953]`；输出=写一个**变量**：`_output.Value = 激活? OutputValue : (0或1)`（模式 Toggle/Once/…），并带 `Active` 布尔沿标记 `[G§241061-241072]`；灯光/按压动画 Clamp01 渐变。⇒ 座舱开关是"人→律"的输入件（比 ActivateN 直观），官方 Droplet 的 setter 面板变量即此族 `[实测 Droplet]`。
- CameraVantage：输出 7 变量（IsActive/LookPitch/Roll/Yaw、ViewOffset XYZ）`[G§238345-238373]`。
- Cockpit-1（输出侧）：Heading/Pitch/Roll Angle（**DeltaAngle 归一 (−180,180]**）、Pitch/Roll/Yaw Rate（机体角速度分量）、Longitude/Latitude/Altitude（世界坐标分量，米）、Speed（机体系点速度）`[G§240110-240144]`。
- **Label-1**：`designText` 含 `{` 才走表达式（`DynamicExpressionText`，LabelScript @L256707）；XML 存 `designText/fontName/fontSize/width/height/…` `[G§256523-256570]`——`[实测]` "容量由 width 定"与此一致。
- **FlightComputer-1 实为无名存件**：registry 定义只有 `<Cockpit hasCamera="false">` + `<FloatingPart weightFactor="3">` `[XML§2089-2092]`——**没有任何专用脚本类**（全码 `class FlightComputer*` 零命中）。"可编程"的实质=它是机体 ExpressionContext/变量面板的挂载锚（`[实测]` 本机只有它带面板）。`FloatingPart weightFactor=3`：它还是浮力锚——**翻扣水面时它是"不沉"的那块**，做水上迫降测试时注意。

---

## 三、零件输出变量全表（60 条 `[VariableOutput]` 实测清点）

启用方式=零件"部件变量"菜单勾选命名（文档 §2.3.4）。单位列：`/0.01f`=源码把内部小质量制还原成常规单位。

| 类 | 显示名 | 值来源（getter 原文摘要） | 范围/单位 |
|---|---|---|---|
| BladedEngineScript | RPM | RpmAbs | ≥0 |
| CarEngineScript | RPM | _engineRpm | ≥0 |
| JEngineScript | RPM / OutputTorque | Powertrain.engine.OutputRPM / outputTorque | ≥0 / N·m |
| EngineScript | Thrust | `virtual Thrust`（Jet 族实现） | N（÷0.01 制） |
| PropellerAssemblyScript | PitchAngle / RPM / Thrust / Torque | PropellerPitchDegrees / \|Rpm\| / `_liftForce·thrustAxis/0.01` / `_dragTorque/0.01` | ° / ≥0 / N / N·m |
| TurboshaftScript | RPM / N1 / N2 / Spool / TorqueRatio / OutputTorque | 各级转速比 | N1/N2 比（0~1 附近），Spool governor 中间量 |
| HeliMainRotorScript | RPM→"RotorRPM"（默认名 RotorRPM 优先级 10） | \|Rpm\| | ≥0 |
| JointRotatorScript | Current Angle | BodyAngle=SignedAngle | **±180°** |
| GearLegScript | Extension / Suspension | Animator Percent / 悬挂压缩 | 0~1 / 米 |
| SuspensionScript | Extension | CurrOffset | 米 |
| JWheelScript / JWheelAssemblyScript / ResizableWheelScript | ForwardSlip / SidewaysSlip / RPM；Assembly 另有 **Grounded** | 轮控制器滑移/转速；GroundedOutput | 滑移率（≈±1 内）、RPM≥0、Grounded 0/1 |
| WingScript（老翼） | Drag Force / Lift Force | `ForceMagnitude/0.01` | N（带符号：SignedLift） |
| BombScript / MissileScript | Fired | 0/1 | 布尔 |
| CounterMeasureDispenserScript | Ammo | 计数 | ≥0 |
| JTransmissionScript | Gear / GearRatio / InputTorque / OutputTorque | 挡索引（−1 倒/0 空/1+ ）等 | |
| CockpitScript | Heading/Pitch/Roll Angle, Pitch/Roll/Yaw Rate, Longitude/Latitude/Altitude, Speed | 见 2.14 | 角度归一 (−180,180] |
| CameraVantageScript | Is Active, Look Pitch/Roll/Yaw, View Offset X/Y/Z | 相机位姿 | |
| （Switch/Button） | 自定义 `_output` | 2.14 | 用户配 |

**内置全局量（非零件）**的接收/回读精度不在本篇——`Latitude/Longitude/Altitude…` 走 `AircraftVariable.Value(float)` 同一 float 面 `[G§201400]`；世界坐标 float 在 ~10⁶ m 量级只剩 ~0.1 m 分辨率（float32 推论，实机标定见挂账）。

---

## 四、精度总结（一页版）

1. **数值面**：引擎/IC/执行器全链 float32（约 7 位有效数字）；无定点化、无网络量化环节参与本地求值。
2. **仅有的量化/离散点**：老翼 5° 几何格 `[G§29085]` + int 度上限 `[G§241188]`；Transmission 挡位离散（±0.1 沿触发）；一切 `MoveTowards/StepTowards` 是**时间离散化不是值量化**。
3. **无 epsilon 浮点比较**——判等必须区间化（1.1）。
4. **表达式的 |v|>1 不会被 IC 层钳**，下游才钳：翼面 `GetInput(range)` 硬钳 `[G§217601]`、Manual 桨距 Clamp(±1) `[G§281299]`、Turboshaft Clamp01 `[G§289923]`、反转推力 Clamp01 单向 `[G§280408]`；**不钳且外插的**：JointRotator（超 Range）、Winch、Piston、differential bias、Gauge 指针。⇒ 同一表达式在不同执行器上"越界后果"不同，**律出口一律自己 clamp**。
5. **速率限制硬常量**：桨距手动 90°/s、反推 50°/s、可调项（ThrottleResponse/BrakeDeflectionSpeed/rotator maxSpeed/TurningRate）都在 XML 属性，取零件档案现值算权限。
6. **时间源**：FT 侧 dt=`Time.deltaTime`（缩放）；IC 每物理帧 order −100 刷新；暂停时 IC 冻结、setter 面板不冻结（1.5）。
7. **动画类件是"位置指令+行程时间"**（Animator Duration、翼 0.3 s 过渡）——高增益律配这类执行器会自激（11.5 Hz 铰链共振史的另一半解释：执行器相位滞后真实存在）。

## 五、与既有法典的订正/挂账

- 维持：min/max=乘数、`==` 非法、1e9 非法、False→−1、rate=0 冻结、前向引用全灭、轴名不可被 setter 覆写、腿 IC 量程 [−1,0]——**全部获得源码正身**（上面行号）。
- ⚠ 新挂账 A：setter `activator` 源码上有门控（空才恒真）vs 实测"恒真"未合拢 → 需一个两值自证局（`activator="Time>30"` + Label 读数）。
- ⚠ 新挂账 B：`LegacyFlaps` 改名逻辑可能影响 `Flaps` 轴语义（搬 TESTfighter 的 Flaps 武装信号前先 dump 盘上 XML 实际写法）。
- ⚠ 新挂账 C：`round` 舍入模式未证（Unity 实现）；`e=0` 引擎 bug 已证（1.6）。
- 未探面：RCN 无零件级输入（2.11，要每喷嘴独立控制=换路）；Gun 无限弹（2.12，`ammo()` 读的是 WeaponSystem 侧弹药账，SC-2 若引用过"机炮备弹消耗"需重核）；Gauge 可绑 setter 变量（2.14，座舱可视化新通道，免 Label）；~~FlightComputer-1 未测~~ **已结案**=Cockpit+FloatingPart 的锚件，无自身逻辑（2.14 末条）。
