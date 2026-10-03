# 诊断探针：绕过 evaluator 直接调 langgraph router，打印原始产出与解析结果。
# 跑法（在 REALM-Bench 仓库根目录）：
#   ./venv/Scripts/python.exe /d/aiteam-lab/probe_langgraph_p1.py
import os
import sys
import json

ROOT = r"D:\aiteam-lab\repos\REALM-Bench"
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "agent_frameworks_general", "langgraph"))

# 复制 framework_runners.py 里 LangGraphRunner 的任务描述模板（保持一致）
td = None
from evaluation.task_definitions import TASK_DEFINITIONS  # noqa: E402

td = TASK_DEFINITIONS["P1"]
task_description = f"""
            Task: {td.description}
            Goals: {[goal.description for goal in td.goals]}
            Constraints: {[c.description for c in td.constraints]}
            Resources: {td.resources}
            """

print("═══ P1 任务描述（前 500 字）═══")
print(task_description[:500])

from router import run_agent  # noqa: E402  (在 sys.path 就绪后导入)

result = run_agent(task_description)

print("\n═══ run_agent 返回（解析后）═══")
print(json.dumps({k: v for k, v in result.items() if k != "raw_output"}, ensure_ascii=False, indent=1)[:800])
print("\n═══ raw_output（原始产出，前 1500 字）═══")
print(result.get("raw_output", "")[:1500])
