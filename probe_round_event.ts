// 探针：验证 host.on("round_completed") 对 spawn 出来的分身是否触发、result.text 是否非空。
// 用仓库自带的假 provider，零 API 成本。
// 跑法：cd D:/Desktop/aiteam-frame && node D:/aiteam-lab/probe_round_event.ts
import { createAgentHost, createAgent } from "../Desktop/aiteam-frame/src/index.ts";
import { startFaux, sleep } from "../Desktop/aiteam-frame/test/faux-server.ts";
import { makeFauxRuntime, FAUX_MODEL_REF } from "../Desktop/aiteam-frame/test/faux-models.ts";
import { runTool } from "../Desktop/aiteam-frame/test/helpers.ts";

const faux = await startFaux();
const made = await makeFauxRuntime(faux.baseUrl);

const host = createAgentHost({
  members: { worker: { description: "测试成员", tools: [] } },
});
const events: string[] = [];
host.on("agent_created", () => events.push("agent_created"));
host.on("round_completed", ({ agent, result }: any) => {
  events.push(`round_completed: agent=${agent.id} textLen=${String(result?.text ?? "").length} tok=${result?.usage?.totalTokens}`);
});
host.on("agent_disposed", () => events.push("agent_disposed"));

const lead = await createAgent(
  { model: FAUX_MODEL_REF, cwd: made.cwd, agentDir: made.agentDir, tools: ["spawn_agent"] },
  { host, modelRuntime: made.runtime },
);

// lead 用脚本假模型调一次 spawn_agent，worker 收到任务后回声
await runTool("spawn_agent", { member: "worker", task: "echo:worker-done" }, { agent: lead, host } as never);
await sleep(300);

console.log("事件序列：");
for (const e of events) console.log("  ", e);
const ok = events.some((e) => e.startsWith("round_completed") && !e.includes("agent=lead"));
console.log(ok ? "→ 分身的 round_completed 有触发 ✓" : "→ 分身的 round_completed 没触发 ✗（这就是黑板写不上的根因）");
host.dispose();
await faux.close();
