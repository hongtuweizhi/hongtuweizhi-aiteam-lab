# T-D 设计稿：动态上下文门控原语（aiteam-frame 功能提案）

> 状态：设计稿（2026-10-03）。原型已在实验室桥层验证
> （T4c12 静态全失败规模上 12/12 恢复满分，成本 1/30，见 REPORT.md「T-D 原型验证成功」）。
> 本文把它从"桥的硬编码"上移为 aiteam-frame 的任务级声明原语。

## 1. 动机（三条实测）

1. **指令式共享不可靠**：让分身"把结果写黑板"，三级递进的提示词强制
   （成员描述 → lead 派工转述 → role 系统注入）在 12 部件任务上全部失效（0/3 激活）；
   事件驱动的结构落盘 3/3 成功。协作协议不能走提示词。
2. **静态隔离/全共享都有失效规模**：12 行数据链，隔离 1.61M tokens 0/12、
   结构共享 116k tokens 0/12；而动态阶段门控（写时隔离、读时共享）51k tokens 12/12。
3. **spawn 返回通道无损**（确定性管道实测 N=4–12 全绿）：单道中继不是瓶颈，
   需要管理的是"谁能看什么、在什么阶段"。

## 2. 原语设计

### 2.1 `members[x].contextPolicy`（成员级上下文策略）

```ts
const host = createAgentHost({
  members: {
    analyst: {
      description: "独立核算",
      model: "...",
      contextPolicy: {
        spawn:  ["task"],            // spawn 时注入：仅任务数据（隔离计算，防污染）
        onRoundEnd: "blackboard",    // 轮次结束：框架自动把产出落盘黑板（结构保证）
        spawnRead: "none",           // 本成员 spawn 时不读黑板
      },
    },
    synthesizer: {
      description: "交叉核对汇总",
      model: "...",
      contextPolicy: {
        spawn:  ["task", "blackboard"],  // 汇总者 spawn 时：任务 + 黑板全文（读时共享）
        onRoundEnd: "none",
        spawnRead: "blackboard",
      },
    },
  },
});
```

语义：
- `spawn: ["task" | "blackboard" | "verdicts"]`——框架在 spawn 时自动注入哪些内容块，
  lead 的派工文本因此只需携带"子任务差异"（甚至可以完全省略，见 2.2）；
- `onRoundEnd: "blackboard"`——轮次产出由框架落盘，等价于本实验室验证过的
  `host.on("round_completed")` 桥层实现，但成为声明式配置；
- `spawnRead` 与 `spawn` 的区别：前者控制黑板读权限，后者控制注入。
- **默认值即现状**（不声明 = 无策略，行为与 0.9.x 完全兼容）。

### 2.2 审查门（`host.reviewGate`，可选增强）

多轮审查场景：分身轮次结束后，宿主暂停，审查者（人或只读 agent）在侧信道审阅
思考链（`thinking` 事件已在事件流中分离），框架只把 **verdict（一行）** 注回下一轮——
审查链的篇幅与被审查者上下文完全隔离。

```ts
host.on("round_review", async ({ agent, result, sideChannel }) => {
  // sideChannel：本分身全部轮次的产出与思考（供审查，不进任何上下文）
  return { verdict: "pass" | "fix", note: "第 3 行与数据不符" };
});
```

框架行为：verdict=fix 时，框架 dispose 该分身并以
`原任务 + verdict.note + blackboard 状态` 重新 spawn（"重生成而非续会话"，
规避续会话的上下文滚雪球——实测 1.6M token 螺旋的解法）。

### 2.3 与现有红线的相容性

- 不违反"agent 不能配置 agent"：contextPolicy 是**设计者**在花名册里声明的，
  agent 无权限修改（spawn_agent 依旧只传 member + task）；
- `spawn_agent` 工具签名不变；注入内容由宿主按声明执行；
- 事件系统零新增（复用 `round_completed` / `agent_created`），只加配置语义。

## 3. 验证计划（原语落地后）

1. 回归：既有 demo 与 76 项测试全绿（默认值兼容）；
2. 用原语重跑实验室 T4c12 动态对照（应复现 12/12 @ ~51k）；
3. 指令式 vs 声明式的激活率对照（预期：声明式 3/3 vs 指令式 0/3，与桥层一致）；
4. 审查门：多轮返修场景的上下文体积对比（重生成 vs 续会话）。

## 4. 落地路径建议

- 第一步：只做 `contextPolicy.spawn/onRoundEnd`（约几十行，事件系统已就绪），
  配 GUIDE 一节"何时该拆分身 / 怎么共享状态"；
- 第二步：`reviewGate`（需要宿主暂停语义，工程量较大）；
- 第三步：门控规则的任务级声明进 `TASK_DEFINITIONS` 一类结构（跨框架泛化）。

## 5. 实验室参考实现

- 桥层：`bridge/aiteam_battle.ts` 的 `runDynamic()`（阶段门控）与
  `round_completed` 自动落盘（结构保证）；
- 探针：`audit/verify-structural-blackboard.ts`（已提交 fork 分支）、
  `probe_blackboard_write.ts`、`probe_round_event.ts`。
