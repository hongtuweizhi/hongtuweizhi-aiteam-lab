// 斗蛐蛐桥：aiteam-frame × REALM-Bench
// 用法：node aiteam_battle.ts <spec.json>
// spec: {
//   condition: "fixed" | "free",
//   model: "opencode-go/deepseek-v4.1-flash",
//   agentDir: "D:/aiteam-lab/agent",
//   workDir: "D:/aiteam-lab/runs/<run>",   // 本次运行的独立工作目录
//   task: { id, description, goals: [{id, description}], constraints: [{id, type, parameters}], resources },
//   crew?: { agents: [...], edges: [[from, to]] },  // fixed 必填（来自 notebook 抽取）
//   budgetTokens?: number,                  // free 条件的安全天花板
//   resultPath: "..."                       // 结果 JSON 落这里
// }
import { appendFileSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { createAgent, createAgentHost } from "../../Desktop/aiteam-frame/src/index.ts";

const spec = JSON.parse(readFileSync(process.argv[2]!, "utf8"));

// 两个条件共用的输出契约（同一把尺子）+ id 词表（fixed 的中间角色看不到任务
// 原文，末端节点需要词表才能"逐字挑选"；free 的 lead 在任务文本里已见到）
const OUTPUT_CONTRACT = `

【输出格式（硬性要求）】
你的最后一条回复必须以一个 JSON 代码块结尾，形如：
\`\`\`json
{
  "achieved_goals": ["<goal id>", "..."],
  "constraints_satisfied": ["<constraint id>", "..."],
  "schedule": [{"task": "<事项>", "start": <小时数>, "end": <小时数>}, "..."]
}
\`\`\`
规则：
1. achieved_goals 只能从任务给出的 goal id 里**逐字**挑选你确实达成的（如 visit_all_locations）；
2. constraints_satisfied 同理；
3. schedule 给出最终计划的时间表，start/end 用小时数（例如 9.5 表示 9:30）；
4. JSON 之前可以先给分析过程。`;

function idVocab(t: any): string {
  const goals = t.goals.map((g: any) => `- ${g.id}：${g.description}`).join("\n");
  const cons = t.constraints.map((c: any) => `- ${c.id}`).join("\n");
  return `\n【可选 goal id 词表（逐字使用）】\n${goals}\n【可选 constraint id 词表（逐字使用）】\n${cons}`;
}

// 实际生效的输出契约：任务可在 spec.outputContract 覆盖默认（如 T4c 的采购表契约）
const CONTRACT = spec.outputContract ?? OUTPUT_CONTRACT;

// 任务文本渲染（对齐 run_evaluation 的模板，但 goals/constraints 带 id）
function taskText(t: any): string {
  const goals = t.goals.map((g: any) => `- ${g.id}: ${g.description}`).join("\n");
  const cons = t.constraints
    .map((c: any) => `- ${c.id} (${c.type}): ${JSON.stringify(c.parameters)}`)
    .join("\n");
  return `Task: ${t.description}\n\nGoals:\n${goals}\n\nConstraints:\n${cons}\n\nResources: ${JSON.stringify(t.resources)}`;
}

function newUsage() {
  return { calls: 0, totalTokens: 0, costTotal: 0 };
}
function addUsage(acc: any, u: any) {
  acc.calls += 1;
  acc.totalTokens += u?.totalTokens ?? 0;
  acc.costTotal += u?.cost?.total ?? 0;
}

// ───────────────────────── A 路：固定流程 ─────────────────────────
// 1:1 复刻论文 src/multi_agent：backstory 当 system、拓扑序执行、
// 前驱输出按「<接收者> received context: \n<输出>」累进、create_prompt 模板逐字保留。
async function runFixed() {
  const crew = spec.crew;
  const n = crew.agents.length;
  const indeg = new Array(n).fill(0);
  const succ: number[][] = Array.from({ length: n }, () => []);
  for (const [f, t] of crew.edges) {
    succ[f].push(t);
    indeg[t]++;
  }
  const order: number[] = [];
  const q = crew.agents.map((_: any, i: number) => i).filter((i) => indeg[i] === 0);
  while (q.length) {
    const x = q.shift()!;
    order.push(x);
    for (const t of succ[x]) if (--indeg[t] === 0) q.push(t);
  }
  if (order.length !== n) throw new Error("crew 配置有环，无法拓扑排序");

  const outputs: string[] = new Array(n);
  const agentRecords: any[] = [];
  const usage = newUsage();

  for (const idx of order) {
    const a = crew.agents[idx];
    let context = "";
    for (const [f, t] of crew.edges) {
      if (t === idx) context += `${a.name} received context: \n${outputs[f]}\n`;
    }
    // 论文 create_prompt 模板（逐字保留）；末端节点追加输出契约（与 free 条件同一把尺子）
    const isTerminal = succ[idx].length === 0;
    const prompt = `You are an AI agent. You are part of a team of agents working together to complete a task.
I'm going to give you the task description enclosed in <task_description></task_description> tags. I'll also give
you the available context from the other agents in <context></context> tags. If the context
is not available, the <context></context> tags will be empty. You'll also receive the task
expected output enclosed in <task_expected_output></task_expected_output> tags. With all this information
you need to create the best possible response, always respecting the format as describe in
<task_expected_output></task_expected_output> tags. If expected output is not available, just create
a meaningful response to complete the task.

<task_description>
${a.task_description}
</task_description>

<task_expected_output>
${a.task_expected_output}
</task_expected_output>

<context>
${context}
</context>

Your response:${isTerminal ? CONTRACT + idVocab(spec.task) : ""}`;

    const agent = await createAgent({
      id: `crew-${idx}`,
      model: spec.model,
      role: a.backstory,
      agentDir: spec.agentDir,
      cwd: spec.workDir,
      // crew 配置里带工具的角色（如 Writer 的 write_str_to_txt）接 pi 的 write
      tools: a.tools && a.tools.length ? ["write"] : [],
    });
    const started = Date.now();
    const { text, usage: u } = await agent.prompt(prompt);
    outputs[idx] = text;
    addUsage(usage, u);
    agentRecords.push({
      index: idx,
      name: a.name,
      elapsed_s: (Date.now() - started) / 1000,
      usage: u,
      output: text,
    });
    await agent.dispose();
  }

  let finalText = outputs[order[order.length - 1]];
  // 兜底：末端角色若按任务要求把 JSON 写进了文件（如 ./p1_output.json），
  // 而回复正文里没有 JSON 块，则读工作目录里最新写出的 JSON 文件当最终产出。
  if (!/```json/.test(finalText)) {
    const { readdirSync, statSync } = await import("node:fs");
    const files = readdirSync(spec.workDir)
      .filter((f: string) => f.endsWith(".json"))
      .map((f: string) => ({ f, m: statSync(`${spec.workDir}/${f}`).mtimeMs }))
      .sort((a: any, b: any) => b.m - a.m);
    if (files.length) {
      finalText += `\n\`\`\`json\n${readFileSync(`${spec.workDir}/${files[0].f}`, "utf-8")}\n\`\`\``;
    }
  }
  return { finalText, usage, agentRecords, topology: order.map((i) => crew.agents[i].name) };
}

// ───────────────────────── B 路：自由集群 ─────────────────────────
// 同一模型、同一任务文本、同一输出契约；编排方式（拆不拆、开几个分身、怎么分工）
// 完全交给 lead 自己决定。
// spec.shared=true 时切共享黑板形态（课题 4）：worker 带 read/write，
// 全队同 cwd，通过 blackboard.md 共享中间结果；false = 默认全隔离。
async function runFree() {
  // 上下文策略三档（课题 4 / 导师指导的混合模式）：
  //   isolated：黑板不存在，worker 只写 write（其实没有共享面）
  //   shared   ：黑板全开放（读共同上下文 + 写一切）
  //   mixed    ：读共享/写隔离——黑板承载共同上下文与各成员最终结论，思考过程私有
  const policy = spec.contextPolicy ?? (spec.shared ? "shared" : "isolated");
  const sharing = policy !== "isolated";
  const mixed = policy === "mixed";
  // 花名册可由 spec.members 覆盖（如 T4c 的 analyst/auditor 分工）；默认单一 worker
  const roster = spec.members ?? {
    worker: {
      description: mixed
        ? "通用规划/执行成员：承担任务的一个子部分；blackboard.md 是全队共同上下文——读取它，完成子任务后把最终结论写上去"
        : sharing
          ? "通用规划/执行成员：承担任务的一个子部分；工作目录里的 blackboard.md 是全队共享黑板，读写你的中间结果与结论"
          : "通用规划/执行成员：承担任务的一个子部分并返回结果文本",
      model: spec.model,
      tools: spec.workerTools ?? (sharing ? ["read", "write"] : ["write"]),
      ...(mixed ? { role: "你是执行成员。你的思考过程是私有的——绝不写入任何文件。完成子任务后，只把最终结论（而非推理过程）追加写入工作目录的 blackboard.md，然后返回一行摘要。" } : {}),
    },
  };
  const host = createAgentHost({
    members: roster,
    // 硬约束：forceSpawn=N 时总实例数（含 lead）钉死为 N+1——第 N+1 次 spawn 会被
    // 库护栏直接拒绝，lead 无法进入"再派分身修复"循环
    maxAgents: spec.forceSpawn ? spec.forceSpawn + 1 : (spec.maxAgents ?? 16),
    maxDepth: 2,
    budgetTokens: spec.budgetTokens ?? 1_500_000,
  });

  const spawned: string[] = [];
  host.on("agent_created", ({ agent }: any) => spawned.push(agent.id));

  // 结构保证型共享（课题 4）：worker 每轮产出由桥自动追加到 blackboard.md——
  // 写入不经过模型裁量（指令型共享三级失效的教训）；lead 与下游成员从黑板读。
  if (sharing) {
    host.on("round_completed", ({ agent, result }: any) => {
      const dbg: any = { ts: new Date().toISOString(), agent: agent?.id, textLen: String(result?.text ?? "").length, error: result?.error ?? null };
      try {
        if (!agent || agent.id === "lead") { dbg.skip = "lead"; throw new Error("__skip__"); }
        const out = String(result?.text ?? "").trim();
        if (!out) { dbg.skip = "空文本"; throw new Error("__skip__"); }
        appendFileSync(
          join(spec.workDir, "blackboard.md"),
          `\n## [${agent.id}] ${new Date().toISOString()}\n\n${out}\n`,
          "utf-8",
        );
        dbg.written = out.length;
      } catch (e: any) {
        if (e?.message !== "__skip__") dbg.appendError = String(e?.message ?? e);
      }
      try { appendFileSync(join(spec.workDir, "blackboard_debug.jsonl"), JSON.stringify(dbg) + "\n", "utf-8"); } catch { }
    });
  }

  const LEAD_ROLE = (sharing
    ? `你是主持人（lead）。你会收到一个规划任务。你可以：
- 直接自己完成；或
- 用 spawn_agent 从花名册挑选成员、把子任务交给它们（可以开多个分身，也可以给不同成员不同指示），
  用 send_message 给已有分身追加消息，最后由你汇总裁决。
工作目录里的 blackboard.md 是全队${mixed
      ? "共同上下文：把任务书与共同要求写入其中；成员只把最终结论写上去，思考过程不上黑板"
      : "共享黑板：把任务关键信息写入其中，成员可以读写它来共享中间结果"}。`
    : `你是主持人（lead）。你会收到一个规划任务。你可以：
- 直接自己完成；或
- 用 spawn_agent 从花名册挑选成员、把子任务交给它们（可以开多个分身，也可以给不同成员不同指示），
  用 send_message 给已有分身追加消息，最后由你汇总裁决。`)
    + (spec.forceSpawn
      ? `\n\n【硬性编排要求】不许自己单独完成全部工作：你必须用 spawn_agent 把任务拆解给恰好 ${spec.forceSpawn} 个成员（spawn_agent 恰好调用 ${spec.forceSpawn} 次），每次派一个明确的子任务，并把该子任务需要的全部信息写进派工文本。全部成员完成后由你汇总裁决。`
        + (sharing
          ? `\n【黑板协议（必须执行）】你派出的每个成员，其子任务完成后都会把产出写入工作目录的 blackboard.md${mixed ? "（只写最终结论，不写思考过程）" : ""}——你在派工文本里必须明确要求：「完成后把你的最终结论写入 blackboard.md」。下游成员的派工文本里必须写明：「从 blackboard.md 读取你需要的上游结果」。汇总前你自己也要读一遍 blackboard.md 核对。`
          : "")
      : `\n如何编排完全由你决定：没有规定必须拆分，也没有规定不许拆分。`);

  const lead = await createAgent({
    id: "lead",
    model: spec.model,
    role: LEAD_ROLE,
    agentDir: spec.agentDir,
    cwd: spec.workDir,
    tools: ["spawn_agent", "send_message"],
  }, { host });

  const started = Date.now();
  const { text, usage: leadUsage } = await lead.prompt(taskText(spec.task) + CONTRACT);

  const usage = newUsage();
  addUsage(usage, leadUsage);
  const instRecords: any[] = [
    { id: "lead", usage: leadUsage, output: text },
  ];
  for (const inst of host.list()) {
    const u = (inst as any).usage;
    if (u && inst.id !== "lead") {
      addUsage(usage, u);
      instRecords.push({ id: inst.id, member: (inst as any).member, usage: u });
    }
  }
  const elapsed_s = (Date.now() - started) / 1000;

  const out: any = {
    finalText: text,
    usage,
    spawned,
    spawn_count: spawned.length,
    forceSpawn: spec.forceSpawn ?? null,
    spawn_compliant: spec.forceSpawn ? spawned.length === spec.forceSpawn : null,
    elapsed_s,
    instances: instRecords,
  };
  await host.dispose();
  return out;
}

// ───────────────────────── solo：单 agent 基线 ─────────────────────────
// 导师版对比的"分别"组：一个智能体独立完成整个任务，无花名册、无派工。
async function runSolo() {
  const agent = await createAgent({
    id: "solo",
    model: spec.model,
    role: "你是独立的执行者，独立完成整个任务。",
    agentDir: spec.agentDir,
    cwd: spec.workDir,
    tools: [],
  });
  const started = Date.now();
  const { text, usage: u } = await agent.prompt(taskText(spec.task) + CONTRACT);
  const usage = newUsage();
  addUsage(usage, u);
  const out: any = {
    finalText: text,
    usage,
    spawned: ["solo"],
    spawn_count: 1,
    elapsed_s: (Date.now() - started) / 1000,
    instances: [{ id: "solo", usage: u, output: text }],
  };
  await agent.dispose();
  return out;
}

// ───────────────────────── dynamic：阶段门控（T-D 原型）─────────────────────────
// 写时隔离、读时共享：第一波 K 个核算员完全隔离并行（多样性 + 防污染），
// 桥结构化收集全部产出写入黑板；第二波汇总者拿共享读权限核对出最终答案。
// 隔离度按阶段动态切换，由桥确定性执行——零决策方差。
async function runDynamic() {
  const K = spec.forceSpawn ?? 3;
  const usage = newUsage();
  const stageRecords: any[] = [];
  const started = Date.now();
  const results: string[] = [];

  for (let i = 0; i < K; i++) {
    const a = await createAgent({
      id: `analyst-${i + 1}`,
      model: spec.model,
      role: `你是第 ${i + 1} 号独立核算员。与其他核算员完全隔离，独立完成全部计算——不要猜测别人的答案，只相信自己的计算。`,
      agentDir: spec.agentDir,
      cwd: spec.workDir,
      tools: spec.dynamicTools ?? (spec.seedFiles?.length ? ["read", "bash"] : []),
    });
    const t0 = Date.now();
    const { text, usage: u } = await a.prompt(taskText(spec.task) + CONTRACT);
    results.push(text ?? "");
    addUsage(usage, u);
    stageRecords.push({ stage: `analyst-${i + 1}`, tokens: u?.totalTokens ?? 0, elapsed_s: (Date.now() - t0) / 1000, output: text });
    appendFileSync(join(spec.workDir, "blackboard.md"),
      `\n## [analyst-${i + 1}] 独立核算结果\n\n${text ?? ""}\n`, "utf-8");
    await a.dispose();
  }

  const synthesizer = await createAgent({
    id: "synthesizer",
    model: spec.model,
    role: `你是汇总者。你有 ${K} 份来自独立核算员的隔离核算结果（已写入你的输入）。
它们可能有分歧或各自的错误。你的任务：逐部件交叉核对三份结果，不一致时用任务原始数据重新验算，
输出唯一一份最终答案。你的最后一条回复必须以指定格式的 JSON 代码块结尾。`,
    agentDir: spec.agentDir,
    cwd: spec.workDir,
    tools: spec.synthTools ?? (spec.seedFiles?.length ? ["read", "bash"] : []),
  });
  const t1 = Date.now();
  const synthPrompt = `原始任务如下：

${taskText(spec.task)}

以下是 ${K} 份独立核算结果：

${results.map((r, i) => `<result_${i + 1}>\n${r}\n</result_${i + 1}>`).join("\n\n")}

请交叉核对并输出最终答案。${CONTRACT}`;
  const { text: finalText, usage: su } = await synthesizer.prompt(synthPrompt);
  addUsage(usage, su);
  stageRecords.push({ stage: "synthesizer", tokens: su?.totalTokens ?? 0, elapsed_s: (Date.now() - t1) / 1000, output: finalText });
  await synthesizer.dispose();

  return {
    finalText,
    usage,
    spawned: Array.from({ length: K }, (_, i) => `analyst-${i + 1}`).concat(["synthesizer"]),
    spawn_count: K + 1,
    topology: Array.from({ length: K }, (_, i) => `analyst-${i + 1}`).concat(["synthesizer"]),
    stageRecords,
    elapsed_s: (Date.now() - started) / 1000,
  };
}

// ───────────────────────── 主流程 ─────────────────────────
mkdirSync(spec.workDir, { recursive: true });
// 任务种子文件（如 T4c 的 stock/needs/prices.json）：运行前写进工作目录
for (const f of spec.seedFiles ?? []) writeFileSync(join(spec.workDir, f.name), f.content, "utf-8");
const started = Date.now();
let result: any;
try {
  result = spec.condition === "fixed" ? await runFixed()
    : spec.condition === "solo" ? await runSolo()
    : spec.contextPolicy === "dynamic" ? await runDynamic()
    : await runFree();
  result.condition = spec.contextPolicy === "dynamic" ? "dynamic" : spec.condition + (spec.shared ? "-shared" : "");
  result.shared = !!spec.shared;
  result.task_id = spec.task.id;
  result.model = spec.model;
  result.elapsed_s = result.elapsed_s ?? (Date.now() - started) / 1000;
  result.error = null;
  // 静默失败检测：pi 的 prompt() 会把 provider 429 吞成"零 token 空产出"（实测 2026-10-03），
  // 这种运行必须标记为基建失败，不能当作数据点
  if (!result.error && result.condition !== "fixed" && (result.usage?.totalTokens ?? 0) === 0) {
    result.error = "silent-empty: 0 tokens（疑似 provider 限流被静默吞掉，本运行无效）";
  }
} catch (e: any) {
  result = {
    condition: spec.condition,
    task_id: spec.task.id,
    model: spec.model,
    elapsed_s: (Date.now() - started) / 1000,
    finalText: "",
    usage: newUsage(),
    error: String(e?.stack ?? e),
  };
}
writeFileSync(spec.resultPath, JSON.stringify(result, null, 1), "utf-8");
console.log(JSON.stringify({ ok: !result.error, usage: result.usage, elapsed_s: result.elapsed_s }));
