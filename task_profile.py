# 边界画像器：给任务沿六轴打分 → 预测哪个条件赢 → 战斗验证 → 回填边界图。
#
# 这是课题 2（自由发挥 vs 固定流程的边界）的系统性工具：
#   1. python task_profile.py score <profile.json>     # 预测 + 写入 boundary_map.json
#   2. 战斗跑完后：
#      python task_profile.py update <task_id> <winner> <evidence>   # 回填结果
#   3. python task_profile.py map                      # 打印当前边界图 + 预测命中率
#
# 六轴（0-2 分，越高越强）：
#   spec_clarity     需求明确度（2=规格完整无歧义）
#   decomposability  可分解性（2=子任务独立、接口清晰）
#   verifiability    可验证性（2=有测试/标准答案/客观最优）
#   exploration      探索量（2=要多轮搜索试错、方向未知）
#   coupling         耦合度（2=强耦合，改一处动全身）
#   data_dependency  数据依赖（2=必须从给定数据推导，编造即错）
#
# 预测规则（启发式 v0，规则本身是课题 2 的研究对
# 象——战斗结果会回填校准）：
#   fixed_score  = spec_clarity*2 + decomposability*1.5 + verifiability*1.5 + data_dependency*1
#   free_score   = exploration*2.5 + (2-spec_clarity)*1.5 + (2-verifiability)*0.5 + 1.0(编排自适应基线)
#   free-shared  额外条件：coupling>=2 或 任务需要成员间共享中间产物 时，free 方 +1
import json
import sys
from pathlib import Path

MAP_PATH = Path(r"D:\aiteam-lab\boundary_map.json")

AXES = ["spec_clarity", "decomposability", "verifiability", "exploration", "coupling", "data_dependency"]


def predict(p: dict) -> dict:
    ax = p["axes"]
    fixed = (ax["spec_clarity"] * 2 + ax["decomposability"] * 1.5
             + ax["verifiability"] * 1.5 + ax["data_dependency"] * 1)
    free = (ax["exploration"] * 2.5 + (2 - ax["spec_clarity"]) * 1.5
            + (2 - ax["verifiability"]) * 0.5 + 1.0)
    shared_bonus = 0
    note = ""
    if ax["coupling"] >= 2 or p.get("needs_shared_artifacts"):
        shared_bonus = 1
        note = "强耦合/需要共享中间产物 → free-shared 可能优于 free-isolated（课题 4 待验证）"
    winner = "fixed" if fixed > free + shared_bonus else ("tie" if abs(fixed - free - shared_bonus) < 0.5 else "free")
    return {
        "task_id": p["task_id"],
        "axes": ax,
        "fixed_score": round(fixed, 2),
        "free_score": round(free + shared_bonus, 2),
        "shared_bonus": shared_bonus,
        "predicted_winner": winner,
        "judging": "objective" if ax["verifiability"] == 2 else ("machine" if ax["verifiability"] >= 1 else "blind-rubric"),
        "note": note,
    }


def cmd_score(path: str):
    p = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = [a for a in AXES if a not in p.get("axes", {})]
    if missing:
        print(f"缺少轴评分: {missing}")
        sys.exit(1)
    pred = predict(p)
    m = json.loads(MAP_PATH.read_text(encoding="utf-8")) if MAP_PATH.exists() else {"entries": {}}
    m["entries"][p["task_id"]] = {**pred, "result": m.get("entries", {}).get(p["task_id"], {}).get("result")}
    MAP_PATH.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(pred, ensure_ascii=False, indent=1))
    print(f"→ 已写入 {MAP_PATH}")


def cmd_update(task: str, winner: str, evidence: str):
    m = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    e = m["entries"].get(task)
    if not e:
        print(f"boundary_map 里没有 {task}，先 score")
        sys.exit(1)
    e["result"] = {"winner": winner, "evidence": evidence}
    e["hit"] = (e["result"]["winner"] == e["predicted_winner"])
    MAP_PATH.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{task}: 预测 {e['predicted_winner']} / 实际 {winner} → {'命中 ✓' if e['hit'] else '未命中 ✗'}")


def cmd_map():
    m = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    hits = [(t, e) for t, e in m["entries"].items() if e.get("result")]
    print("任务  | 轴(spec/dec/ver/exp/cou/dat) | 预测 | 实际 | 命中")
    print("-" * 70)
    for t, e in m["entries"].items():
        ax = e["axes"]
        r = e.get("result")
        hit = e.get("hit")
        if r and hit is None:
            hit = (r["winner"] == e["predicted_winner"])
        print(f"{t:<5} | {ax['spec_clarity']}/{ax['decomposability']}/{ax['verifiability']}/"
              f"{ax['exploration']}/{ax['coupling']}/{ax['data_dependency']}          | "
              f"{e['predicted_winner']:<5} | {r['winner'] if r else '待战斗':<5} | "
              f"{('✓' if hit else '✗') if r else '-'}")
    if hits:
        hit = sum(1 for _, e in hits if e.get("hit") or (e.get("result", {}) or {}).get("winner") == e["predicted_winner"])
        print(f"\n预测命中率：{hit}/{len(hits)}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "score":
        cmd_score(sys.argv[2])
    elif len(sys.argv) >= 4 and sys.argv[1] == "update":
        cmd_update(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    elif len(sys.argv) >= 2 and sys.argv[1] == "map":
        cmd_map()
    else:
        print(__doc__)
