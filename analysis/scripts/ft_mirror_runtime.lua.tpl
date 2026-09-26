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

--[[ 由生成器注入：S.xxx 取值源与 V.xxx 求值式（见 ft_mirror_gen.py 输出）]]
__MIRROR_BODY__

--[[ 每帧调用一次：填内置量 → 按面板顺序求值 → 返回 V 表（供日志取用） ]]
function M.step()
  local now = craft.Time
  local dt = _prev.t and (now - _prev.t) or 0
  _prev.t = now
  if dt <= 0 or dt > 0.5 then dt = 0.05 end     -- 暂停/实验跳变钳位（同 telemetry-addon 纪律）
  S.dt = dt
  S.Time = now
  local c = craft
  local ctl = craft.Controls
  S.Altitude = c.Altitude
  S.AltitudeAgl = c.AltitudeAgl
  S.AngleOfAttack = c.AngleOfAttack
  S.AngleOfSlip = c.AngleOfSlip
  S.Fuel = c.Fuel
  S.GForce = c.GForce
  S.GS = c.GS
  S.Heading = c.Heading
  S.IAS = c.IAS
  S.Latitude = c.Latitude
  S.Longitude = c.Longitude
  S.PitchAngle = c.PitchAngle
  S.PitchRate = c.PitchRate
  S.RollAngle = c.RollAngle
  S.RollRate = c.RollRate
  S.TAS = c.TAS
  S.VerticalG = c.VerticalG
  S.YawRate = c.YawRate
  -- 控制轴（**飞行员轴**，与 FT 零件上下文同名）
  S.Pitch = ctl.Pitch
  S.Roll = ctl.Roll
  S.Yaw = ctl.Yaw
  S.Throttle = ctl.Throttle
  S.Trim = ctl.Trim
  S.Brake = ctl.Brake
  S.VTOL = ctl.VTOL or 0
  S.Flaps = ctl.Flaps or 0
  S.LandingGear = ctl.LandingGear or 0
  S.GearDown = ctl.LandingGearDown and 1 or 0
  -- Activate1..8：**面板上下文读不到**（platform-facts §28/29），镜像按同规则置 0
  --   ⇒ 镜像里凡用 ActivateN 的量（SLK 的进7门）与真面板**必然不同**，读 APPR 行时要记住。
  --   本镜像的处置：从零件层可读物无通道 ⇒ 用 Flaps 代主电（与 SC-5 定案一致），另打 ACT 列。
  local fl = 0
  pcall(function() fl = ctl.Flaps or 0 end)
  for i = 1, 8 do S["Activate" .. i] = 0 end
  __MIRROR_EVAL__
  return V
end

return M
