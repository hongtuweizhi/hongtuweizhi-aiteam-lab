---
name: battle
description: 斗蛐蛐实验台——aiteam-frame 固定流程 vs 自由集群（vs 共享黑板）的对照实验工具。触发场景：跑边界实验、对比 agent 编排方式、查边界图/战报、给新任务做形状画像。
---

# 斗蛐蛐实验台（aiteam-frame × REALM-Bench）

你在 aiteam 斗蛐蛐实验工作区。实验室根目录：`D:\aiteam-lab`，评测仓库：`D:\aiteam-lab\repos\REALM-Bench`（Python venv 在 `venv/`），斗蛐蛐桥：`D:\aiteam-lab\bridge\aiteam_battle.ts`。

## 核心概念

- **条件**：`aiteam-fixed`（论文式固定流程，notebook 手写角色链）vs `aiteam-free`（自由集群，lead 自主编排）vs `aiteam-free-shared`（自由集群 + 共享黑板，课题 4）。全部经桥跑 aiteam-frame。
- **任务**：P1–P10（REALM-Bench 规划）、P11（JSSP，crew 来自 J1）、T3（钉死实例 JSSP，**客观判分**：t3_checker.py 穷举精确最优 makespan=9）、T4（交接保真探针，5 条机器可核验约束过 4 次交接，**判分靠约束存活率**：probe_handoff.py）。
- **铁律**：判分不信任自报（t3_checker / probe_handoff 机器核验）；模型口径要打标签（opencode v4.1-flash vs DS v4-pro）。

## 常用命令

```bash
# 跑战斗（venv 在 REALM-Bench 下；先 cd）
cd /d/aiteam-lab/repos/REALM-Bench
export TMP=/d/aiteam-lab/tmp TEMP=/d/aiteam-lab/tmp TMPDIR=/d/aiteam-lab/tmp
./venv/Scripts/python.exe run_evaluation.py --frameworks aiteam-fixed,aiteam-free --tasks P1 --runs 1 --timeout 1800 --no-viz --output-dir /d/aiteam-lab/realm-battle-<名字>

# 切 provider（环境变量）
AITEAM_AGENT_DIR='D:\aiteam-lab\agent'      AITEAM_MODEL='opencode-go/deepseek-v4.1-flash'   # opencode（订阅内，优先）
AITEAM_AGENT_DIR='D:\aiteam-lab\agent-ds'   AITEAM_MODEL='deepseek/deepseek-v4-pro'          # DS 官方（限流时用，空闲时段省一半）
AITEAM_RUNS_DIR='D:\aiteam-lab\runs-ds'     # DS 运行数据单独存放

# 战报聚合
/d/aiteam-lab/repos/REALM-Bench/venv/Scripts/python.exe /d/aiteam-lab/battle_report.py /d/aiteam-lab/realm-battle-<名字>
/d/aiteam-lab/repos/REALM-Bench/venv/Scripts/python.exe /d/aiteam-lab/variance_report.py <results目录>   # N>1 时用

# T3 客观判分（对任一份 result.json）
/d/aiteam-lab/repos/REALM-Bench/venv/Scripts/python.exe /d/aiteam-lab/t3_checker.py check <result.json>
# T4 交接保真（约束存活率 + fixed 逐跳曲线）
/d/aiteam-lab/repos/REALM-Bench/venv/Scripts/python.exe /d/aiteam-lab/probe_handoff.py <result.json>

# 边界画像（预测谁赢 → 战斗后回填 → 边界图）
/d/aiteam-lab/repos/REALM-Bench/venv/Scripts/python.exe /d/aiteam-lab/task_profile.py score <profile.json>
/d/aiteam-lab/repos/REALM-Bench/venv/Scripts/python.exe /d/aiteam-lab/task_profile.py map
```

## 省钱铁律（用户政策）

1. 能本地完成的不调 API（判分、聚合、画像全部本地）。
2. 真模型战斗优先 opencode-go（订阅配额，`agent/auth.json`）；被 GoUsageLimitError 限流时才用 DeepSeek 官方（`agent-ds/`，key 在 `agent/deepseek_key.txt`），且尽量排空闲时段（v4-pro 输出 ¥13.5/M vs 高峰 ¥27/M）。
3. maxTokens 教训：推理模型给 32768，否则静默空产出。
4. 产出与结论一律写进 `D:\aiteam-lab\REPORT.md`；边界图在 `D:\aiteam-lab\boundary_map.json`。

## 已知结论（截至 2026-10-02，详见 REPORT.md）

- 纯规划任务（P1-P10、P11）：free 全胜且省 5-7 倍成本，lead 自适应单干/加分身；fixed 丢分于场景漂移与交接丢约束。
- 盲评（deepseek-chat 裁判）确认机械分方向：fixed 2.9 vs free 7.0。
- 自报达成不可信：机械判分给 fixed 的 100% 有 5 个被盲评/客观判分证伪。
- 边界未找到：free 在"理论该 fixed 赢"的任务上也赢——下一步靠 T3（客观 makespan）与 T4（交接存活率）找转折点。
