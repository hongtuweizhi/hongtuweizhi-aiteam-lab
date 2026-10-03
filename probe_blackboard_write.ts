// 探针 2：把桥里 round_completed 处理器逐字复制（含 appendFileSync 落盘），
// 验证"文件写入"端到端是否可行。零 API 成本。
import { appendFileSync, existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { mkdtempSync } from "node:fs";
import { createAgentHost, createAgent } from "../Desktop/aiteam-frame/src/index.ts";
import { startFaux, sleep } from "../Desktop/aiteam-frame/test/faux-server.ts";
import { makeFauxRuntime, FAUX_MODEL_REF } from "../Desktop/aiteam-frame/test/faux-models.ts";
import { runTool } from "../Desktop/aiteam-frame/test/helpers.ts";

const faux = await startFaux();
const made = await makeFauxRuntime(faux.baseUrl);
const workDir = mkdtempSync(join(tmpdir(), "bb-probe-"));

const host = createAgentHost({ members: { worker: { description: "测试成员", tools: [] } } });
const log: string[] = [];
host.on("round_completed", ({ agent, result }: any) => {
  try {
    log.push(`event: agent=${agent.id} textLen=${String(result?.text ?? "").length} err=${result?.error ?? "null"}`);
    if (!agent || agent.id === "lead") return;
    const out = String(result?.text ?? "").trim();
    if (!out) { log.push("  skip: 空文本"); return; }
    appendFileSync(join(workDir, "blackboard.md"), `\n## [${agent.id}]\n\n${out}\n`, "utf-8");
    log.push(`  written: blackboard.md +${out.length}`);
  } catch (e: any) {
    log.push(`  handler 异常: ${e?.message}`);
  }
});

const lead = await createAgent(
  { model: FAUX_MODEL_REF, cwd: made.cwd, agentDir: made.agentDir, tools: ["spawn_agent"] },
  { host, modelRuntime: made.runtime },
);
await runTool("spawn_agent", { member: "worker", task: "echo:worker-done" }, { agent: lead, host } as never);
await sleep(300);

for (const l of log) console.log("  ", l);
const bb = join(workDir, "blackboard.md");
console.log(existsSync(bb) ? `→ 黑板写入成功 ✓ 内容=${JSON.stringify(readFileSync(bb, "utf-8").slice(0, 80))}` : "→ 黑板仍未写入 ✗");
host.dispose();
await faux.close();
