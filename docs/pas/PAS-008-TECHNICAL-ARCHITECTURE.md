# PAS-008 — Technical Architecture

**中文名：** 技术架构设计
**版本：** 0.1

## 技术目标

PAS 不是“输入文字—调用模型—返回答案”的包装层。系统必须支持持续对话、相关记忆、心理探索规则、安全检查、用户确认和可审计的数据更新。

## Alpha 架构

```text
Browser
  → Next.js / TypeScript frontend
  → FastAPI backend
     → conversation context
     → memory retrieval
     → psychological exploration policy
     → risk and boundary checks
     → LLM adapter
     → output validation
     → candidate memory evaluation
  → Supabase PostgreSQL + Auth
```

部署目标：

- 前端：Vercel；
- 后端：Render；
- 数据库与认证：Supabase；
- DNS 与基础防护：Cloudflare Free；
- 代码与审查：GitHub。

## 前端职责

- 首页、登录、Reflection Room、历史、心理地图和隐私设置；
- 只接收可公开配置；
- 不保存服务端密钥；
- 清晰展示记忆来源、置信度和确认状态；
- 支持响应式与可访问性。

## 后端职责

- 验证用户身份和资源所有权；
- 构建最小必要上下文；
- 调用模型和安全检查；
- 保存会话与候选记忆；
- 处理用户确认、修正和删除；
- 记录不含敏感正文的运行审计信息。

## 数据职责

核心实体：

- profiles；
- conversations；
- messages；
- memories；
- themes；
- pattern evidence；
- summaries；
- model versions；
- consent and audit records。

公开 schema 中的所有用户数据表必须启用 RLS，并按 `auth.uid()` 限制所有权。服务端密钥永远不能进入浏览器。

## AI 管线

```text
输入风险检测
→ 相关记忆检索
→ 当前探索规划
→ 回应生成
→ 输出边界检查
→ 保存消息
→ 形成候选记忆
→ 等待用户确认
```

MVP 可先使用规则与 LLM 结构化输出，不需要自训练模型或复杂 Agent。

## 非功能要求

- 所有网络传输使用 HTTPS；
- 配置通过环境变量注入；
- 敏感日志最小化；
- API 具备超时、错误处理和基础限流；
- 数据迁移可重放、可审查；
- AI Prompt 独立版本管理；
- 关键安全路径有自动化测试。
