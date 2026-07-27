# PAS-015 — Initial Development Sprint

**中文名：** 第一轮开发冲刺
**版本：** 0.1

## Sprint 目标

建立 PAS Alpha 的可运行技术骨架，证明浏览器、后端和数据库能够形成最小闭环。

## 交付范围

### GitHub

- 单一仓库管理前端、后端、迁移、Prompt 和文档；
- 环境文件和本地工具被忽略；
- 初始提交通过构建和测试。

### Frontend

- Next.js + TypeScript；
- 首页和 `/explore` 路由；
- Reflection Room 基础组件；
- 后端 URL 使用环境变量；
- 基础响应式设计。

### Backend

- FastAPI 应用；
- `GET /health`；
- `POST /chat` 的确定性脚手架回应；
- CORS、配置和错误处理基础；
- Pytest 健康检查。

### Database

- Supabase 迁移草案；
- conversations、messages、memories 和 themes 等基础表；
- RLS 与用户所有权策略；
- 不在仓库保存真实连接密钥。

## 验收标准

- `npm run lint` 通过；
- `npm run build` 通过；
- 后端测试通过；
- `/health` 返回运行状态；
- `/explore` 可发送输入并显示后端回应；
- 数据库迁移经过安全审查后可重复执行；
- 没有诊断、人格分析或未经确认的长期记忆。

## 非目标

- 真实 LLM 接入；
- 完整认证 UI；
- 自动心理地图；
- 支付、社区和移动 App；
- 生产级扩缩容。

## 当前实现说明

仓库中的初始 Alpha 骨架已经完成前端生产构建、后端健康测试和敏感信息扫描。真实云资源和 AI 适配仍需后续 Sprint。
