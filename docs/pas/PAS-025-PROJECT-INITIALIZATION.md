# PAS-025 — Project Initialization

**中文名：** 项目初始化阶段
**版本：** 0.1

## 目标

建立 PAS Alpha Foundation：一个可运行、可测试、可部署并能持续迭代的工程地基。

## 确认的技术方案

- Next.js + TypeScript + Tailwind CSS；
- FastAPI + Python；
- Supabase PostgreSQL + Auth；
- 可替换的 LLM API；
- GitHub；
- Vercel 前端；
- Render 后端；
- Cloudflare DNS 与基础防护。

## 初始化顺序

1. 创建 GitHub 仓库和忽略规则；
2. 初始化前端与基础页面；
3. 初始化后端和健康接口；
4. 验证前后端通信；
5. 设计并审查 Supabase 迁移；
6. 接入认证与 RLS；
7. 接入真实模型；
8. 部署 Preview；
9. 进入小规模 Alpha。

## 环境变量

前端只允许公开配置，例如 API URL 和 Supabase publishable key。后端保存模型密钥、数据库秘密或服务端密钥。

仓库必须包含 `.env.example`，但不得提交真实 `.env`。

## 云资源原则

- GitHub 仓库可先创建；
- Supabase、Vercel 和 Render 创建前确认组织、地区、费用与资源范围；
- Cloudflare Alpha 阶段使用免费 DNS 和基础安全；
- 不在没有真实需求前购买高级基础设施；
- 生产发布必须经过用户明确确认。

## 当前里程碑

已经建立：

- GitHub 仓库 `lssdashuaige-hue/program`；
- Next.js 前端骨架；
- FastAPI 后端骨架；
- 数据库迁移草案；
- PAS Prompt 基线；
- 架构和环境文档；
- 前端构建、后端测试和敏感信息检查。

Supabase 项目尚未创建。创建尝试因账号已达到免费项目上限而停止；不得绕过或删除其他项目，需用户先处理额度。

## 下一步

1. 固化 PAS-001～025 文档；
2. 解决 Supabase 免费项目额度；
3. 创建新加坡地区项目；
4. 审查并执行数据库 schema；
5. 连接认证与数据访问；
6. 部署首个 Preview。

## 完成标准

项目拥有可追溯设计规范、干净的 Git 历史、通过验证的基础代码、明确云资源状态和不含秘密的配置模板。
