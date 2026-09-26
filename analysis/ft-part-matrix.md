# FT 零件可控性矩阵（从头研究 FT 飞控的知识底座）

> **2026-09-26 升级指针**：本篇保留"实测归因史+操作纪律"；**全量零件输入/输出范围与精度的源码档案已建于同目录 `parts-io-matrix.md`**（178 零件型×93 修饰符逐类实读，含 FT 引擎数值语义：`Jundroo.Common.dll` 词法/优先级/float 语义、`e=0` bug、无 epsilon 判等、60 条输出变量表）。写新律先查后者。

来源两类，**逐格标注**：`[文档]`=`analysis/FunkyTrees_文档全集.txt`（§2.3.4 部件变量、§InputController、§5/§6 教程）；`[实测]`=本项目架次证据（`designs/SC-5-ft-autoland.md` 验尸账 appNN、`analysis/platform-facts.md` §23~§33）。
未标 = **未知，须用"一次一通道 + 自证实验"补**，不许类推。
强例解剖与可复用原语见同目录 `ft-droplet-study.md`（用户提供的 Droplet.splane，纯 FT 全权限飞控）。

## 0. 两条全局规则（先记住，否则必踩）

- **`min`/`max` 是两条独立乘数，不是"把 `[-1,1]` 映射到 `[min,max]` 端点"** `[反编译实读，2026-09-25]`：
  `InputControllerScript.UpdateValue()` 原文 —— `if (num < 0) Value = (0-num) * MinValue; else Value = num * MaxValue;`
  ⇒ **负输入乘 `MinValue`、非负输入乘 `MaxValue`**。所以 `min=0 max=1`（标准型，如 `AirBrake`/发动机）下
  输入 1 = 满量、输入 −1 = 0；而 `min=1 max=0` 这类**反向接法**下输入 −1 → Value 1、输入 0/1 → Value 0。
  ⚠ 但**先问"这个 Value 被谁消费"**再谈极性与量程：同一对 `min=1 max=0` 在腿上是"伸出量（−1=放）"、在旧 `Wheel-*` 族上却是"转向角"。
- **每个 IC 的 Value 含义必须"按 partType 找对脚本类"再读源码**（权威表=`analysis/parts-io-matrix.md`）：
  本机腿 `GearLeg-1` 的 IC#0 是 **"Extension Input"**，被 `AnimatorScript` 消费（`Clamp01(Value)`→`Percent`=伸出量）⇒ **可达**；
  轮 `JWheelAssembly-1` 的 IC#1（名 "Brake"）被 `BaseWheelScript.UpdateWheel()` 消费 ⇒ **可达**。
  我 v1.2~v1.7 与 v2.5~v2.6 反复误判，都是把 **`LandingGearScript`（`Wheel-1/2/3` 自带轮子起落架族）** 的
  `_wc.SteerAngle = Value` / `AnimateLandingGear(Controls.LandingGearDown)` / `_wc.BrakeInput = Controls.Brake`
  安到本机零件头上 ⇒ **同名脚本 ≠ 同族零件**。控制轴本身仍不可被零件表达式或面板同名 setter 覆写（探针 A 成立），
  但那**不等于"这件事不可做"**——只要动作有个消费 Value 的零件承接，律就能自动。
- **一条表达式里只允许一个三元、绝不嵌套** `[app89 判决]`：`(A) ? ((B) ? x : y) : z` 报
  `Unary operator not supported: Equal` ⇒ **整条式失能**。要"按模式选指令 + 按门放行"就写**加权混合**
  `G*律 + (1-G)*原生`（`G=(Activate8 ? boot : 0)`），或把内层三元挪成独立 setter。同级并排的多个三元（`min(A?x:y, B?p:q)`）合法。
- **表达式失能的后果是"退回该件原生 defaultInput"，不是恒 0（强证据，待下次复飞结案）**：app89 副翼/升降舵式失能期间他照常操纵；
  SC-5 也记过"表达式失能后坡度仍到 93°"。⇒ 这类故障**不会让飞机变砖，只会让律静默失效**——
  所以"感觉没效果"必须去 grep `Player.log`（`Invalid expression on part N` 只进日志），绝不能靠飞行手感反推。
- **发动机=可达的油门，螺旋桨在 Auto 恒桨下其 `propPitch` IC 被禁用** `[反编译实读]`：
  `BladedEngineScript.SetupInput`：`Name=="throttle"` → `base.ThrottleInput = inputController`（**可达**）；
  `Name=="propPitch"`（`defaultInput="VTOL"`）→ `if (PitchControlType != Manual) _bladePitchInput.Disabled = true;`
  ⇒ 本机 `pitchControlType="Auto"` ⇒ **桨那条 IC 写了没用** ⇒ SC-5"推力阀门在螺旋桨 IC"对 Auto 桨的机体不成立，
  而且**"VTOL 旋钮会不会改推力"这个疑点也随之消掉**（不会）。
- **观测铁律** `[实测 §30]`：HUD 上的油门百分比、遥测 `thr/pit/rol/yaw/flp` 列全都绑**手柄轴**，零件输入值不可见 ⇒ 任何诊断只能挂在**机体响应**（IAS/AGL/坡度/油耗）上。
  ⇒ **推论（2026-09-25 第三次中招，用户原话："我以为没用是因为我游戏 UI 上的显示 throttle 量没变"）**：
  HUD 那个油门表显示的是**你的杆位**，而 FT 律写在它的**下游**（`_controller.Value`）⇒ **律改得再狠，HUD 也纹丝不动**。
  同款误判史：SC-5 app55 曾把"遥测 thr 恒 0.40"当成"ARM 锁死签名"（其实那正是飞行员轴）。
  **唯一可信的零件侧读数 = Label 的 `designText`（它能读面板量）⇒ 能量环必须自带 `th`/`pv` 双显示**，
  否则"没看见变化"和"没工作"永远分不开。

## 1. 矩阵

| 零件（XML ID） | 控制什么 | 表达式可控性 | 证据 |
|---|---|---|---|
| 控制面族：`ControlSurface-Flap-1`、`JWing-1`、`JFuselage-1`（副翼/升降舵/方向舵挂在它们上） | 舵面偏度（`Roll`/`Trim`/`Yaw` 轴 + 叠加项） | **可用**。`clamp(Roll + (ACT ? … : 0), -1, 1)` 形式实飞闭环 | `[实测 app72/76]` 全松杆 110 s、\|LT\|<1 m 保持 5.7 km、落跑道正中 |
| 星型螺旋桨发动机 `JPropEngineRadial`（IC 无名，`min=-1 max=1`） | **油门** | **可达 = 本机唯一的推力权限** `[反编译实读]`：`JEngineScript` 取该件**第一个 IC**（不靠 name）：`_controller = GetModifier<InputControllerScript>()` → `InputThrottle = _controller.Value` → `EngineThrottle = min(StepTowards(...), MaxValue)`。SC-5"喂 1 只看到油耗不见推力"的旧判语**作废**（当时认定的"桨阀门"其实是下面这条被 bypass 的 IC）|
| 螺旋桨总成 `PropellerAssembly-1` | 两条 IC：#0 `BladeAngle`、#1 `ReverseThrust` | **#0 不可达**：`GetPitchInput()` 里 `switch (PitchControlType)` **只有 `case Manual` 才读 `_pitchInput.Value`**，本机 `pitchControlType="Auto"` ⇒ 恒桨由调速器接管，写它没效果（`SetSectionVisible(_pitchInput, Data.IsManual)` 同证）。**#1 可达 = 自动反推**：`if (... || PitchControlType != Auto || ReversePitch <= 0) return 0;` ⇒ **反推恰恰只在 Auto 下被消费**，本机 `reversePitch="12"`（12° 反推桨距）而机体把这条 IC 接成 `input="Disabled"`（=白白关着）。⇒ **纯 FT 想做"自动停住"只能走反推**（轮刹不可达、低速时减速板无效）|
| 螺旋桨叶片 `Engine-Prop-1/2/3/4/5`（Blade T3000/T2000/T1000、Propeller Engine） | 推力实际产生件；有 `RPM`+`Thrust` 输出 | 未测（本机 IC 不在此件上） | `[文档 §2.3.4]` 输出清单 |
| 起落架腿 `GearLeg-1`（IC#0 = **Extension Input**，`min="1" max="0"`，`<Animator.State animationDuration="4">`） | **腿的伸出量 0(收)~1(放)** | ★**可达（2026-09-26 凌晨，用户实测 + 读对类终审）**：链路 = IC#0 Value → `AnimatorScript.InputTargetPercent = Mathf.Clamp01(_inputController.Value)` → `Percent = Mathf.MoveTowards(Percent, TargetPercent, dt/Duration)` → `GearLegScript`：`[VariableOutput("Extension")] Extension => AnimatorData.Script.Percent`，且 `SuppressWheelPhysics = CanRetract && Percent < Data.MinExtensionForWheelPhysics`（默认 **0.4**）⇒ **伸出量真由表达式驱动，且收到 0.4 以下轮子连物理都没了（是真收放，不是动画）**。`CanRetract`=关键帧 ≥2（本机 22 腿 4 帧、25/32 腿 2 帧 ⇒ 都满足）|
| 同上·**量程与极性终审（v1.2~v1.7 冤案的根）** | — | 该 IC 是 `min=1 max=0`，而 `UpdateValue()` 是 `num<0 ? (0-num)*MinValue : num*MaxValue` ⇒ **Value = \|num\|（仅负输入有效），任何 ≥0 的输入都等于 Value 0 = 全收**。⇒ 可用量程 = **输入 [−1, 0] → 伸出 [0, 1]**（−1 全放、−0.5 半程、0 与 +1 同为全收）。**这就是为什么我 v1.4~v1.7 试的 `? 1` 与 `? 0` 是同一个实验做两遍**。另订正：我上一版"起落架收放只读控制轴、写表达式=打舵"来自读错类——`LandingGearScript`（`Wheel-1/2/3` 那族**自带轮子**的收放起落架）才有 `_wc.SteerAngle`/`AnimateLandingGear(Controls.LandingGearDown)`；本机腿是 `GearLegScript`+`AnimatorScript`，**根本没有那条轴依赖** |
| 官方机体的"旋转器拼腿"（`Competitor` part146 `clamp01(LandingGear)` + `JointRotator.State range="90"`；370 条旋转器 IC 读 `LandingGear`/`GearDown`） | 自定义几何的腿 | **另一条路，不是唯一的路**：那批机体（`Competitor`/`Sedona`/`Vertigo IV`/`Stormvark`…）本来就没有 `GearLeg-1`，它们用旋转器 + 独立轮件（`Wheel-Resizable-1`）自造腿形；**原厂腿能直接被表达式驱动，本机不必动手术**。（我曾据此判"原厂腿不可达⇒纯 FT 做不了自动起落架"，两处都错：错在把 `LandingGearScript` 安到 `GearLegScript` 头上、又把官方自造腿当成必要条件。作废副本脚本 `scripts/ft_ta2_rotgear.py` 仅留作官方结构标本。） |
| 同上·旧账（**三版结论全部作废**，只留作误读样本） | — | ~~§32 表达式一律无效~~（app72~75）／~~"轮子起效了⇒零件 IC 吃表达式、§32 推翻"~~（v1.3）／~~`delivered = 1−(input+1)/2` 端点映射定极性~~（v1.4~v1.7）——**同一现象的四种猜法，全错**；真机制见上一行。**教训：拿观测反推量程 = 死路，读那 40 行源码只花 3 分钟。** |
| 仪表 `Gauge-1` / ADI `Gauge-ADI-1` | 指针/画面 | 未测（预期同属动画类零件） | — |
| **系统轴名解析** | 面板同名 setter 能否覆写 `Brake`/`LandingGear` 等轴名 | **不能**（★2026-09-25 深夜，用户提案实测）：面板**最后**追加 `<Setter variable="Brake" …>` + 零件 IC 还原裸名 ⇒ 用户在地面停 150 s、期间一次 7 s 满油门推进，**无任何周期脉动**；日志**零 `Variable error`** ⇒ 同名 setter 被**静默接受但惰性**，面板也没死。⇒ **零件 IC 的 `input="Brake"` 恒解析到系统轴**。**订正（原判"所以只能走零件 IC 表达式"不完整）**：能否用零件 IC，还取决于该件脚本是否消费 IC 的 Value——舵面/发动机/减速板/**原厂腿件伸出量**/**轮刹**都消费（可达）。**我在此处反复翻车的形式错误 = 拿"另一个零件族里同名的脚本"当本件的消费者**（`LandingGearScript` 属 `Wheel-1/2/3` 自带轮子的起落架族，既不是本机的 `GearLegScript`，也不是本机的 `BaseWheelScript`）。**但这不等于"这件事不可做"**：官方机体把这两件事搬到**执行器零件**上完成（腿=旋转器、前轮转向/地面差动=旋转器读 `Brake`/`Aileron` 表达式）。⇒ **"轴不可覆写"只约束"改系统轴的值"；只要动作有个消费 Value 的零件承接，律就能自动。** **先读部件脚本，再谈"这条轴能不能自动"。** | `[实测 SC-6 v1.3 探针 A + 反编译 + 机库普查]` |
| **文本标签 `Label-1`** | 座舱/HUD 文字与颜色 | **可读 setter 面板变量**：`designText` 里 `{表达式}` 被 FT 求值，示例用 `{alpha1}`（setter 名）拼颜色、`{rate(Fuel)=0.0&GS=0.0 ? "○" : ""}` 做条件字符 | `[Droplet 例证]` ft-droplet-study.md 原语#8 ⇒ **这就是律的内部量观测通道** |
| 喷气发动机 `Engine-Jet-1` | 推力份额 | **可用**：Droplet 把 9 台的 IC 写成 `±relZ ± aRoll …` 混控，`min=0 max=0.1` 做量程缩放 | `[Droplet 例证]`；与星型活塞机对照 ⇒ **阀门件随推进器类型变**，无通用"油门通道" |
| 旋转器 `JointRotator-1` / 铰链 `HingeRotator-1` | 角度（`min/max`=角度量程） | **可用**：文档 §4 座舱盖、§6 自定义起落架都是拿旋转器当执行器（`Activate8`、`GearDown ? 0 : 1`） | `[文档]` + `[实测 §29 本机尾舵灯：常数与 setter 值都能驱动 IC 型零件]` |
| 飞行计算机 `FlightComputer-1` | 逻辑/输出 | 未测 | `[文档 §2.3.4 有变量清单]` |
| 刹车：轮 `JWheelAssembly-1`(**IC#1 = 名为 "Brake" 的那条**) / 减速板 `AirBrake-1`(IC#0) | 轮刹 vs 空气阻力 | ★**轮刹可达（2026-09-26 凌晨用户实测 + `BaseWheelScript` 终审订正）**：`_brakeInput = GetInputController("Brake")` → `float value = _brakeInput.Value; _wheelController.brakeInput = Clamp01(value + (ParkingBrake?1:0)); if (value > 0) BrakeTorque = value * (ParkingBrake?5:1) * _weightOnWheel * WheelRadius * BrakeTorqueMultiplier * 2; else BrakeTorque = 0;` ⇒ **量程 = 0(free)~1(抱死)，且只有正半轴有效**（该 IC `min=-1 max=1` ⇒ 负输入=Value 负 ⇒ 力矩 0）；**`∝ _weightOnWheel` ⇒ 空中踩着自动无力，物理自带接地门**（滑跑刹车不必另设判据）。我上一版"无人消费/直读 `Controls.Brake`"又是读错类（那句 `_wc.BrakeInput = aircraft.Controls.Brake * _functionalHealth` 出自 `LandingGearScript`=`Wheel-1/2/3` 族），作废。IC **序号 1 不是 0**（0 是 "Turn"=转向，写错序号=给轮子打舵，这条守卫仍然成立）。**减速板同样可达**（坠海局实证：`? 1` 全开 12 s 吃掉 20 m/s）⇒ 本机 `AirBrake` 是 `min=0 max=1` 标准型、输入 1 = 全开、**权限极大必须限幅**。 |
| 座舱 `Cockpit-*` | 姿态/位置输出（`Heading/PitchAngle/PosX…`） | 输出侧可用（部件变量须在部件变量菜单里启用并命名） | `[文档 §2.3.4]` |

## 2. 部件输出（做"看得见"的仪表时用这个，别猜）

`[文档 §2.3.4]` 用法：**在该部件的"部件变量"菜单里启用对应输出并命名**，之后其它表达式可引用该名字。关键条目：

- 发动机（星型/V/平置）：`RPM`、`OutputTorque` —— **没有 Thrust**；
- 螺旋桨叶片 `Engine-Prop-*`：`RPM`、**`Thrust`（牛）**；
- 起落架腿：`Suspension`、`Extension`（→ 可作"轮子真放下了"的**可观测证据**，比看动画可靠）；
- 轮：`ForwardSlip`/`SidewaysSlip`/`Offroad`/`RPM`（→ 接地/打滑/滑跑判据）；
- 相机：`IsActive`/`LookPitch`/`LookRoll`；旋转器：`CurrentAngle`（→ 舵面/桨距真实位置）。

**机库普查顺手捞到的内置量（官方机体表达式在用、我们的白名单里还没有，未实机验证）**：`WeightOnWheels_L` / `WeightOnWheels_R`（左右主轮承重，0~1，官方拿来作"离地/接地"门：`WeightOnWheels_L<0.51 ? …`）。这正是我们一直用 `AltitudeAgl<3 + IAS` 硬猜的 `airFly`/`gndIdle`/`revOn` 判据的**正品替换**；下一步在 TA2-RT 副本上验证它能否解析（编译失败会让整条表达式恒 0，务必配 Label 读数）。

## 3. 下一程的操作约束（SC-5 用十余架次换来的）

1. **一次只测一个通道**，一个架次只回答一个问题；
2. **实验必须自证**：把待验证的量做成"两值各喂满一段、物理上不可伪造"的形态（样板：`Time > 30 ? 1 : 0`），判据写在飞之前；
3. **先查本矩阵与文档/反编译，再动手**——`min/max 是映射`、`SP2 发动机与螺旋桨是两个部件`这两条文档早就写了，我读晚了才把能量环猜了十几版；
4. 载体用**最小干净机体**（1 发动机 + 1 螺旋桨总成 + 3 控制面 + 1 仪表），不复用带历史包袱的克隆体；
5. 改装机体的脚本必须带**结构锚替换**（按 `partType` 定位，绝不按被替换内容当指纹）+ **引用闸覆盖零件式**（v0.15 差点发出引用未定义 setter 的坏机体）+ 磁盘回读核对；
6. **跨机体搬信号前先跑 `analysis/scripts/dump_part_inputs.py`**（列全机 partType/id/每个 IC 的**序号**与现值）——本机零件清单是首要事实，不是可推断项；
7. **"不碰某个通道"必须写成"显式还原成裸轴名"**：只从 patch 列表里删掉它，上一次试验的式子会**原样赖在盘上**（SC-6 v1.2 真踩），静默且只在飞的时候暴露。
