# T4 交接保真探针：5 条机器可核验的约束过 4 次角色交接，测"约束存活率"。
#
# 这是实验 B（约束丢失）与课题 2/4 的测量仪器：
#   - fixed 条件：每跳的产出都在 agentRecords 里 → 可画"约束存活曲线"（第几跳丢的）
#   - free 条件：只有终局 → 测终局存活率
#   - 共享黑板条件（free-shared）：同样可测终局 + 黑板文件的存活贡献
#
# 约束定义（id → 核验函数，全部基于产出文本的 token/数值，零主观）：
import json
import re
import sys
from pathlib import Path


def _nums(text):
    return set(re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", text.replace("，", ",")))


def c1_venue(text):
    """C1 场地时间窗：『云轩厅』+ 14 点与 18 点边界。"""
    t = text
    return ("云轩厅" in t) and (("14" in _nums(t) or "14:00" in t)) and (("18" in _nums(t) or "18:00" in t))


def c2_budget(text):
    """C2 预算：上限 8000 出现，且算出 4784（2784+2000）或等价明细。"""
    n = _nums(text)
    ok_limit = "8,000" in text or "8000" in n
    ok_math = ("2,784" in text or "2784" in n) and ("4,784" in text or "4784" in n)
    return ok_limit and ok_math


def c3_headcount(text):
    """C3 人数折算：64 × 75% = 48。"""
    n = _nums(text)
    return ("64" in n) and ("75" in n or "0.75" in n) and ("48" in n)


def c4_keynote(text):
    """C4 嘉宾：『林岚』+ 演讲 ≥45 分钟。"""
    n = _nums(text)
    return ("林岚" in text) and ("45" in n)


def c5_qa(text):
    """C5 Q&A 环节 ≥30 分钟。"""
    n = _nums(text)
    return (("Q&A" in text) or ("QA" in text)) and ("30" in n)


CONSTRAINTS = {
    "C1_场地时间窗": c1_venue,
    "C2_预算上限与明细": c2_budget,
    "C3_人数折算": c3_headcount,
    "C4_嘉宾演讲时长": c4_keynote,
    "C5_QA环节": c5_qa,
}

ROLES_HINT = ["Requirements", "Budget", "Venue", "Guest", "Writer"]


def survival(text):
    """单份文本的约束存活集合。"""
    return {cid: bool(fn(text)) for cid, fn in CONSTRAINTS.items()}


def report_result_file(path: str):
    """对一份斗蛐蛐 result.json 出存活报告。"""
    r = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {
        "condition": r.get("condition"),
        "task_id": r.get("task_id"),
        "final_survival": survival(r.get("finalText", "") or ""),
        "per_stage": None,
    }
    stages = (r.get("agentRecords") or [])
    if stages:
        curve = []
        for i, a in enumerate(stages):
            s = survival(a.get("output", "") or "")
            curve.append({"stage": i, "agent": a.get("name"), "alive": sum(s.values()), "detail": s})
        out["per_stage"] = curve
        # 每条约束第一次丢失的跳数
        loss = {}
        for cid in CONSTRAINTS:
            for i, c in enumerate(curve):
                if not c["detail"][cid]:
                    loss[cid] = i
                    break
            else:
                loss[cid] = None
        out["first_lost_at_stage"] = loss
    out["survival_rate_final"] = round(sum(out["final_survival"].values()) / len(CONSTRAINTS), 2)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    rep = report_result_file(sys.argv[1])
    print(json.dumps(rep, ensure_ascii=False, indent=1))
