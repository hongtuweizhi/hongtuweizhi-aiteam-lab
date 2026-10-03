# 去标识化：把 sweep 的 20 份产出入卷。
# - 每个任务×条件取最新一份 result.json（= 全量 sweep 那次）
# - 剥条件线索：crew 角色名 → [成员]、"received context" 论文交接标记、拓扑/分身字段不外传
# - 文件名匿名（卷001…）、顺序打乱；映射单独存 mapping.json（不喂给裁判）
# 产物：D:/aiteam-lab/blind/submissions/*.txt + mapping.json + manifest.json
import json
import random
import re
from pathlib import Path

RUNS = Path(r"D:\aiteam-lab\runs")
CREWS = Path(r"D:\aiteam-lab\crews")
OUT = Path(r"D:\aiteam-lab\blind\submissions")
OUT.mkdir(parents=True, exist_ok=True)
TASKS = [f"P{i}" for i in range(1, 11)]

REPO = Path(r"D:\aiteam-lab\repos\REALM-Bench")
import sys
sys.path.insert(0, str(REPO))
from evaluation.task_definitions import TASK_DEFINITIONS  # noqa: E402


def latest_result(task: str, condition: str):
    cands = sorted(RUNS.glob(f"{task}-{condition}-*/result.json"), key=lambda p: p.stat().st_mtime)
    return cands[-1] if cands else None


def anonymize(text: str, crew_names: list) -> tuple[str, list]:
    redactions = []
    for name in sorted(crew_names, key=len, reverse=True):
        if name and name in text:
            text = text.replace(name, "[成员]")
            redactions.append(name)
    # 论文的交接标记：「<成员> received context:」行
    text = re.sub(r"\[成员\][^\n]{0,40}received context:\s*\n?", "", text)
    return text, redactions


def main():
    entries = []
    for task in TASKS:
        td = TASK_DEFINITIONS[task]
        crew_path = CREWS / f"{task}.json"
        crew_names = [a["name"] for a in json.loads(crew_path.read_text(encoding="utf-8"))["agents"]] if crew_path.exists() else []
        task_material = (
            f"【任务描述】{td.description}\n"
            f"【目标】" + "；".join(f"{g.goal_id}（{g.description}）" for g in td.goals) + "\n"
            f"【约束】" + "；".join(
                f"{c.constraint_id}（{c.constraint_type}）：{json.dumps(c.parameters, ensure_ascii=False)}"
                for c in td.constraints
            ) + "\n"
            f"【资源】{json.dumps(td.resources, ensure_ascii=False)}"
        )
        for condition in ("fixed", "free"):
            p = latest_result(task, condition)
            if not p:
                print(f"⚠ {task}-{condition}: 没有 result.json")
                continue
            r = json.loads(p.read_text(encoding="utf-8"))
            text, red = anonymize(r.get("finalText", ""), crew_names)
            entries.append({
                "task": task, "condition": condition,
                "text": text, "task_material": task_material,
                "source_run": p.parent.name,
                "redactions": red,
            })

    random.seed(20261002)
    random.shuffle(entries)
    mapping = {}
    manifest = []
    for i, e in enumerate(entries, 1):
        anon = f"卷{i:03d}"
        (OUT / f"{anon}.txt").write_text(
            f"{e['task_material']}\n\n{'=' * 40}\n\n【匿名产出】\n{e['text']}\n", encoding="utf-8"
        )
        mapping[anon] = {"task": e["task"], "condition": e["condition"], "source_run": e["source_run"]}
        manifest.append({"anon": anon, "task": e["task"], "condition": e["condition"],
                         "redactions": e["redactions"], "chars": len(e["text"])})
    Path(r"D:\aiteam-lab\blind\mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(r"D:\aiteam-lab\blind\manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    n_leak = sum(1 for m in manifest if m["redactions"])
    print(f"入卷 {len(entries)} 份（匿名卷001–{len(entries):03d}）；{n_leak} 份做过角色名抹除")


if __name__ == "__main__":
    main()
