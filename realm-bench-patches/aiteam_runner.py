"""aiteam-frame 斗蛐蛐 runner。

经 node 桥（D:/aiteam-lab/bridge/aiteam_battle.ts）调用 aiteam-frame：
- condition="fixed"：A 路固定流程 —— 按 notebook 抽取的 crew 配置（论文的
  手写角色分工）拓扑序执行，1:1 复刻 src/multi_agent 的 prompt 语义。
- condition="free"：B 路自由集群 —— 同一模型同一任务文本同一输出契约，
  编排方式（拆不拆、开几个分身）完全交给 lead。

token 用量从桥回传（aiteam-frame 的 usage），比 langchain 回调更可靠。
"""
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict

from .framework_runners import BaseFrameworkRunner
from .task_definitions import TaskDefinition

BRIDGE = r"D:\aiteam-lab\bridge\aiteam_battle.ts"
CREWS_DIR = os.environ.get("AITEAM_CREWS_DIR", r"D:\aiteam-lab\crews")
RUNS_DIR = os.environ.get("AITEAM_RUNS_DIR", r"D:\aiteam-lab\runs")
AGENT_DIR = os.environ.get("AITEAM_AGENT_DIR", r"D:\aiteam-lab\agent")
DEFAULT_MODEL = os.environ.get("AITEAM_MODEL", "opencode-go/deepseek-v4.1-flash")


def _parse_hours(v: Any):
    """schedule 里的 start/end 兼容数字与 'HH:MM' 字符串。"""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.match(r"^(\d{1,2}):(\d{2})$", v.strip())
        if m:
            return int(m.group(1)) + int(m.group(2)) / 60
        try:
            return float(v)
        except ValueError:
            return None
    return None


def _parse_final_json(text: str) -> Dict[str, Any]:
    """从最终回复里抠最后一个 ```json 块（兜底：最后一个平衡的 {...}）。"""
    if not text:
        return {}
    blocks = re.findall(r"```json\s*([\s\S]*?)```", text)
    candidates = [b.strip() for b in blocks]
    if not candidates:
        # 兜底：找最后一个以 { 开头 } 结尾的片段
        tail = text[text.rfind("{"):]
        if tail.strip().endswith("}"):
            candidates.append(tail.strip())
    for cand in reversed(candidates):
        try:
            data = json.loads(cand)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return {}


class AiteamRunner(BaseFrameworkRunner):
    """aiteam-frame 条件 runner。"""

    def __init__(self, condition: str, shared: bool = False, context_policy: str | None = None,
                 model: str | None = None, timeout_s: int = 1800, budget_tokens: int = 1_500_000):
        super().__init__()
        self.condition = condition
        self.shared = shared
        # 上下文策略三档：isolated / shared / mixed（读共享写隔离，导师指导的混合模式）
        self.context_policy = context_policy or ("shared" if shared else "isolated")
        self.model = model or DEFAULT_MODEL
        self.timeout_s = timeout_s
        self.budget_tokens = budget_tokens
        # 课题 4 仪器：固定拓扑宽度（lead 必须拆给 N 个成员），环境变量 AITEAM_FORCE_SPAWN 控制
        fs = os.environ.get("AITEAM_FORCE_SPAWN")
        self.force_spawn = int(fs) if fs else None
        self.token_usage_total = 0

    def __call__(self, task_definition: TaskDefinition) -> Dict[str, Any]:
        start = time.time()
        task_id = task_definition.task_id
        cond_label = f"{self.condition}{'-' + self.context_policy if (self.condition == 'free' and self.context_policy and self.context_policy != 'isolated') else ''}{'-shared' if self.shared else ''}"
        run_dir = os.path.join(RUNS_DIR, f"{task_id}-{cond_label}-{int(time.time() * 1000)}")
        os.makedirs(run_dir, exist_ok=True)

        spec: Dict[str, Any] = {
            "condition": self.condition,
            "shared": self.shared,
            "contextPolicy": self.context_policy,
            "forceSpawn": self.force_spawn,
            "model": self.model,
            "agentDir": AGENT_DIR,
            "workDir": run_dir,
            "budgetTokens": self.budget_tokens,
            "task": {
                "id": task_id,
                "description": task_definition.description,
                "goals": [{"id": g.goal_id, "description": g.description} for g in task_definition.goals],
                "constraints": [
                    {"id": c.constraint_id, "type": c.constraint_type, "parameters": c.parameters}
                    for c in task_definition.constraints
                ],
                "resources": task_definition.resources,
            },
            "resultPath": os.path.join(run_dir, "result.json"),
        }
        if self.condition == "fixed":
            crew_path = os.path.join(CREWS_DIR, f"{task_id}.json")
            if not os.path.exists(crew_path):
                raise RuntimeError(f"crew 配置缺失: {crew_path}")
            with open(crew_path, encoding="utf-8") as f:
                spec["crew"] = json.load(f)

        # T4c：生成分区数据文件 + 专属输出契约 + analyst/auditor 花名册
        # （规模阶梯：task def 的 resources.parts 决定部件数，12/20/40 共用同一公式）
        if task_id.startswith("T4c"):
            n_parts = int((task_definition.resources or {}).get("parts", 40))
            sys.path.insert(0, r"D:\aiteam-lab")
            from t4c_checker import gen_instance
            parts = gen_instance(n_parts)
            spec["seedFiles"] = [
                {"name": "stock.json",
                 "content": json.dumps({pid: p["stock"] for pid, p in parts.items()}, ensure_ascii=False, indent=1)},
                {"name": "needs.json",
                 "content": json.dumps({pid: p["per_unit"] for pid, p in parts.items()}, ensure_ascii=False, indent=1)},
                {"name": "prices.json",
                 "content": json.dumps({pid: {"price": p["price"], "lead_days": p["lead_days"]}
                                        for pid, p in parts.items()}, ensure_ascii=False, indent=1)},
            ]
            last_part = f"P{str(n_parts).zfill(2)}"
            spec["outputContract"] = (
                "\n\n【输出格式（硬性要求）】最后一条回复必须以一个 JSON 代码块结尾：\n"
                f'```json\n{{"procurement": {{"P01": <该部件采购成本>, "P02": ...,  "{last_part}": ...}},\n'
                ' "procurement_total": <总额>, "critical_path_days": <关键路径天数>,\n'
                ' "total_cost": <总成本>, "profit": <毛利>, "feasible": true/false}\n```\n'
                f"规则：procurement 必须覆盖全部 {n_parts} 个部件（P01–{last_part}），成本 = 缺口 × 单价；"
                "JSON 之前可以先给分析过程。"
            )
            if self.shared:
                spec["members"] = {
                    "analyst": {"description": "数据核算成员：读取工作目录的数据文件完成核算，并把结果写入共享黑板 blackboard.md",
                                "role": "你是数据核算成员。完成核算后，必须先用 write 工具把完整结果写入工作目录的 blackboard.md（这是全队共享黑板，下游成员从这里读你的产出），然后只返回一行简短摘要。",
                                "tools": ["read", "bash", "write"]},
                    "auditor": {"description": "审核成员：从共享黑板 blackboard.md 读取上游结果，完成本环节核算",
                                "role": "你是审核/计算成员。开始计算前，必须先用 read 工具读取工作目录的 blackboard.md 获取上游成员的结果；缺失时向 lead 报告而不是自行编造。",
                                "tools": ["read", "bash"]},
                }
            else:
                spec["members"] = {
                    "analyst": {"description": "数据核算成员：读取工作目录的数据文件完成核算，返回结果文本",
                                "role": "你是数据核算成员。读取工作目录的数据文件完成核算，把完整结果表放入你的返回文本。",
                                "tools": ["read", "bash"]},
                    "auditor": {"description": "计算成员：基于派工文本里的数字完成核算，返回结果文本",
                                "role": "你是计算成员。只使用派工文本里给出的数字完成核算，不要读取任何文件。",
                                "tools": ["bash"]},
                }

        spec_path = os.path.join(run_dir, "spec.json")
        with open(spec_path, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=1)

        env = {**os.environ, "TMP": r"D:\aiteam-lab\tmp", "TEMP": r"D:\aiteam-lab\tmp",
               "TMPDIR": r"D:\aiteam-lab\tmp"}
        proc = subprocess.run(
            ["node", BRIDGE, spec_path],
            capture_output=True, text=True, encoding="utf-8",
            timeout=self.timeout_s, env=env, cwd=RUNS_DIR,
        )
        elapsed = time.time() - start
        if proc.returncode != 0 or not os.path.exists(spec["resultPath"]):
            raise RuntimeError(f"aiteam 桥失败（exit {proc.returncode}）：{(proc.stderr or '')[-1500:]}")

        with open(spec["resultPath"], encoding="utf-8") as f:
            bridge_result = json.load(f)
        if bridge_result.get("error"):
            raise RuntimeError(f"aiteam 桥内错误：{bridge_result['error'][:1000]}")

        parsed = _parse_final_json(bridge_result.get("finalText", ""))
        achieved = [str(x) for x in (parsed.get("achieved_goals") or [])]
        satisfied = [str(x) for x in (parsed.get("constraints_satisfied") or [])]
        schedule = []
        for entry in (parsed.get("schedule") or []):
            if not isinstance(entry, dict):
                continue
            schedule.append({
                "task": str(entry.get("task") or entry.get("location") or entry.get("step", "")),
                "start": _parse_hours(entry.get("start") or entry.get("visit_start") or entry.get("arrival")),
                "end": _parse_hours(entry.get("end") or entry.get("visit_end")),
            })

        usage = bridge_result.get("usage", {}) or {}
        total_tokens = int(usage.get("totalTokens", 0))
        self.token_usage_total = total_tokens
        self.execution_times.append(elapsed)

        return {
            "achieved_goals": achieved,
            "satisfied_constraints": satisfied,
            "schedule": schedule,
            "disruptions_handled": [],
            "replanning_attempts": [],
            "resource_usage": {
                "token_usage": {"total_tokens": total_tokens},
                "execution_times": [elapsed],
            },
            # 额外留档：原始产出与桥级用量（evaluator 的 TaskResult 不收，落结果文件用）
            "raw_output": bridge_result.get("finalText", ""),
            "aiteam_usage": usage,
            "spawned": bridge_result.get("spawned", []),
            "topology": bridge_result.get("topology"),
        }
