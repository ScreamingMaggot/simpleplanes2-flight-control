--[[ ==========================================================================
  FT 面板镜像运行时（**自动生成，请勿手改** —— 由 analysis/scripts/ft_mirror_gen.py 产出）

  用途：面板 setter 由游戏表达式引擎求值，**从不写进 Player.log**；CraftProxy 无变量袋，
        Lua 读不到。Label 是唯一窗口 ⇒ 只能人眼读数 ⇒ 样本离散易误判（用户 2026-09-27 点破）。
        本文件把面板**同一条式子**用 Lua 复算，把内部量按 APPR 行打进日志 ⇒ 全自动、每帧、可回放。

  语义忠实度（照 platform-facts §1 源码定义，逐条对齐）：
        sum(x)      = value += x*dt
        rate(x)     = (x − last)/dt            （首帧 0）
        smooth(x,t) = MoveTowards(last, x, t*dt)（首帧 = x）
        PID(T,C,p,i,d) = p·e + i·Σe·dt + d·(C_last−C)/dt，e = T−C
  三角函数按**度**（FT 约定），atan2(y,x) 出参为度。

  ⚠ 已知偏差（**读数据时必须知道**）：
    1. 有状态量（sum/smooth/rate）从**本镜像启用那一刻**起算；面板的状态可能更早建立
       ⇒ 头几秒内两者可能不同。看数据时以稳态段为准，或保证"开镜像后重开一局"。
    2. dt 用 craft.Time 差分（同 telemetry-addon 既有做法）；实验/暂停会给出异常 dt，已钳。
    3. 本镜像**只读不写轴**，绝不参与控制（与 FT_ONLY 纪律一致）。
========================================================================== ]]

local M = {}          -- 镜像状态表（每个 rate/sum/smooth 一格）
local V = {}          -- 面板 setter 值快照（按面板顺序求值后落表）
local S = {}          -- FT 内置量快照（每帧从 craft 代理填）
local _prev = {}      -- 上一帧的内置量（给 rate 用）
local _init = false   -- 首帧标志（rate 首帧 0、smooth 首帧=x）

-- ── FT 语义 shim ─────────────────────────────────────────────────────────
local function _rate(key, x, dt)
  local last = M[key]
  M[key] = x
  if last == nil then return 0 end
  if dt <= 0 then return 0 end
  return (x - last) / dt
end

local function _sum(key, x, dt)
  M[key] = (M[key] or 0) + x * dt
  return M[key]
end

local function _smooth(key, x, t, dt)
  local last = M[key]
  if last == nil then M[key] = x; return x end
  local mx = t * dt
  local d = x - last
  if d > mx then d = mx elseif d < -mx then d = -mx end
  M[key] = last + d
  return M[key]
end

local function _pid(key, T, C, p, i, d, dt)
  local st = M[key]
  if st == nil then st = {s = 0, last = C}; M[key] = st end
  local e = T - C
  st.s = st.s + e * dt
  local dd = 0
  if dt > 0 then dd = (C - st.last) / dt end
  st.last = C
  return p * e + i * st.s + d * dd
end

-- 三角（度）
local function _rad(x) return x * math.pi / 180 end
local function _deg(x) return x * 180 / math.pi end
local function _wrap180(a) return (a + 180) % 360 - 180 end

--[[ ★安全取值（2026-09-27 血的教训，见下方长注）：
     CraftProxy/CraftControlsProxy 是 MoonSharp 的 **userdata**，Lua 里访问不存在的字段
     会**抛错**（不是返回 nil）：`cannot access field VTOL of userdata<...CraftControlsProxy>`。
     抛在 update() 里 ⇒ **整个 update() 中断** ⇒ 连 TEL 都不再落盘。

     实测记录：`ctl.VTOL` 就是这样的字段 ⇒ 镜像每帧抛错、把用户仅有的一条遥测流也一起弄瞎
     （platform-facts §30 早写过"Lua 代理可读面有限"，我没逐个实测就裸读，付了一局架次）。

     ⇒ 铁律：**凡从代理取值一律走 _g()**（pcall 包裹 + 失败落默认）。
     这道兜底不是"以防万一"，而是必需品：代理字段可读性是**逐字段**的，且不同游戏版本会变。
]]
local function _g(obj, key, dflt)
  local ok, v = pcall(function() return obj[key] end)
  if not ok or v == nil then return dflt end
  if type(v) == "number" then return v end
  if type(v) == "boolean" then return v and 1 or 0 end
  return dflt
end

--[[ ★★布尔→数值强制转换（2026-09-27 第四次架次的事故根因，面板里 33 处）：
     FT 里 `clamp01(MU12 > 0.5)` 合法——比较出 bool，函数按 §23 的 true→1/false→−1 收下。
     Lua **没有**隐式转换：`math.min(1, true)` 直接抛
         bad argument #2 to 'min' (number expected, got boolean)
     异常从 _ftmirror.step() 抛出 ⇒ 整个 APPR 停摆（所幸 pcall 围栏保住了 TEL）。

     ⇒ 翻译器给**每个数值函数的实参**都套上 _n()。这一层是必需的，不是防御性冗余：
     面板里"布尔喂进数值函数"共 33 处、涉及 16 个 setter（clamp01(min/max/abs 系列）。
]]
local function _n(x)
  if type(x) == "number" then return x end
  if type(x) == "boolean" then return x and 1 or 0 end
  return 0                     -- nil/其它 ⇒ 0（与 FT 的 false→数 取 0/1 指示语义一致）
end

--[[ 由生成器注入：S.xxx 取值源与 V.xxx 求值式（见 ft_mirror_gen.py 输出）]]
__MIRROR_BODY__

--[[ 每帧调用一次：填内置量 → 按面板顺序求值 → 返回 V 表（供日志取用） ]]
function M.step()
  local now = _g(craft, "Time", 0)
  local dt = _prev.t and (now - _prev.t) or 0
  _prev.t = now
  if dt <= 0 or dt > 0.5 then dt = 0.05 end     -- 暂停/实验跳变钳位（同 telemetry-addon 纪律）
  --[[ ★★V 表预置为 0（2026-09-27 第五架次事故）：
       FT 引擎里每个 setter 的初值是 **0**（未赋值也能参与算术）；
       镜像的 V 是普通空表 ⇒ 首帧读到自己就是 **nil**，nil 做算术直接抛
           attempt to perform arithmetic on a nil value
       受害的是**自参照** setter（`SLK`、`cmdTheF_I` 的退绕支 `0 - X*1.5`）。
       这里按 FT 语义统一预置 0（而不是给那两条单独打补丁）——
       与 §37"镜像须与面板同初值"一致，也让任何未来的自参照写法天然安全。
  ]]
  for k in pairs(V) do V[k] = 0 end
  for _, k in ipairs(__VKEYS__) do V[k] = 0 end
  S.dt = dt
  S.Time = now
  local c = craft
  local ctl = _g(craft, "Controls", nil)
  -- 机体量：全部经 _g（同一类 userdata，未实测过的名字一律不裸读）
  S.Altitude      = _g(c, "Altitude", 0)
  S.AltitudeAgl   = _g(c, "AltitudeAgl", 0)
  S.AngleOfAttack = _g(c, "AngleOfAttack", 0)
  S.AngleOfSlip   = _g(c, "AngleOfSlip", 0)
  S.Fuel          = _g(c, "Fuel", 0)
  S.GForce        = _g(c, "GForce", 0)
  S.GS            = _g(c, "GS", 0)
  S.Heading       = _g(c, "Heading", 0)
  S.IAS           = _g(c, "IAS", 0)
  S.Latitude      = _g(c, "Latitude", 0)
  S.Longitude     = _g(c, "Longitude", 0)
  S.PitchAngle    = _g(c, "PitchAngle", 0)
  S.PitchRate     = _g(c, "PitchRate", 0)
  S.RollAngle     = _g(c, "RollAngle", 0)
  S.RollRate      = _g(c, "RollRate", 0)
  S.TAS           = _g(c, "TAS", 0)
  S.VerticalG     = _g(c, "VerticalG", 0)
  S.YawRate       = _g(c, "YawRate", 0)
  -- 控制轴（**飞行员轴**）。可读性**逐字段不同**、且未全测 ⇒ 一律 _g 兜底。
  --   已实测可读：LandingGearDown（§30）、Throttle/Trim/Pitch/Roll/Yaw（TEL 行在用）。
  --   实测**不可读**：VTOL（本轮，报错原文见文件头）。
  S.Pitch        = _g(ctl, "Pitch", 0)
  S.Roll         = _g(ctl, "Roll", 0)
  S.Yaw          = _g(ctl, "Yaw", 0)
  S.Throttle     = _g(ctl, "Throttle", 0)
  S.Trim         = _g(ctl, "Trim", 0)
  S.Brake        = _g(ctl, "Brake", 0)
  S.VTOL         = _g(ctl, "VTOL", 0)          -- ★不可读 ⇒ 恒 0（真值未知，勿当真相）
  S.Flaps        = _g(ctl, "Flaps", 0)
  S.LandingGear  = _g(ctl, "LandingGear", 0)
  S.GearDown     = _g(ctl, "LandingGearDown", 0)
  -- Activate1..8：**面板上下文读不到**（platform-facts §28/29），镜像按同规则置 0
  --   ⇒ 镜像里凡用 ActivateN 的量（SLK 的进7门）与真面板**必然不同**，读 APPR 行时要记住。
  for i = 1, 8 do S["Activate" .. i] = 0 end
  __MIRROR_EVAL__
  return V
end

return M
