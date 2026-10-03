// 多 agent 中继曲线（确定性管道版）：
//   调用1（worker）：拿全量数据算 N 行成本表，输出 JSON —— 等价于 spawn 里的分身
//   调用2（lead）：拿到 worker 的返回文本（= spawn_agent 工具结果通道），收口输出最终 JSON
// 两段之间唯一的传递通道就是"worker 返回文本"——与真实 spawn_agent 的返回路径一致。
// 零指令方差：不依赖任何模型自觉。用法：node spawn_chain_curve.ts <N> <runIndex>
import { appendFileSync, mkdirSync } from "node:fs";
import { createAgent } from "../Desktop/aiteam-frame/src/index.ts";

const N = parseInt(process.argv[2] ?? "6", 10);
const runIdx = process.argv[3] ?? "0";
const MODEL = process.env.AITEAM_MODEL ?? "opencode-go/deepseek-v4.1-flash";
const AGENT_DIR = process.env.AITEAM_AGENT_DIR ?? "D:/aiteam-lab/agent";
const FIRST_ORDER = 1200;

// 与 t4c_checker.gen_instance 同一公式（事实源一致）
function genInstance(n: number) {
  const parts: Record<string, { per_unit: number; stock: number; price: number; lead_days: number }> = {};
  for (let i = 1; i <= n; i++) {
    parts[`P${String(i).padStart(2, "0")}`] = {
      per_unit: (i % 3) + 1,
      stock: ((i * 37) % 50) + 10,
      price: ((i * 13) % 20) + 5,
      lead_days: (i % 5) + 1,
    };
  }
  return parts;
}

function groundTruth(parts: Record<string, any>) {
  const costs: Record<string, number> = {};
  for (const [pid, p] of Object.entries(parts)) {
    costs[pid] = (FIRST_ORDER * p.per_unit - p.stock) * p.price;
  }
  return costs;
}

function num(x: any): number | null {
  const v = parseFloat(String(x ?? "").replace(/[,¥元 ]/g, ""));
  return Number.isFinite(v) ? v : null;
}

function score(text: string, costs: Record<string, number>) {
  const m = (text ?? "").match(/\{[\s\S]*\}/);
  if (!m) return { parse: false, correct: 0, total: Object.keys(costs).length };
  let data: any;
  try { data = JSON.parse(m[0]); } catch { return { parse: false, correct: 0, total: Object.keys(costs).length }; }
  const proc = data.procurement ?? data;
  let ok = 0;
  for (const [pid, c] of Object.entries(costs)) {
    const v = num(proc[pid]);
    if (v !== null && Math.abs(v - (c as number)) <= 0.5) ok++;
  }
  return { parse: true, correct: ok, total: Object.keys(costs).length };
}

const parts = genInstance(N);
const costs = groundTruth(parts);
const rows = Object.entries(parts)
  .map(([pid, p]) => `${pid}: 单台用量 ${p.per_unit}，库存 ${p.stock}，采购单价 ${p.price} 元/个`)
  .join("\n");
const taskText = `某产品首批订单 ${FIRST_ORDER} 台，需为 ${N} 个部件制定采购成本表。给定数据：\n${rows}\n\n请逐个部件计算：采购成本 = (${FIRST_ORDER} × 单台用量 − 库存) × 采购单价。\n只输出一个 JSON 对象，格式：\n\`\`\`json\n{"procurement": {"P01": <成本>, ...}}\n\`\`\`\n必须覆盖全部 ${N} 个部件。`;

const workDir = `D:/aiteam-lab/runs/spawnchain-N${N}-${runIdx}-${Date.now()}`;
mkdirSync(workDir, { recursive: true });

// 调用 1：worker 计算（等价于 spawn 分身）
const worker = await createAgent({
  id: "worker", model: MODEL, agentDir: AGENT_DIR, cwd: workDir, tools: [],
  role: "你是计算成员。严格按派工文本的要求计算并输出。",
});
const t0 = Date.now();
const workerRun = await worker.prompt(taskText);
const workerText = workerRun.text ?? "";
const workerTok = workerRun.usage?.totalTokens ?? 0;
await worker.dispose();

// 调用 2：lead 经 spawn 返回通道收口（唯一的输入就是 worker 的返回文本）
const lead = await createAgent({
  id: "lead", model: MODEL, agentDir: AGENT_DIR, cwd: workDir, tools: [],
  role: "你是主持人。你的下属 worker 刚通过 spawn_agent 返回了它的计算结果。你的任务：基于返回文本整理出最终采购成本表。",
});
const leadRun = await lead.prompt(
  `你的 worker 通过 spawn_agent 返回了以下结果：\n\n<worker_result>\n${workerText}\n</worker_result>\n\n请基于这份返回，输出最终采购成本表。你的最后一条回复必须以一个 JSON 代码块结尾，格式：\n\`\`\`json\n{"procurement": {"P01": <成本>, ...}}\n\`\`\`\n必须覆盖全部 ${N} 个部件（P01–P${String(N).padStart(2, "0")}）。`,
);
const leadText = leadRun.text ?? "";
const leadTok = leadRun.usage?.totalTokens ?? 0;
await lead.dispose();

const record = {
  ts: new Date().toISOString(), model: MODEL, n: N, run: runIdx,
  worker_score: score(workerText, costs), worker_tokens: workerTok,
  lead_score: score(leadText, costs), lead_tokens: leadTok,
  total_tokens: workerTok + leadTok,
  elapsed_s: Math.round((Date.now() - t0) / 100) / 10,
  worker_text_len: workerText.length,
};
const out = "D:/aiteam-lab/spawn_chain_results.jsonl";
appendFileSync(out, JSON.stringify(record) + "\n", "utf-8");
console.log(JSON.stringify(record));
