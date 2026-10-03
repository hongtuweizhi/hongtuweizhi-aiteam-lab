# T4b 判分器：数据依赖链任务（课题 4 的真正测试场）。
#
# 任务形状：3 个 worker 严格依赖（A 物料缺口 → B 采购排期 → C 预算审核），
# 全链数字有**确定性标准答案**——判分器本地重算，逐字段核对最终产出，
# 不信任自报、不需要 LLM 裁判。
#
# 对照设计（同任务同模型同 N=3，只变上下文策略）：
#   isolated：lead 把 A/B/C 需要的输入写进各自派工文本（考验 lead 中继保真）
#   shared  ：A 把产出写黑板，B/C 直接读（考验黑板读写保真）
# 度量：终局数字正确率（客观）、token 成本（isolated 的中继开销 vs shared 的工具开销）、
#       错误传播位置（哪个字段先错）。
import json
import re
import sys
from pathlib import Path

# ── 钉死的实例与标准答案（任务文本与判分共用同一份）──
INSTANCE = {
    "product": "智能水杯",
    "unit_price": 85,              # 出厂价 ¥/台
    "first_order": 1200,           # 首批订单（台），30 天内交付
    "bom": {"杯体": 1, "电路板": 2, "电池": 1},
    "stock": {"杯体": 400, "电路板": 900, "电池": 380},
    "purchase": {"杯体": {"price": 30, "lead_days": 5},
                 "电路板": {"price": 12, "lead_days": 3},
                 "电池": {"price": 8, "lead_days": 7}},
    "assembly_cost_per_unit": 15,
}


def ground_truth():
    """本地重算全链标准答案（判分的唯一依据）。"""
    order = INSTANCE["first_order"]
    gap, buy_cost = {}, {}
    for part, per in INSTANCE["bom"].items():
        need = order * per
        gap[part] = need - INSTANCE["stock"][part]
        buy_cost[part] = gap[part] * INSTANCE["purchase"][part]["price"]
    total_buy = sum(buy_cost.values())
    critical_days = max(INSTANCE["purchase"][p]["lead_days"] for p in INSTANCE["purchase"])
    revenue = order * INSTANCE["unit_price"]
    assembly = order * INSTANCE["assembly_cost_per_unit"]
    total_cost = total_buy + assembly
    profit = revenue - total_cost
    feasible = profit > 0 and critical_days <= 30
    return {
        "gap": gap, "buy_cost": buy_cost, "procurement_total": total_buy,
        "critical_path_days": critical_days, "revenue": revenue,
        "assembly_cost": assembly, "total_cost": total_cost,
        "profit": profit, "feasible": feasible,
    }


def _nums(text):
    return set(float(x.replace(",", "")) for x in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", text))


def check_result_file(path: str):
    """对一份 result.json 逐字段核对（数字精确匹配，容忍千分位/小数波动）。"""
    r = json.loads(Path(path).read_text(encoding="utf-8"))
    text = r.get("finalText", "") or ""
    gt = ground_truth()
    nums = _nums(text)
    fields = {
        "gap_杯体": gt["gap"]["杯体"], "gap_电路板": gt["gap"]["电路板"], "gap_电池": gt["gap"]["电池"],
        "采购费_杯体": gt["buy_cost"]["杯体"], "采购费_电路板": gt["buy_cost"]["电路板"],
        "采购费_电池": gt["buy_cost"]["电池"], "采购总额": gt["procurement_total"],
        "关键路径天数": gt["critical_path_days"], "收入": gt["revenue"],
        "组装成本": gt["assembly_cost"], "总成本": gt["total_cost"], "毛利": gt["profit"],
    }
    detail = {k: (v in nums or float(v) in nums) for k, v in fields.items()}
    ok_count = sum(detail.values())
    return {
        "condition": r.get("condition"),
        "task_id": r.get("task_id"),
        "fields_correct": f"{ok_count}/{len(fields)}",
        "all_correct": ok_count == len(fields),
        "feasible_claim_ok": ("可行" in text) or ("feasible" in text.lower()),
        "detail": detail,
        "ground_truth": fields,
        "violations": [k for k, ok in detail.items() if not ok],
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        gt = ground_truth()
        print("标准答案（本地重算）：")
        print(json.dumps(gt, ensure_ascii=False, indent=1))
        sys.exit(0)
    print(json.dumps(check_result_file(sys.argv[1]), ensure_ascii=False, indent=1))
