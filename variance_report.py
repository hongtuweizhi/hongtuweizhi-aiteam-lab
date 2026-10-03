# N>1 方差战报聚合：读 evaluator 的 per-framework results JSON（每任务 N 条）
# + runs 目录里的 result.json（用量/编排），输出每格的均值/极差/CV。
# 用法: venv python variance_report.py <results目录> <runs目录> [t3也可]
import json
import statistics as st
import sys
from pathlib import Path

res_dir = Path(sys.argv[1] if len(sys.argv) > 1 else r"D:\aiteam-lab\realm-battle-variance")
runs_dir = Path(sys.argv[2] if len(sys.argv) > 2 else r"D:\aiteam-lab\runs")

records = []  # (framework, task, metrics dict, run_dir)
for f in sorted(res_dir.glob("*_results_*.json")):
    fw = f.name.split("_results_")[0]
    data = json.loads(f.read_text(encoding="utf-8"))
    for item in (data if isinstance(data, list) else []):
        task = item.get("task_id")
        # 反查 run 目录：按任务+条件取最新的若干份（与 runs 数对齐用时间排序）
        records.append({"fw": fw, "task": task, "metrics": item.get("metrics", {}),
                        "ts_hint": None})

def run_meta(task, condition):
    """该任务+条件全部 run 的 meta（按时间升序）。mixed 的历史目录也叫 T4b-free-*。"""
    pats = {"mixed": [f"{task}-free-mixed-*", f"{task}-free-*"],
            "free-mixed": [f"{task}-free-mixed-*", f"{task}-free-*"]}.get(
        condition, [f"{task}-{condition}-*"])
    out = []
    seen = set()
    for pat in pats:
        for d in sorted(runs_dir.glob(pat), key=lambda p: p.stat().st_mtime):
            if d in seen:
                continue
            seen.add(d)
            rp = d / "result.json"
            if not rp.exists():
                continue
            r = json.loads(rp.read_text(encoding="utf-8"))
            if r.get("error"):  # 崩溃/静默失败的运行不计入
                continue
            u = r.get("usage", {}) or {}
            out.append({
                "tokens": u.get("totalTokens", 0),
                "cost": round(u.get("costTotal", 0), 4),
                "calls": u.get("calls", 0),
                "elapsed": round(r.get("elapsed_s", 0)),
                "spawn": r.get("spawn_count"),
                "dir": d.name,
            })
    return out

def stats(values, fmt="{:.2f}"):
    vals = [v for v in values if v is not None]
    if not vals:
        return "-"
    if len(vals) == 1:
        return fmt.format(vals[0])
    mean = st.mean(vals)
    cv = (st.stdev(vals) / mean) if mean else 0
    return f"{min(vals):.2f}~{max(vals):.2f} (CV={cv:.2f})"

conds = sorted({r["fw"] for r in records})
def _task_key(t: str):
    import re as _re
    m = _re.match(r"([A-Za-z]*)(\d+)", t)
    return (m.group(1) if m else "", int(m.group(2)) if m else 0)

tasks = sorted({r["task"] for r in records}, key=_task_key)
print("═" * 96)
print("N 次方差战报")
print("═" * 96)
for fw in conds:
    cond = fw.replace("aiteam-", "")
    print(f"\n【{fw}】")
    for t in tasks:
        rs = [r for r in records if r["fw"] == fw and r["task"] == t]
        if not rs:
            continue
        metas = run_meta(t, cond)
        n = len(rs)
        goal = [r["metrics"].get("goal_satisfaction_rate") for r in rs]
        tok = [m["tokens"] for m in metas]
        cost = [m["cost"] for m in metas]
        el = [m["elapsed"] for m in metas]
        spawn = [m["spawn"] for m in metas if m.get("spawn") is not None]
        print(f"  {t}: n={n} | 目标% {stats(goal)} | tok {stats(tok, '{:.0f}')} | "
              f"¥ {stats(cost)} | 秒 {stats(el, '{:.0f}')} | 分身 {stats(spawn, '{:.0f}')}")

# T3 客观判分（若在跑的任务里）
try:
    sys.path.insert(0, r"D:\aiteam-lab")
    from t3_checker import check_result_file
    t3_rows = [(r["task"], r["fw"]) for r in records if r["task"] == "T3"]
    if t3_rows:
        print("\n【T3 客观判分（不信任自报）】")
        for task, fw in t3_rows:
            cond = fw.replace("aiteam-", "")
            for d in sorted(runs_dir.glob(f"{task}-{cond}-*"), key=lambda p: p.stat().st_mtime):
                rp = d / "result.json"
                if not rp.exists():
                    continue
                rep = check_result_file(str(rp))
                print(f"  {d.name}: 覆盖 {rep['ops_found']}/{rep['ops_expected']} "
                      f"先后{'✓' if rep['precedence_ok'] else '✗'} 不重叠{'✓' if rep['machine_no_overlap'] else '✗'} "
                      f"工时{'✓' if rep['durations_ok'] else '✗'} | makespan {rep['makespan']} "
                      f"vs 最优 {rep['optimal_makespan']} (ratio {rep.get('makespan_ratio','-')}) "
                      f"| 自报 {rep['self_claimed_goals']}")
except Exception as e:
    print(f"(T3 客观判分跳过: {e})")
