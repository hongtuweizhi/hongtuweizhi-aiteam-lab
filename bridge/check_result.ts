// 检查斗蛐蛐 result.json 的输出契约遵守情况
// 用法: node check_result.js <resultPath>
import { readFileSync } from "node:fs";
const r = JSON.parse(readFileSync(process.argv[2]!, "utf8"));
const text = r.finalText ?? "";
console.log("condition:", r.condition, "| task:", r.task_id, "| error:", r.error);
console.log("usage:", JSON.stringify(r.usage));
if (r.topology) console.log("拓扑:", r.topology.join(" → "));
if (r.spawn_count !== undefined) console.log("分身数:", r.spawn_count, JSON.stringify(r.spawned));
const m = text.match(/```json\s*([\s\S]*?)```/);
console.log("JSON 块:", m ? "有 ✓" : "无 ✗");
if (m) {
  try {
    const j = JSON.parse(m[1]);
    console.log("achieved_goals:", JSON.stringify(j.achieved_goals));
    console.log("constraints_satisfied:", JSON.stringify(j.constraints_satisfied));
    console.log("schedule 条目数:", (j.schedule ?? []).length, JSON.stringify((j.schedule ?? []).slice(0, 3)));
  } catch (e: any) {
    console.log("JSON 解析失败:", e.message);
    console.log(m[1].slice(0, 500));
  }
} else {
  console.log("—— finalText 末尾 500 字 ——");
  console.log(text.slice(-500));
}
