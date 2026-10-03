# 廉价中继保真曲线仪：单次调用测"单一上下文能扛多少行数字"。
# 动机：规模阶梯发现 3 部件多 agent 全对、6+ 部件全崩，但全战斗太贵（一局 1.6M）。
# 本仪器每次测量只花一次模型调用：给 N 部件原始数据 → 模型算出 N 行成本表 JSON →
# 本地逐行核对（ground truth 来自 t4c_checker.gen_instance，与战斗判分同一事实源）。
# 曲线用法：relay_curve.py --sizes 4,6,8,10,12 --runs 3 --model deepseek-v4.1-flash
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:\aiteam-lab")
from t4c_checker import gen_instance  # noqa: E402  同一事实源

from openai import OpenAI  # noqa: E402

FIRST_ORDER = 1200


def ground_truth(n):
    parts = gen_instance(n)
    costs = {}
    for pid, p in parts.items():
        gaps = FIRST_ORDER * p["per_unit"] - p["stock"]
        costs[pid] = gaps * p["price"]
    return parts, costs


def build_prompt(n, parts):
    rows = "\n".join(
        f"{pid}: 单台用量 {p['per_unit']}，库存 {p['stock']}，采购单价 {p['price']} 元/个"
        for pid, p in parts.items()
    )
    return (
        f"某产品首批订单 1200 台，需为 {n} 个部件制定采购成本表。给定数据：\n{rows}\n\n"
        f"请逐个部件计算：采购成本 = (1200 × 单台用量 − 库存) × 采购单价。\n"
        f"只输出一个 JSON 对象，格式：\n"
        f'{{"procurement": {{"P01": <成本>, "P02": <成本>, ...}}}}\n'
        f"必须覆盖全部 {n} 个部件，不要输出其他内容。"
    )


def num(x):
    try:
        return float(str(x).replace(",", "").replace("¥", "").replace("元", ""))
    except (TypeError, ValueError):
        return None


def score(text, costs):
    import re
    m = re.search(r"\{[\s\S]*\}", text or "")
    if not m:
        return {"parse": False}
    try:
        data = json.loads(m.group())
    except json.JSONDecodeError:
        return {"parse": False}
    proc = data.get("procurement") or {}
    ok = sum(1 for pid, c in costs.items()
             if (v := num(proc.get(pid))) is not None and abs(v - c) <= 0.5)
    return {"parse": True, "correct": ok, "total": len(costs),
            "rate": round(ok / len(costs), 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="4,6,8,10,12")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--model", default="deepseek-v4.1-flash")
    ap.add_argument("--endpoint", default="https://opencode.ai/zen/go/v1")
    ap.add_argument("--keyfile", default=r"D:\aiteam-lab\agent\auth.json")
    ap.add_argument("--keypath", default="opencode-go,key")
    ap.add_argument("--out", default=r"D:\aiteam-lab\relay_curve_results.json")
    args = ap.parse_args()

    key = json.loads(open(args.keyfile, encoding="utf-8").read())
    node = key
    for k in args.keypath.split(","):
        node = node[k]
    client = OpenAI(base_url=args.endpoint, api_key=node,
                    default_headers={"x-opencode-session": "aiteam-relay-curve",
                                     "x-opencode-client": "aiteam-lab"})

    results = {"model": args.model, "endpoint": args.endpoint, "runs": args.runs, "data": {}}
    out_path = Path(args.out)
    if out_path.exists():
        old = json.loads(out_path.read_text(encoding="utf-8"))
        if old.get("model") == args.model:
            results["data"] = old.get("data", {})

    for n in [int(x) for x in args.sizes.split(",")]:
        parts, costs = ground_truth(n)
        rows = []
        for i in range(args.runs):
            try:
                resp = client.chat.completions.create(
                    model=args.model,
                    messages=[{"role": "user", "content": build_prompt(n, parts)}],
                    temperature=0,
                )
                text = resp.choices[0].message.content or ""
                s = score(text, costs)
                s["tokens"] = resp.usage.total_tokens if resp.usage else 0
            except Exception as e:
                s = {"error": f"{type(e).__name__}: {str(e)[:80]}"}
            s["run"] = i
            rows.append(s)
            print(f"N={n} run{i}: {json.dumps(s, ensure_ascii=False)}")
        results["data"][str(n)] = rows
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n═══ 保真曲线（各 N 的平均正确行数率）═══")
    for n, rows in sorted(results["data"].items(), key=lambda kv: int(kv[0])):
        rates = [r.get("rate") for r in rows if r.get("rate") is not None]
        toks = [r.get("tokens", 0) for r in rows if r.get("tokens")]
        avg = f"{sum(rates)/len(rates):.2f}" if rates else "-"
        print(f"N={n:>3}: 平均正确率 {avg} ({len(rates)}/{len(rows)} 次可解析) | 平均 tok "
              f"{sum(toks)//len(toks) if toks else '-'}")
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
