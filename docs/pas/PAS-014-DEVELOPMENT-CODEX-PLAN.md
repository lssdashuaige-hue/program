# PAS-014 — Development Architecture & Codex Execution Plan

**中文名：** 开发架构与 Codex 执行计划
**版本：** 0.1

## 目标

将 PAS 设计转化为可分阶段构建、验证和审查的工程。Codex 是工程执行协作者，不是一次性网站生成器。

## 技术栈

- Frontend：Next.js、TypeScript、Tailwind CSS；
- Backend：Python、FastAPI；
- Database/Auth：Supabase PostgreSQL；
- LLM：可替换的模型适配层；
- Hosting：Vercel + Render；
- DNS/Security：Cloudflare；
- Source control：GitHub。

## 仓库结构

```text
frontend/       Web 界面
backend/        API、AI、安全和数据逻辑
database/       可审查的数据库迁移
prompts/        版本化 AI 行为规则
docs/           产品与工程规范
work/           本地临时工具，不提交
```

## AI 模块

- Conversation Controller；
- Context Builder；
- Memory Retrieval；
- Psychological Exploration Planner；
- Response Generator；
- Risk Detector；
- Boundary and Output Validator；
- Candidate Memory Evaluator；
- Summary Generator。

MVP 可以在一个 FastAPI 服务中保持模块化，不提前拆成微服务。

## Codex 执行规则

每项任务应说明：

1. 当前目标；
2. 相关 PAS 章节；
3. 技术边界；
4. 不在本次范围内的内容；
5. 验收标准和测试；
6. 安全、隐私与迁移影响。

开发循环：

```text
明确范围 → 独立分支 → 小步实现 → 自动验证
→ 人工审查 → 合并 → 部署验证
```

## 开发顺序

1. 工程骨架与健康检查；
2. 首页和 Reflection Room；
3. 身份验证与 RLS；
4. PAS 对话适配层；
5. 会话持久化；
6. 候选记忆和用户确认；
7. 心理地图与总结；
8. 安全评测；
9. 部署和 Alpha 反馈。

## 避免事项

- 一次生成完整产品；
- 在没有测试时引入复杂 Agent；
- 把 Prompt 硬编码在路由中；
- 在前端暴露服务密钥；
- 无迁移地直接修改生产数据库；
- 为追求“聪明”而绕过用户确认和安全边界。

## 完成定义

每个 Sprint 必须有可运行增量、明确验证结果、已知限制和可追溯提交。
