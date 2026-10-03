#!/usr/bin/env python3
"""客观判分器模板 —— 复制本文件，改三处 [EDIT-*] 标记即可用于你的任务。

原则：不信任自报。ground_truth 本地重算；产出逐字段核对；数值容忍小误差；
拒绝无 JSON；空产出标记为基建失败而非 0 分。

用法：
  python checker_template.py selftest            # 自检（内置演示实例，验证打分逻辑）
  python checker_template.py solve               # 打印标准答案
  python checker_template.py check <result.json> # 校验一份被测产出（含 finalText 字段，或纯文本 .txt）
"""
import json
import re
import sys

# ── [EDIT-1] 钉死任务实例：数据唯一事实源（任务文本与判分共用）──────────────
INSTANCE = {
    "order": 1200,
    "items": {  # 演示：3 个部件；真实任务替换为你的实例
        "A": {"per_unit": 2, "stock": 400, "price": 12},
        "B": {"per_unit": 1, "stock": 900, "price": 8},
        "C": {"per_unit": 3, "stock": 100, "price": 5},
    },
}


# ── [EDIT-2] 本地重算标准答案 ────────────────────────────────────────────────
def ground_truth():
    costs = {}
    for pid, p in INSTANCE["items"].items():
        costs[pid] = (INSTANCE["order"] * p["per_unit"] - p["stock"]) * p["price"]
    return costs


# ── [EDIT-3] 字段清单（最终产出必须逐个给出且数值正确）─────────────────────
def fields():
    gt = ground_truth()
    return {f"cost_{pid}": v for pid, v in gt.items()}


def _num(x):
    try:
        return float(str(x).replace(",", "").replace("¥", "").replace("元", ""))
    except (TypeError, ValueError):
        return None


def _extract_final_json(text):
    """取最后一个 ```json 块（兜底：最后一个平衡 {...}）。"""
    if not text:
        return None
    blocks = re.findall(r"```json\s*([\s\S]*?)```", text)
    candidates = [b.strip() for b in blocks]
    if not candidates:
        tail = text[text.rfind("{"):]
        if tail.strip().endswith("}"):
            candidates.append(tail.strip())
    for cand in reversed(candidates):
        try:
            data = json.loads(cand)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None


def score_text(text):
    """对任意产出文本打分。返回逐字段判定与 violations。"""
    data = _extract_final_json(text)
    if data is None:
        return {"parse": False, "error": "无可解析 JSON（空产出/格式违约）"}
    flat = data.get("procurement") or data  # 允许嵌套或平铺
    detail, violations = {}, []
    for k, want in fields().items():
        pid = k.replace("cost_", "")
        got = _num(flat.get(pid)) or _num(flat.get(k))
        ok = got is not None and abs(got - want) <= 0.5
        detail[k] = {"want": want, "got": got, "ok": ok}
        if not ok:
            violations.append(f"{k}: 产出 {got} vs 正确 {want}")
    ok_n = sum(1 for d in detail.values() if d["ok"])
    return {
        "parse": True,
        "correct": f"{ok_n}/{len(fields())}",
        "all_ok": ok_n == len(fields()),
        "detail": detail,
        "violations": violations,
    }


def _text_of_result(path):
    p = str(path)
    if p.endswith(".json"):
        r = json.loads(open(path, encoding="utf-8").read())
        return r.get("finalText") or r.get("text") or r.get("output") or ""
    return open(path, encoding="utf-8").read()


def selftest():
    """内置演示：完美产出应满分，缺字段/算错/无 JSON 应被正确判定。"""
    gt = ground_truth()
    perfect = "分析过程略。\n```json\n{\"procurement\": {" + \
        ", ".join(f'"{pid}": {v}' for pid, v in gt.items()) + "}}\n```"
    assert score_text(perfect)["all_ok"], "完美产出未满分 —— 打分逻辑有 bug"
    broken = "```json\n{\"procurement\": {" + \
        ", ".join(f'"{pid}": {v * 2}' for pid, v in gt.items()) + "}}\n```"
    assert not score_text(broken)["all_ok"], "翻倍错误未被识别"
    assert score_text("没有 JSON 的回复")["parse"] is False, "无 JSON 未被识别"
    empty = score_text("")
    assert empty["parse"] is False, "空产出未被识别"
    print("selftest ✓：满分/算错/无 JSON/空产出 四种情形判定全部正确")
    print("标准答案（演示实例）：", json.dumps(ground_truth(), ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest()
    elif len(sys.argv) > 1 and sys.argv[1] == "solve":
        print(json.dumps(ground_truth(), ensure_ascii=False, indent=1))
    elif len(sys.argv) > 2 and sys.argv[1] == "check":
        print(json.dumps(score_text(_text_of_result(sys.argv[2])), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
