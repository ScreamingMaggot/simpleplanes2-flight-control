# SimplePlanes 2 飞行控制实验项目

以游戏 SimplePlanes 2（Unity，物理仿真 + 可编写机载控制律）为自由飞行试验场，完成的一组"建模 → 辨识 → 控制律设计 → 试飞验证"闭环实验。全部结论以机载遥测数据裁决，迭代账本与验证报告随仓库发布。

## 课题与结论

| 课题 | 内容 | 定版 | 报告 |
|---|---|---|---|
| SC-1 | 定高自动驾驶仪（纵向通道：姿态内环 + 高度/速度外环、坡度补偿） | v5.1 封版 | `analysis/report-sc3.pdf` 前史见账本 |
| SC-2 | 高性能验证机自主空战导引（截获—跟踪—穿越—机炮杀伤链，比例导引 + 挂点射法） | 主链路验收通过 | `analysis/report-sc2.pdf` |
| SC-3 / 3b | 远距机场自主选配、程序进场与切线消高、全自主着陆（含复飞重入） | v4.68 收口 | `analysis/report-sc3b.pdf` |

## 控制架构

分层：快回路（舵面内环、导引律）运行于机载表达式引擎 Funky Trees（每物理拍位置式求值）；慢回路（能量管理、模式仲裁、遥测记录）由 MFD Lua 脚本以真时间步长实现（`analysis/mfd-lua/telemetry-addon.lua`）。目标信息经表达式侧只读变量获取。补丁工具 `analysis/mfd-lua/build_patch.py`：Lua 语法门禁 → 注入 resources.assets（需冷启动加载）。

## 观测与评估方法

- 机载多流遥测（TEL 12 Hz / POS / APP / LAND），逐流实例身份列（cid）分离同场多机；
- 以几何距离残差唯一配对"本机—所追目标"，防止归因张冠李戴；
- 离线 1:1 重建全部制导量（指令—执行—收敛三环分别可裁决）；
- 抖振诊断规程：≥50 Hz 采样（低频采样会把振荡折叠藏身）；采样极限环判据：振峰锁步跟随帧率。

## 仓库结构

```
crafts/        课题机体 XML（E1 活塞验证机 TESTaircraft、喷气 TESTfighter；
               FT 舵面律与参数面板内嵌于机体文件，复现必需）
analysis/
  mfd-lua/     机载 Lua 律与补丁工具（build_patch.py）
  scripts/     遥测解析 parse_telemetry.py、机体建模 craft_model.py、
               3D 航迹出图 plot_track3d.py、交互查看器 make_track_html.py、
               辨识 fighter_id.py / fighter_stats.py
  matlab/      闭环辨识（sp_id3.m）
  *.pdf/*.tex  三份课题报告源文件与成品
designs/       迭代账本（SC-3b-approach-planning.md：逐版定罪与修复记录）
```

## 复现说明

原始遥测日志（约 90 MB）与游戏反编译产物不随仓库分发；报告中的统计与图表可由 `analysis/scripts/` 对自采日志重跑复现。`make_track_html.py` 生成的 3D 航迹查看器为自包含 HTML（内嵌 plotly.js，离线可用）。

游戏与引擎版权归 Jundroo 所有；本仓库仅含自研脚本、数据与文档，不含任何游戏二进制。
