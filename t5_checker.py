# T5 判分器：模糊探索任务（planted bug 定位）。
# 任务形状：只给模糊症状（"8 台 × 153 元、软件类的订单收入明显不对"）+ 工作目录源码，
# 不给文件/行号——考察探索与定位。判分完全客观：
#   1) 根因定位：必须指出 shop.py 的 order_revenue 函数（唯一 planted bug，含干扰文件）；
#   2) 修正值：给出该例的正确收入 1040.40（8 × 153 × (1 − 15%)）——数值精确核对。
# 源码 fixture 由 fixture_files() 生成（seedFiles 注入工作目录）。
import json
import sys
from pathlib import Path

BUG_FILE = "shop.py"
BUG_FUNC = "order_revenue"
EXAMPLE = {"qty": 8, "unit_price": 153, "category": "软件", "discount": 15}
CORRECT_REVENUE = round(EXAMPLE["qty"] * EXAMPLE["unit_price"] * (1 - EXAMPLE["discount"] / 100), 2)  # 1040.40


def fixture_files():
    shop = '''"""订单收入计算模块。"""
DISCOUNTS = {"硬件": 10, "软件": 15, "服务": 5, "培训": 20, "维护": 8}


def order_revenue(qty, unit_price, category, discounts=None):
    """计算单笔订单收入。"""
    discounts = discounts or DISCOUNTS
    rate = discounts.get(category, 0)
    return round(qty * unit_price * rate / 100, 2)
'''
    utils = '''"""通用工具。"""
def safe_round(x, nd=2):
    """四舍五入到 nd 位。"""
    return round(x + 0.0, nd)
'''
    readme = '''# shop 模块

`order_revenue(qty, unit_price, category)` 应返回：
qty × unit_price × (1 − 折扣%/100)，折扣按类别查表（硬件 10%、软件 15%、服务 5%、培训 20%、维护 8%）。
'''
    return {"shop.py": shop, "utils.py": utils, "README.md": readme}


def check_result_file(path):
    r = json.loads(Path(path).read_text(encoding="utf-8"))
    text = r.get("finalText", "") or ""
    final = None
    import re
    for b in reversed(re.findall(r"```json\s*([\s\S]*?)```", text)):
        try:
            data = json.loads(b)
            if isinstance(data, dict) and ("root_cause_file" in data or "root_cause" in data):
                final = data
                break
        except json.JSONDecodeError:
            continue
    rep = {"condition": r.get("condition"), "task_id": r.get("task_id"),
           "expected": {"file": BUG_FILE, "function": BUG_FUNC, "corrected_revenue": CORRECT_REVENUE}}
    if not final:
        rep["error"] = "最终回复里没有可解析的 JSON"
        return rep
    blob = json.dumps(final, ensure_ascii=False)
    rep["file_found"] = BUG_FILE in blob
    rep["function_found"] = BUG_FUNC in blob
    rev = None
    for k in ("corrected_revenue", "corrected", "fixed_revenue"):
        rev = rev or _num(final.get(k))
    for v in (final.values() if isinstance(final, dict) else []):
        if rev is None:
            rev = _num(v)
    rep["revenue"] = f"{rev} vs {CORRECT_REVENUE} {'✓' if rev is not None and abs(rev - CORRECT_REVENUE) <= 0.5 else '✗'}"
    rep["all_ok"] = rep["file_found"] and rep["function_found"] and rev is not None and abs(rev - CORRECT_REVENUE) <= 0.5
    return rep


def _num(x):
    try:
        return float(str(x).replace(",", "").replace("¥", "").replace("元", ""))
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "gen":
        print(json.dumps(fixture_files(), ensure_ascii=False))
    elif len(sys.argv) > 1:
        print(json.dumps(check_result_file(sys.argv[1]), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
