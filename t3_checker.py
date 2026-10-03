# T3 客观判分器：钉死的 3×3 JSSP 实例 + 离线穷举最优解 + 排程校验。
#
# 为什么存在：P11 战斗暴露了"发明数据"架构的死角——fixed 的 Setup Agent 和
# free 的 lead 各自编造实例，两边解的不是同一道题，自报 goal% 不可比。
# T3 把实例钉死在任务里，判分不信任任何自报：
#   - makespan 与离线穷举的精确最优解对比（达优率）
#   - 排程合法性机器核验（工序覆盖 / 工件先后 / 机器不重叠 / 工时一致）
#
# 原理：JSSP 的最优解必在 active schedule 集合里，而 active ⊆ semi-active；
# 枚举全部 9!/3!³ = 1680 个工件先后合法的工序全排列、按排列做贪婪半活动排程，
# 取最小 makespan —— 即为精确最优（3×3 规模毫秒级）。
#
# 用法：
#   python t3_checker.py solve                    # 打印实例与精确最优 makespan
#   python t3_checker.py check <result.json>      # 校验一份战斗产出
import itertools
import json
import re
import sys
from pathlib import Path

# ── 钉死的实例（T3 任务与判分共用同一份，写进 TASK_DEFINITIONS.resources）──
INSTANCE = {
    "machines": ["M1", "M2", "M3"],
    "jobs": [
        {"job_id": "J1", "operations": [
            {"op_id": "J1-O11", "machine": "M1", "duration": 2},
            {"op_id": "J1-O12", "machine": "M2", "duration": 3},
            {"op_id": "J1-O13", "machine": "M3", "duration": 2},
        ]},
        {"job_id": "J2", "operations": [
            {"op_id": "J2-O21", "machine": "M2", "duration": 4},
            {"op_id": "J2-O22", "machine": "M3", "duration": 1},
            {"op_id": "J2-O23", "machine": "M1", "duration": 3},
        ]},
        {"job_id": "J3", "operations": [
            {"op_id": "J3-O31", "machine": "M3", "duration": 2},
            {"op_id": "J3-O32", "machine": "M1", "duration": 3},
            {"op_id": "J3-O33", "machine": "M2", "duration": 2},
        ]},
    ],
}

OPS = {op["op_id"]: op for j in INSTANCE["jobs"] for op in j["operations"]}
JOB_SEQ = {j["job_id"]: [o["op_id"] for o in j["operations"]] for j in INSTANCE["jobs"]}


def _semi_active_makespan(order):
    """按工序启动顺序（工件先后合法）做半活动排程，返回 makespan。"""
    job_next = {jid: 0 for jid in JOB_SEQ}          # 每个工件下一个待排工序
    job_free = {jid: 0.0 for jid in JOB_SEQ}        # 工件上一工序结束时间
    machine_free = {m: 0.0 for m in INSTANCE["machines"]}
    for op_id in order:
        job_id = op_id.split("-")[0]
        op = OPS[op_id]
        start = max(job_free[job_id], machine_free[op["machine"]])
        end = start + op["duration"]
        job_free[job_id] = end
        machine_free[op["machine"]] = end
        job_next[job_id] += 1
    return max(job_free.values())


def solve_optimum():
    """穷举 1680 个线性扩展，返回（精确最优 makespan, 达到最优的排列数）。"""
    all_ops = list(OPS)
    best, count = None, 0
    for order in itertools.permutations(all_ops):
        # 检查工件内先后（线性扩展约束）
        pos = {op: i for i, op in enumerate(order)}
        if any(pos[b] < pos[a] for j in JOB_SEQ for a, b in zip(JOB_SEQ[j], JOB_SEQ[j][1:])):
            continue
        ms = _semi_active_makespan(order)
        if best is None or ms < best:
            best, count = ms, 1
        elif ms == best:
            count += 1
    return best, count


def parse_schedule(entries):
    """从产出 schedule 里抽 (op_id, start, end)；容错多种 task 写法。"""
    parsed = []
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        label = str(e.get("task") or e.get("operation") or e.get("location") or "")
        m = re.search(r"J\d+-O\d+", label)
        if not m:
            continue
        start, end = e.get("start"), e.get("end")
        if start is None or end is None:
            continue
        parsed.append((m.group(), float(start), float(end)))
    return parsed


def validate_schedule(entries):
    """机器核验一份排程。返回 dict：合法性与 objective 指标（不信任任何自报）。"""
    sched = parse_schedule(entries)
    result = {
        "ops_expected": len(OPS),
        "ops_found": len(sched),
        "all_ops_covered": False,
        "precedence_ok": False,
        "machine_no_overlap": False,
        "durations_ok": False,
        "makespan": None,
        "violations": [],
    }
    if not sched:
        result["violations"].append("没有任何可识别的工序条目")
        return result

    found = {}
    for op_id, s, e in sched:
        if op_id in found:
            result["violations"].append(f"{op_id} 重复")
        found[op_id] = (s, e)

    result["all_ops_covered"] = set(found) == set(OPS)
    for op in OPS:
        if op not in found:
            result["violations"].append(f"缺工序 {op}")

    # 工时一致
    dur_ok = True
    for op_id, (s, e) in found.items():
        if abs((e - s) - OPS[op_id]["duration"]) > 1e-6:
            dur_ok = False
            result["violations"].append(f"{op_id} 工时 {e-s} ≠ 规定 {OPS[op_id]['duration']}")
    result["durations_ok"] = dur_ok

    # 工件先后
    prec_ok = True
    for jid, seq in JOB_SEQ.items():
        times = [found[o] for o in seq if o in found]
        for (s1, e1), (s2, e2) in zip(times, times[1:]):
            if s2 < e1 - 1e-6:
                prec_ok = False
                result["violations"].append(f"{jid} 工序先后违反：后序先于前序结束")
                break
    result["precedence_ok"] = prec_ok

    # 机器不重叠（机器归属来自实例，不由产出自报）
    by_machine = {}
    for op_id, (s, e) in found.items():
        by_machine.setdefault(OPS[op_id]["machine"], []).append((s, e, op_id))
    overlap_ok = True
    for mach, lst in by_machine.items():
        lst.sort()
        for (s1, e1, o1), (s2, e2, o2) in zip(lst, lst[1:]):
            if s2 < e1 - 1e-6:
                overlap_ok = False
                result["violations"].append(f"{mach} 上 {o1} 与 {o2} 重叠")
    result["machine_no_overlap"] = overlap_ok

    if found:
        ms = max(e for _, e in found.values())
        result["makespan"] = ms
    return result


def objective_report(entries):
    """产出 objective 判分：合法性 + makespan 达优率（vs 离线穷举最优）。"""
    opt, _ = solve_optimum()
    v = validate_schedule(entries)
    v["optimal_makespan"] = opt
    if v["makespan"] is not None:
        v["makespan_ratio"] = round(v["makespan"] / opt, 3)   # 1.0 = 达到最优
        v["optimal"] = v["makespan_ratio"] == 1.0
    return v


def check_result_file(path: str):
    """校验一份斗蛐蛐 result.json（取最终回复里的 schedule JSON）。"""
    r = json.loads(Path(path).read_text(encoding="utf-8"))
    text = r.get("finalText", "") or ""
    blocks = re.findall(r"```json\s*([\s\S]*?)```", text)
    entries = []
    for b in reversed(blocks):
        try:
            data = json.loads(b)
            if isinstance(data, dict) and data.get("schedule"):
                entries = data["schedule"]
                break
        except json.JSONDecodeError:
            continue
    rep = objective_report(entries)
    rep["condition"] = r.get("condition")
    rep["task_id"] = r.get("task_id")
    rep["self_claimed_goals"] = _self_claimed(text)
    return rep


def _self_claimed(text: str):
    m = re.findall(r"```json\s*([\s\S]*?)```", text)
    for b in reversed(m):
        try:
            data = json.loads(b)
            if isinstance(data, dict) and "achieved_goals" in data:
                return data.get("achieved_goals")
        except json.JSONDecodeError:
            continue
    return None


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "solve":
        opt, count = solve_optimum()
        print(f"实例：{len(INSTANCE['machines'])} 机器 × {len(INSTANCE['jobs'])} 工件 × 3 工序")
        print(f"精确最优 makespan = {opt}（{count} 个排列达优）")
    elif len(sys.argv) > 2 and sys.argv[1] == "check":
        print(json.dumps(check_result_file(sys.argv[2]), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
