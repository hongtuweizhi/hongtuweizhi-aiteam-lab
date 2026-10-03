# aiteam-frame 问题草稿（待审阅后提交）

> 以下 4+1 条均在斗蛐蛐实验室实测复现（2026-10-02 ~ 10-03，约 35 次运行、3 个模型厂家）。
> 每条独立成 issue。提交前建议把"复现"部分精简为最小脚本——必要时可以把实验室探针
> 改写成仓库 `audit/` 风格的一次性脚本（假 provider，零成本）。

---

## Issue 1：provider 限流 429 被 prompt() 吞成"零 token 空成功"

**标题**：prompt() 在 provider 返回 429 时不抛错，静默返回空结果（error=null、tokens=0）

**层级**：根因在 pi SDK 的请求层；aiteam-frame 的 `ControlledAgent.prompt` 直接暴露该行为。

**实测现象**（deepseek-v4.1-flash @ opencode-go，GoUsageLimitError 期间）：
- `await agent.prompt("...")` 约 1.2 秒返回，`result.text === ""`
- `result.usage.totalTokens === 0`，`result.error === null`，不抛异常
- 同一时刻直接 curl 同端点得到 `HTTP 429 {"type":"error","error":{"type":"GoUsageLimitError"}}`

**为什么有害**：调用方无法区分"模型真的回了空"和"被限流"。我们的多 agent 实验里，
这类运行曾以"成功"身份混进数据集（某 agent 0 token 空返回，导致 lead 空转等待）。

**期望**：至少在 `result.error` 里带上限流信息；或提供 `result.silentFailure: true` 之类的标志。
理想：429 抛错（可重试类），与"模型真空回复"区分开。

**复现**：任一会被限流的 key + 最小 prompt；对照 curl 同端点的原始响应。

---

## Issue 2：分身级静默失败——worker 0 token 返回无 error，宿主级观测看不见

**标题**：分身轮次可能 0 token 空返回且无任何 error 信号，宿主 usage 与事件都看不出异常

**实测现象**（forceSpawn=3 的三 worker 编排，6 部件任务）：
- lead 通过 spawn_agent 派工后，分身 a1 的轮次 0 token 返回、无 error
- `host.usage.totalTokens` 只累计到 8,192（全部来自 lead），宿主侧完全看不到 a1 异常
- lead 只能输出"等待 analyst 重试"，任务失败但全程无错误信号

**为什么有害**：多 agent 编排里这是致命盲区——宿主的预算/观测都在聚合层，
一个分身挂了，lead 与设计者都收不到信号，任务静默劣化成"部分完成"。

**期望**：分身轮次 0 token（或 finish 异常）时至少发一个宿主事件（如 `agent_round_anomaly`）；
`spawn_agent` 的返回文本里附上该轮的 error/usage 摘要，让 lead 有机会换策略。

**复现**：假 provider 脚本化"worker 轮返回空"即可稳定复现（test/faux-server.ts 加一个
`[[empty]]` 标记就行）。

---

## Issue 3：协作协议的指令优先级——lead 派工文本会压倒成员 role

**标题**：spawn 派工文本与成员 role 冲突时，派工文本赢——结构性的协议注入需求

**实测现象**（同一任务、同一模型、4 次迭代）：
1. 成员 description 写"把结果写入共享黑板 blackboard.md" → 0/3 场次写入；
2. lead 派工文本转述"完成后把结果写入黑板" → 仍不写（派工文本自己的"返回结果"要求赢）；
3. 成员 role 系统注入"必须先写黑板再返回" → 12 部件任务上仍不写（大任务下指令被淹没）；
4. **桥层监听 `round_completed` 事件、由框架代码直接落盘 → 3/3 worker 全部写入** ✓。

**为什么有害**：多 agent 协作协议（共享状态、审批、留痕）如果靠"提示词要求"传递，
可靠性随任务规模下降；这是使用者在真跑里最先撞的墙。

**期望/建议**：aiteam-frame 可考虑一等公民的"结构保证"原语——例如
`members[x].onComplete: "append-to-blackboard"` 或宿主级 `round_completed` 钩子的官方配方
（事件系统已经有了，缺的是把"自动落盘"做成文档化的模式）。实验室验证过的桥层实现：
`host.on("round_completed", ({agent, result}) => appendFileSync(blackboard, result.text))`，
十余行，可靠。

---

## Issue 4：上下文超限的静默空产出（已有审计结论）在多 agent 下的放大效应

**标题**：分身上下文超限静默空产出，在多 agent 编排下被放大成任务级失败

**实测现象**：40 部件任务、3 分身编排：单分身大产出叠加 lead 汇总轮，lead 上下文膨胀后
推理档模型把 maxTokens 全部烧在思考上、正文为空（我们两次踩中，一次直接 1800s 无产出超时）。
审计已记录"上下文超限=永久静默返回空"；多 agent 下它还会**级联**：lead 收到空产出 →
重新派工 → 新分身同样失败 → 循环烧预算。

**期望**：超限时抛错或至少 `result.error` 标注（同 Issue 1 的诉求）；
`spawn_agent` 返回里带分身的 error，让 lead 的重试决策有依据。

---

## 附：一条正面发现（可作为 GUIDE 素材）

**单道 spawn 边界的中继是无损的**：确定性管道实测（worker 算 → 返回文本经 spawn_agent
通道 → lead 收口），N=4–12 数据行、12 字段逐行核对，lead 侧 100% 保真，每链仅约 2.3k tokens。
——aiteam-frame 的 spawn 返回通道本身值得信赖；多 agent 的失败来自"多分身并行 + 汇总"
的编排复杂度，不是通道。这可以直接写进 GUIDE 的"何时该拆分身"一节。

---

## 提交顺序建议

1. Issue 1（影响所有用户，最值得先提）
2. Issue 2（多 agent 用户的核心盲区）
3. Issue 3（含正面建议，jerphy 大概率欢迎）
4. Issue 4（与审计报告既有结论合并提，引用 audit/ 既有编号）
