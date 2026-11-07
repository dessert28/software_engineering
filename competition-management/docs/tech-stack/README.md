# 技术选型

> 本目录存放比赛平台的技术选型文档。**当前采用纯 Python 方案。**

---

## 结论

| 文档 | 状态 | 说明 |
|---|---|---|
| [tech-stack-python.md](tech-stack-python.md) | ★ **采用** | 纯 Python 后端，v2.0，35KB，含高并发设计总纲 |
| [tech-stack-ts.md](tech-stack-ts.md) | 留档 | 早期 NestJS 为主 + Python 侧车的方案，v1.0，21KB |

后端语言已确定为 **Python**。TS 方案保留是因为它的结构（12 章 + 2 附录）和部分推理仍然成立，可作为决策依据与对照参考，但它不是实施依据。

---

## 两份方案的核心差异

| 维度 | 纯 Python（采用） | TypeScript（留档） |
|---|---|---|
| 服务形态 | **单 FastAPI 服务** + 按队列拆的 Celery worker | NestJS 主服务 + Python 评审侧车（双服务） |
| 运维组件 | 一套 Python 生态 | 两套运行时 + 两套依赖管理 |
| 文档处理 | PyMuPDF 在 `docproc` 队列执行 | 必须跨服务边界，走内部 HTTP |
| 团队学习成本 | 学一门语言能吃透全栈 | 两人组要同时维护两份后端 |
| 高并发论述 | 独立第 9 章（四层扩展梯度 + 削峰 + 连接池算式 + 四条压测曲线） | 分散在各章，未成体系 |

**为什么选纯 Python**：两人组、跨实验复用、文档处理（PDF/docx）天然是 Python 生态强项。双服务形态在课程规模下只会增加联调成本，不会带来收益。

---

## 会被问到的问题

### 前端为什么还是 TypeScript

没有找到「前端也要 Python」的依据。React + Vite + TypeScript + Ant Design 是这个规模的比赛管理后台的最短路径：表格、表单、上传、时间线全是 AntD 现成组件，能省掉大量布局工期。

如果坚持全 Python，唯一现实选项是 NiceGUI 或 Streamlit，但它们在复杂权限 UI 和多角色路由上的表达力不足以支撑 FR-001～FR-028，代价大于收益。

### 纯 Python 的并发能力够吗

够，但前提是**全 async 且不阻塞事件循环**：

- 所有路由 `async def`
- 所有数据库调用 `await`（SQLAlchemy 2.0 async + asyncpg）
- 所有 HTTP 调用 `httpx.AsyncClient`
- 所有 CPU 密集任务（PDF 解析、哈希、导出）进 Celery

做到这四条，单进程能跑几千并发 IO 型请求。做不到，纯 Python 和 NestJS 都扛不住——瓶颈不在语言，在事件循环是否被同步代码占住。

量化判据见 [tech-stack-python.md 第 11.2 节：必须验证的四条曲线](tech-stack-python.md#112-必须验证的四条曲线)。

### 什么时候需要切回 TS 方案

基本不会。只有当出现以下情况时才需要重新评估：

- 要求前端也必须是 Python（课程硬性规定，目前没有证据）
- 需要把评审侧车独立部署到不同机器上做资源隔离（纯 Python 方案也能做到，只是拆进程而非拆服务）

---

## 已被否决的方案

记录在这里，避免后续重复讨论：

| 方案 | 否决原因 |
|---|---|
| Django + DRF | 同步 ORM 为默认，即便用 `async` 视图也只是局部异步，文件下载/PDF 解析仍会阻塞；换 async 生态要放弃 Django 大部分 ORM 优势 |
| Flask + Gunicorn 同步 | 并发能力天花板明显，压测时线性劣化 |
| 纯 Serverless（云函数） | 分块上传要靠对象存储直传才成立，但导出、汇总等长任务在 Serverless 里超时且难调试 |
| SQLite 起步，后期再迁 PostgreSQL | 审计表的「只 INSERT」需要数据库层权限控制，SQLite 无此能力；并发写入也扛不住 |
| Elasticsearch 做检索 | 规模不需要，PG 的 `pg_trgm` + `tsvector` 足够，少一个运维组件 |

---

## 阅读建议

- 只想了解结论 → 看本文档
- 要写代码 → 直接读 [tech-stack-python.md](tech-stack-python.md) 的 3、4、5 章（后端分层、数据库、文件上传）
- 要准备压测答辩 → 读 9、11 章（高并发设计、压测方案）
- 要理解当初为什么考虑过 TS → 读 [tech-stack-ts.md](tech-stack-ts.md)
