#!/usr/bin/env python3
"""交接保真探针模板 —— 复制本文件，改两处 [EDIT-*] 即可用于你的多 agent 管线。

用法：
  python probe_template.py selftest              # 自检（内置 5 约束 × 3 阶段合成数据）
  python probe_template.py report <result.json>  # 对一份被测运行出存活报告
      result.json 需含：finalText（终稿文本）；可选 agentRecords：[{name, output}, ...]（逐阶段产出）
"""
import json
import re
import sys
from pathlib import Path

# ── [EDIT-1] 约束集：每条 = 名称 → 核验函数（输入某阶段产出文本 → bool）────────
# 设计要点：约束必须绑定"产出文本里的 token/数值"，能被正则或算式核验。
# 下面是 5 条演示约束（技术沙龙筹备任务），替换成你的。


def _nums(text):
    return set(re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", text.replace("，", ",")))


def c1_venue(text):
    """场地时间窗：场地名 + 边界小时必须同时出现。"""
    return ("云轩厅" in text) and ("14:00" in text or "14" in _nums(text)) and ("18:00" in text or "18" in _nums(text))


def c2_budget(text):
    """预算：上限与可算明细同时出现（8000；明细 2784 与 4784）。"""
    n = _nums(text)
    return ("8,000" in text or "8000" in n) and ("2,784" in text or "2784" in n) and ("4,784" in text or "4784" in n)


def c3_headcount(text):
    """人数折算：64 × 75% = 48 三个数都在。"""
    n = _nums(text)
    return ("64" in n) and ("75" in n or "0.75" in n) and ("48" in n)


def c4_keynote(text):
    """嘉宾：专有名词 + 时长下限。"""
    return ("林岚" in text) and ("45" in _nums(text))


def c5_qa(text):
    """Q&A ≥30 分钟。"""
    return (("Q&A" in text) or ("QA" in text)) and ("30" in _nums(text))


CONSTRAINTS = {
    "C1_场地时间窗": c1_venue,
    "C2_预算上限与明细": c2_budget,
    "C3_人数折算": c3_headcount,
    "C4_嘉宾演讲时长": c4_keynote,
    "C5_QA环节": c5_qa,
}


def survival(text):
    """单份文本的约束存活集合。"""
    return {cid: bool(fn(text)) for cid, fn in CONSTRAINTS.items()}


def report(stages, final_text):
    """
    stages: [{"name": <阶段名>, "text": <该阶段产出文本>}, ...]（按执行序；黑盒系统传 []）
    final_text: 终稿文本
    """
    out = {"final_survival": survival(final_text),
           "survival_rate_final": None, "per_stage": None, "first_lost_at_stage": None}
    out["survival_rate_final"] = round(sum(out["final_survival"].values()) / len(CONSTRAINTS), 2)
    if stages:
        curve = []
        for i, s in enumerate(stages):
            det = survival(s.get("text", ""))
            curve.append({"stage": i, "name": s.get("name", f"stage{i}"),
                          "alive": sum(det.values()), "detail": det})
        out["per_stage"] = curve
        loss = {}
        for cid in CONSTRAINTS:
            for c in curve:
                if not c["detail"][cid]:
                    loss[cid] = c["stage"]
                    break
            else:
                loss[cid] = None
        out["first_lost_at_stage"] = loss
    return out


def _demo_stages():
    """[EDIT-2] 演示：真实使用时把这里换成你的管线采集逻辑（框架事件/日志/逐步落盘）。"""
    full = ("场地云轩厅周六 14:00-18:00；报名 64 人按 75% 出席=48 人；"
            "餐费 48×58=2,784 加场地 2,000 共 4,784 未超 8,000；林岚演讲 45 分钟；Q&A 30 分钟。")
    lost1 = ("预算核算：餐费 2,784 + 场地 2,000 = 4,784，未超 8,000。"
             "人数折算 64×75%=48。")  # 丢 C1/C4/C5
    lost2 = "预算 4,784 元在 8,000 以内，人数 48 人，议程含 Q&A 30 分钟。"  # 再丢 C3
    return [{"name": "需求", "text": full},
            {"name": "预算", "text": lost1},
            {"name": "终稿", "text": lost2}]


def selftest():
    stages = _demo_stages()
    final = stages[-1]["text"]
    rep = report(stages, final)
    assert rep["per_stage"][0]["alive"] == 5, "阶段0应全活"
    assert rep["per_stage"][1]["alive"] == 2, f"阶段1应存活2条，实际{rep['per_stage'][1]['alive']}"
    assert rep["survival_rate_final"] == 0.2, f"终局存活率应为0.2，实际{rep['survival_rate_final']}"
    assert rep["first_lost_at_stage"]["C1_场地时间窗"] == 1, "C1 应在第1跳丢失"
    assert rep["first_lost_at_stage"]["C5_QA环节"] == 1, "C5 应在第1跳丢失"
    assert rep["first_lost_at_stage"]["C2_预算上限与明细"] == 2, "C2 应在第2跳丢失"
    # 黑盒模式（只有终稿）
    blackbox = report([], final)
    assert blackbox["survival_rate_final"] == 0.2 and blackbox["per_stage"] is None
    print("selftest ✓：逐跳曲线、首次丢失定位、终局存活率、黑盒模式 全部正确")
    print("演示曲线：", json.dumps(rep["first_lost_at_stage"], ensure_ascii=False))


def report_result_file(path):
    """[EDIT-2] 对一份被测运行出报告。默认约定：result.json 含 finalText 与可选 agentRecords。"""
    r = json.loads(Path(path).read_text(encoding="utf-8"))
    stages = [{"name": a.get("name", str(i)), "text": a.get("output", "")}
              for i, a in enumerate(r.get("agentRecords") or [])]
    return report(stages, r.get("finalText", ""))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest()
    elif len(sys.argv) > 1:
        print(json.dumps(report_result_file(sys.argv[1]), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
