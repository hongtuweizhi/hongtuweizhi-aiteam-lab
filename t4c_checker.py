# T4c 判分器：大中间产物 + 数据分区（共享黑板的真正用例验证）。
#
# 任务形状：40 个部件的采购计划，数据分区在文件里（stock.json / prices.json 在工作目录），
# worker A 必须读文件算缺口 → 40 行缺口表是 B 的唯一输入来源（隔离=lead 中继 40 行，
# 共享=A 写黑板 B 直读）→ C 用采购总额审预算。
# 判分：最终 JSON 的 40 行采购成本逐行核对 + 总额/预算字段（公式化实例，本地重算）。
import json
import re
import sys
from pathlib import Path

FIRST_ORDER = 1200
UNIT_PRICE = 85
ASSEMBLY = 15
DELIVERY_DAYS = 30
PARTS = 40


def gen_instance(n: int = PARTS):
    """公式化实例（确定性，可复现）：P01..P{n}。规模阶梯（12/20/40）共用同一公式。"""
    parts = {}
    for i in range(1, n + 1):
        pid = f"P{i:02d}"
        parts[pid] = {
            "per_unit": (i % 3) + 1,           # 单台用量 1..3
            "stock": (i * 37) % 50 + 10,       # 库存 10..59（远小于需求，缺口恒正）
            "price": (i * 13) % 20 + 5,        # 采购单价 5..24
            "lead_days": (i % 5) + 1,          # 采购周期 1..5
        }
    return parts


def ground_truth(n: int = PARTS):
    parts = gen_instance(n)
    gaps, costs = {}, {}
    for pid, p in parts.items():
        need = FIRST_ORDER * p["per_unit"]
        gaps[pid] = need - p["stock"]
        costs[pid] = gaps[pid] * p["price"]
    total = sum(costs.values())
    critical = max(p["lead_days"] for p in parts.values())
    revenue = FIRST_ORDER * UNIT_PRICE
    assembly = FIRST_ORDER * ASSEMBLY
    total_cost = total + assembly
    profit = revenue - total_cost
    return {"gaps": gaps, "costs": costs, "procurement_total": total,
            "critical_path_days": critical, "revenue": revenue,
            "assembly_cost": assembly, "total_cost": total_cost,
            "profit": profit, "feasible": profit > 0 and critical <= DELIVERY_DAYS}


def _num(x):
    try:
        return float(str(x).replace(",", "").replace("¥", "").replace("元", ""))
    except (ValueError, TypeError):
        return None


def check_result_file(path: str, parts: int | None = None):
    r = json.loads(Path(path).read_text(encoding="utf-8"))
    text = r.get("finalText", "") or ""
    if parts is None:
        # 规模自动探测：从同目录 spec.json 的 resources.parts 读
        spec_path = Path(path).parent / "spec.json"
        if spec_path.exists():
            try:
                parts = json.loads(spec_path.read_text(encoding="utf-8")).get("task", {}).get("resources", {}).get("parts")
            except Exception:
                parts = None
        parts = parts or PARTS
    gt = ground_truth(parts)

    # 抠最终 JSON（含 40 行采购表）
    final = None
    for b in reversed(re.findall(r"```json\s*([\s\S]*?)```", text)):
        try:
            data = json.loads(b)
            if isinstance(data, dict) and ("procurement" in data or "procurement_total" in data):
                final = data
                break
        except json.JSONDecodeError:
            continue

    rep = {"condition": r.get("condition"), "task_id": r.get("task_id"),
           "optimal_total": gt["procurement_total"], "ground_truth_feasible": gt["feasible"]}
    if not final:
        rep["error"] = "最终回复里没有可解析的采购 JSON"
        return rep

    proc = final.get("procurement") or {}
    per_part_ok, wrong = 0, []
    for pid, cost in gt["costs"].items():
        got = _num(proc.get(pid))
        if got is not None and abs(got - cost) <= 0.5:
            per_part_ok += 1
        else:
            wrong.append(f"{pid}: 产出 {proc.get(pid)} vs 正确 {cost}")
    rep["per_part_correct"] = f"{per_part_ok}/{len(gt['costs'])}"
    rep["per_part_wrong_sample"] = wrong[:5]

    totals = {
        "procurement_total": (_num(final.get("procurement_total")), gt["procurement_total"]),
        "critical_path_days": (_num(final.get("critical_path_days")), gt["critical_path_days"]),
        "total_cost": (_num(final.get("total_cost")), gt["total_cost"]),
        "profit": (_num(final.get("profit")), gt["profit"]),
    }
    for k, (got, want) in totals.items():
        rep[k] = f"{got} vs {want} {'✓' if got is not None and abs(got - want) <= 0.5 else '✗'}"
    claimed_feasible = final.get("feasible")
    rep["feasible"] = f"{claimed_feasible} vs {gt['feasible']} {'✓' if claimed_feasible == gt['feasible'] else '✗'}"
    rep["all_ok"] = (per_part_ok == len(gt["costs"])) and all(
        g is not None and abs(g - w) <= 0.5 for g, w in totals.values())
    return rep


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "gen":
        # 输出 seedFiles（stock.json / prices.json 内容），供 runner 写入工作目录
        parts = gen_instance()
        stock = {pid: p["stock"] for pid, p in parts.items()}
        needs = {pid: p["per_unit"] for pid, p in parts.items()}
        prices = {pid: {"price": p["price"], "lead_days": p["lead_days"]} for pid, p in parts.items()}
        print(json.dumps({"stock.json": json.dumps(stock, ensure_ascii=False, indent=1),
                          "needs.json": json.dumps(needs, ensure_ascii=False, indent=1),
                          "prices.json": json.dumps(prices, ensure_ascii=False, indent=1),
                          "ground_truth": ground_truth()}, ensure_ascii=False))
    elif len(sys.argv) > 1:
        print(json.dumps(check_result_file(sys.argv[1]), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
