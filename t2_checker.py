# T2 判分器：工具必需任务（跨文件Join + 折扣核算）。
# 任务形状：两份数据文件（orders.json / discounts.json）必须都读取并按类别 Join，
# 逐单计算折后收入、汇总总额——40 行级别，心算不可能，必须用工具。
# 判分：逐单核对（25 单）+ 总额，全部本地重算，不信任自报。
import json
import re
import sys
from pathlib import Path

CATEGORIES = {"硬件": 10, "软件": 15, "服务": 5, "培训": 20, "维护": 8}  # 折扣 %
ORDERS = 25


def gen_data():
    """确定性公式生成订单与折扣表（可复现）。"""
    cats = list(CATEGORIES)
    orders = {}
    for i in range(1, ORDERS + 1):
        oid = f"O{i:02d}"
        orders[oid] = {
            "category": cats[i % len(cats)],
            "qty": (i * 7) % 9 + 1,          # 1..9
            "unit_price": ((i * 53) % 800) + 100,  # 100..899
        }
    return orders, dict(CATEGORIES)


def ground_truth():
    orders, discounts = gen_data()
    per, total = {}, 0.0
    for oid, o in orders.items():
        rev = round(o["qty"] * o["unit_price"] * (1 - discounts[o["category"]] / 100), 2)
        per[oid] = rev
        total = round(total + rev, 2)
    return {"per_order": per, "grand_total": total}


def _num(x):
    try:
        return float(str(x).replace(",", "").replace("¥", "").replace("元", ""))
    except (TypeError, ValueError):
        return None


def _tolerant_extract(final):
    """格式宽容抽取：per_order 字典 / orders 数组（id+revenue）都能读。"""
    per = {}
    if not isinstance(final, dict):
        return per
    d = final.get("per_order")
    if isinstance(d, dict):
        for k, v in d.items():
            v = _num(v)
            if v is not None:
                per[k] = v
    arr = final.get("orders")
    if isinstance(arr, list):
        for e in arr:
            if isinstance(e, dict) and e.get("id"):
                v = _num(e.get("revenue") or e.get("收入"))
                if v is not None:
                    per[str(e["id"])] = v
    return per


def check_result_file(path):
    r = json.loads(Path(path).read_text(encoding="utf-8"))
    text = r.get("finalText", "") or ""
    gt = ground_truth()
    final = None
    for b in reversed(re.findall(r"```json\s*([\s\S]*?)```", text)):
        try:
            data = json.loads(b)
            if isinstance(data, dict) and ("per_order" in data or "grand_total" in data or "orders" in data):
                final = data
                break
        except json.JSONDecodeError:
            continue
    rep = {"condition": r.get("condition"), "task_id": r.get("task_id"),
           "grand_total_want": gt["grand_total"]}
    if not final:
        rep["error"] = "最终回复里没有可解析的核算 JSON"
        return rep
    per = final.get("per_order") or {}
    ok = sum(1 for oid, want in gt["per_order"].items()
             if (v := _num(per.get(oid))) is not None and abs(v - want) <= 0.5)
    rep["contract_score"] = f"{ok}/{len(gt['per_order'])}"  # 契约格式分（指令遵从）
    got_total = _num(final.get("grand_total"))
    rep["grand_total"] = f"{got_total} vs {gt['grand_total']} {'✓' if got_total is not None and abs(got_total - gt['grand_total']) <= 0.5 else '✗'}"
    # 宽容分：计算保真（任意格式，按 id 对账）
    tol = _tolerant_extract(final)
    ok2 = sum(1 for oid, want in gt["per_order"].items()
              if (v := tol.get(oid)) is not None and abs(v - want) <= 0.5)
    rep["tolerant_score"] = f"{ok2}/{len(gt['per_order'])}"  # 计算保真分（格式无关）
    rep["all_ok_contract"] = (ok == len(gt["per_order"])) and got_total is not None and abs(got_total - gt["grand_total"]) <= 0.5
    rep["all_ok_tolerant"] = (ok2 == len(gt["per_order"])) and got_total is not None and abs(got_total - gt["grand_total"]) <= 0.5
    return rep


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "gen":
        orders, discounts = gen_data()
        print(json.dumps({"orders.json": json.dumps(orders, ensure_ascii=False, indent=1),
                          "discounts.json": json.dumps(discounts, ensure_ascii=False, indent=1),
                          "ground_truth": ground_truth()}, ensure_ascii=False))
    elif len(sys.argv) > 1:
        print(json.dumps(check_result_file(sys.argv[1]), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
