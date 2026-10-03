# 管线健康与判分无关信号：扫全部 runs/*/result.json。
# 看：解析成功率、耗时分布（抓停滞）、调用数/token 波动（课题 1 的原始素材）、
#     free 条件的编排决策（分身数随任务的变化）。
import json
import re
import statistics as st
from pathlib import Path

RUNS = Path(r"D:\aiteam-lab\runs")

rows = []
for d in sorted(RUNS.iterdir()):
    if not d.is_dir():
        continue
    m = re.match(r"(P\d+)-(fixed|free)-(\d+)", d.name)
    if not m:
        continue
    rp = d / "result.json"
    if not rp.exists():
        continue
    r = json.loads(rp.read_text(encoding="utf-8"))
    text = r.get("finalText", "") or ""
    u = r.get("usage", {}) or {}
    has_block = "```json" in text
    rows.append({
        "task": m.group(1), "cond": m.group(2), "ts": int(m.group(3)),
        "elapsed": r.get("elapsed_s", 0), "calls": u.get("calls", 0),
        "tokens": u.get("totalTokens", 0), "cost": round(u.get("costTotal", 0), 4),
        "spawn": r.get("spawn_count"), "has_block": has_block,
        "error": bool(r.get("error")),
    })

# 1) 解析与错误
errs = [r for r in rows if r["error"]]
no_block = [r for r in rows if not r["has_block"] and not r["error"]]
print(f"总运行 {len(rows)} 份 | 桥级错误 {len(errs)} | 正文无 JSON 块 {len(no_block)} 份")
for r in no_block:
    print(f"  无JSON块: {r['task']}-{r['cond']} ts={r['ts']}（早期桥版本的概率大）")

# 2) 停滞/离群（耗时 > 300s）
outliers = [r for r in rows if r["elapsed"] > 300]
print(f"\n耗时离群（>300s）: {len(outliers)} 份")
for r in sorted(outliers, key=lambda x: -x["elapsed"]):
    print(f"  {r['task']}-{r['cond']} ts={r['ts']}: {r['elapsed']:.0f}s, calls={r['calls']}")

# 3) 同格重复运行的波动（课题 1 素材：同一集群代码多次跑）
print("\n同格波动（≥3 份的格子）:")
cells = {}
for r in rows:
    cells.setdefault((r["task"], r["cond"]), []).append(r)
for (task, cond), rs in sorted(cells.items()):
    if len(rs) < 3:
        continue
    toks = [r["tokens"] for r in rs]
    calls = [r["calls"] for r in rs]
    el = [r["elapsed"] for r in rs]
    print(f"  {task}-{cond} n={len(rs)}: tokens {min(toks)}–{max(toks)} (CV={st.stdev(toks)/st.mean(toks):.2f}), "
          f"calls {min(calls)}–{max(calls)}, elapsed {min(el):.0f}–{max(el):.0f}s")

# 4) free 的编排决策 vs 任务（sweep 最新一份）
print("\nfree 条件编排决策（每任务最新一份）:")
for task in [f"P{i}" for i in range(1, 11)]:
    rs = sorted([r for r in rows if r["task"] == task and r["cond"] == "free"], key=lambda x: x["ts"])
    if rs:
        r = rs[-1]
        print(f"  {task}: spawn={r['spawn']} calls={r['calls']} tokens={r['tokens']} elapsed={r['elapsed']:.0f}s")
