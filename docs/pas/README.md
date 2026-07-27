# PAS 设计与工程规范

本目录保存 Psychological AI System（PAS）的正式设计基线。它将早期产品讨论整理为可审查、可实现、可版本化的规范。

PAS 的核心承诺是：

> 不定义用户，而是帮助用户逐渐形成理解自己的能力。

## 文档地图

### 理念与心理模型

1. [PAS-001 Psychological AI Manifesto](PAS-001-MANIFESTO.md)
2. [PAS-002 Core Psychological Model](PAS-002-CORE-PSYCHOLOGICAL-MODEL.md)
3. [PAS-003 AI Interaction Architecture](PAS-003-AI-INTERACTION-ARCHITECTURE.md)
4. [PAS-004 Psychological Knowledge Framework](PAS-004-PSYCHOLOGICAL-KNOWLEDGE-FRAMEWORK.md)

### 产品、记忆与安全

5. [PAS-005 User Experience Architecture](PAS-005-USER-EXPERIENCE-ARCHITECTURE.md)
6. [PAS-006 AI Memory & Personal Model System](PAS-006-MEMORY-PERSONAL-MODEL.md)
7. [PAS-007 Safety & Ethical Framework](PAS-007-SAFETY-ETHICAL-FRAMEWORK.md)

### 工程、验证与商业

8. [PAS-008 Technical Architecture](PAS-008-TECHNICAL-ARCHITECTURE.md)
9. [PAS-009 MVP Product Design & Roadmap](PAS-009-MVP-ROADMAP.md)
10. [PAS-010 Evaluation System](PAS-010-EVALUATION-SYSTEM.md)
11. [PAS-011 Business & Sustainability Model](PAS-011-BUSINESS-SUSTAINABILITY.md)
12. [PAS-012 Brand Identity & Positioning](PAS-012-BRAND-POSITIONING.md)
13. [PAS-013 Product Requirements Document](PAS-013-PRD.md)
14. [PAS-014 Development Architecture & Codex Plan](PAS-014-DEVELOPMENT-CODEX-PLAN.md)
14.5. [PAS-014.5 Development Environment Setup](PAS-014.5-DEVELOPMENT-ENVIRONMENT.md)
15. [PAS-015 Initial Development Sprint](PAS-015-INITIAL-DEVELOPMENT-SPRINT.md)

### AI、个人模型与前端实现

16. [PAS-016 AI Core Implementation](PAS-016-AI-CORE-IMPLEMENTATION.md)
17. [PAS-017 Memory & Personal Model Implementation](PAS-017-MEMORY-MODEL-IMPLEMENTATION.md)
18. [PAS-018 Safety Guardrails Implementation](PAS-018-SAFETY-GUARDRAILS.md)
19. [PAS-019 Frontend Experience Implementation](PAS-019-FRONTEND-EXPERIENCE.md)
20. [PAS-020 Integration & First Prototype](PAS-020-INTEGRATION-PROTOTYPE.md)

### 测试、演进与生产

21. [PAS-021 Alpha Testing & Feedback](PAS-021-ALPHA-TESTING.md)
22. [PAS-022 AI Improvement Loop](PAS-022-AI-IMPROVEMENT-LOOP.md)
23. [PAS-023 Data Privacy & Trust](PAS-023-DATA-PRIVACY-TRUST.md)
24. [PAS-024 Scaling & Production Readiness](PAS-024-SCALING-PRODUCTION.md)
25. [PAS-025 Project Initialization](PAS-025-PROJECT-INITIALIZATION.md)

## 规范优先级

发生冲突时按以下顺序处理：

1. 用户安全、现实连接与主体性；
2. 用户隐私和数据控制权；
3. 用户明确表达与确认；
4. 当前产品需求和工程可行性；
5. 增长、留存和商业目标。

任何商业指标、交互优化或技术便利都不能覆盖前三项。

## 变更规则

- 重要原则的修改必须记录原因和影响。
- AI 推断不得悄悄升级为用户事实。
- 新功能必须说明对应的 PAS 章节和验收标准。
- 与安全、记忆、隐私有关的变更必须经过专项测试。
