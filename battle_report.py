# 斗蛐蛐战报聚合：读 evaluator 的 benchmark CSV（指标）+ runs/*/result.json（用量/编排），
# 产出每任务 × 条件的对照表。
# 用法: venv python battle_report.py <csv目录> [runs目录]
import csv
import json
import os
import sys
from pathlib import Path

csv_dir = Path(sys.argv[1] if len(sys.argv) > 1 else r"D:\aiteam-lab\realm-battle-full")
runs_dir = Path(sys.argv[2] if len(sys.argv) > 2 else r"D:\aiteam-lab\runs")

# 1) 从 CSV 拿每框架每任务的指标
rows = []
for f in csv_dir.glob("benchmark_results_*.csv"):
    with open(f, encoding="utf-8") as fh:
        rows += list(csv.DictReader(fh))
if not rows:
    print("没找到 benchmark_results_*.csv")
    sys.exit(1)

# 列名探测
cols = rows[0].keys()
def col(*names):
    for n in names:
        if n in cols:
            return n
    return None

c_fw, c_task = col("framework"), col("task_id")
c_goal = col("goal_satisfaction_rate")
c_cons = col("constraint_satisfaction_rate")
c_makespan = col("makespan")
c_token = col("token_usage")
c_time = col("execution_time")

# 2) runs 里最新的 result.json（用量/编排决策）
def latest_result(task, condition):
    cands = sorted(runs_dir.glob(f"{task}-{condition}-*/result.json"), key=os.path.getmtime)
    return cands[-1] if cands else None

def load_meta(task, condition):
    p = latest_result(task, condition)
    if not p:
        return {}
    r = json.loads(p.read_text(encoding="utf-8"))
    u = r.get("usage", {})
    return {
        "tokens": round(u.get("totalTokens", 0)),
        "cost": round(u.get("costTotal", 0), 4),
        "calls": u.get("calls", 0),
        "elapsed": round(r.get("elapsed_s", 0)),
        "spawn": r.get("spawn_count"),
        "topology": " → ".join(r.get("topology", [])),
    }

tasks = sorted({r[c_task] for r in rows if r.get(c_task)})
fws = sorted({r[c_fw] for r in rows if r.get(c_fw)})
meta_all = {fw: {t: load_meta(t, fw.replace("aiteam-", "")) for t in tasks} for fw in fws}

def fmt(v, suf=""):
    if v is None or v == "":
        return "-"
    try:
        return f"{float(v):.0f}{suf}" if suf == "%" else f"{float(v):.1f}{suf}"
    except (TypeError, ValueError):
        return str(v)

print("═" * 100)
print("斗蛐蛐战报（每任务 1 次，模型 deepseek-v4.1-flash @ opencode-go）")
print("═" * 100)
header = f"{'任务':<5} | {'条件':<13} | {'目标%':>5} | {'tok':>7} | {'$':>7} | {'调用':>4} | {'秒':>5} | {'分身':>4} | 备注"
print(header)
print("-" * 100)
for t in tasks:
    for fw in fws:
        row = next((r for r in rows if r.get(c_fw) == fw and r.get(c_task) == t), None)
        m = meta_all[fw].get(t, {})
        note = m.get("topology", "") if fw.endswith("fixed") else (f"单干" if m.get("spawn") == 1 else f"开了 {m.get('spawn')} 个分身" if m.get("spawn") else "")
        if len(note) > 42:
            note = note[:39] + "..."
        print(f"{t:<5} | {fw:<13} | {fmt(row.get(c_goal) if row else None, '%'):>5} | {m.get('tokens','-'):>7} | {m.get('cost','-'):>7} | {m.get('calls','-'):>4} | {m.get('elapsed','-'):>5} | {m.get('spawn','-') if m.get('spawn') is not None else '-':>4} | {note}")
    print("-" * 100)

# 3) 汇总
print("汇总（各条件跨任务平均）:")
for fw in fws:
    cond = fw.replace("aiteam-", "")
    goals = [float(r[c_goal]) for r in rows if r.get(c_fw) == fw and r.get(c_goal) not in (None, "")]
    toks = [meta_all[fw][t].get("tokens", 0) or 0 for t in tasks]
    costs = [meta_all[fw][t].get("cost", 0) or 0 for t in tasks]
    if goals:
        print(f"  {fw:<14} 目标均值 {sum(goals)/len(goals):.0f}% | 平均 tok {sum(toks)/max(len(toks),1):.0f} | 总成本 ${sum(costs):.3f}")
