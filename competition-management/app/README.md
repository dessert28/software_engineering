# 数学建模比赛管理系统 · 初版

> MVP v0.1 ｜ 纯 Python 后端 + React 前端 ｜ 覆盖赛事主链路

---

## 这是什么

按 [功能需求 FR-001～FR-028](../../docs/functional-requirements.md) 的 **P0 范围**搭出来的第一版可运行系统。目标不是做完所有需求，而是把主链路跑通：

```
管理员建赛事 → 配置时间节点 → 发布
   → 队伍报名 → 管理员审核资格
   → 队长提交作品（版本管理）
   → 管理员分配评审任务 → 专家匿名打分
   → 管理员汇总成绩 → 发布结果
```

这条链路已在真实 HTTP 请求下逐段验证通过（见文末「验证记录」）。

---

## 目录结构

```
app/
├── README.md               # 本文件
├── docker-compose.yml      # 一键起 api + web 两容器（可选）
├── Dockerfile              # 一个镜像两个角色，多阶段构建
├── docker/
│   ├── entrypoint.sh       # 按 command 切换 api / web
│   └── nginx.conf          # SPA 回落 + /api 反代
├── backend/
│   ├── pyproject.toml
│   ├── .env.example
│   ├── app/
│   │   ├── main.py         # FastAPI 应用入口
│   │   ├── core/           # 配置、安全、依赖注入
│   │   ├── db/             # 引擎、会话、种子数据
│   │   ├── models/         # SQLAlchemy 模型（17 个业务对象）
│   │   ├── schemas/        # Pydantic v2 模型
│   │   ├── routers/        # 按业务域分路由（7 个）
│   │   └── services/       # 业务规则（生命周期、存储、审计）
│   ├── scripts/
│   │   └── cold_start_check.py   # 冷启动自检
│   └── tests/              # pytest：规则单测 + 全链路集成测试
└── frontend/
    ├── package.json
    └── src/
        ├── api/client.ts   # 唯一碰 fetch 的地方
        ├── components/     # 布局与登录态
        ├── lib/labels.ts   # 枚举中文映射
        └── pages/          # 6 个页面
```

---

## 快速开始

### 后端

```powershell
cd app\backend
.\.venv\Scripts\Activate.ps1
pip install -e .
uvicorn app.main:app --reload --port 8000
```

打开 <http://127.0.0.1:8000/docs> 看接口文档。

首次启动会自动建表并写入种子数据（3 个账号、1 个示例赛事、1 套评分细则）。
数据库文件与上传目录会在启动时自动创建到 `backend/data/`，不需要手工建目录。

**默认账号**（密码都是 `Passw0rd!`）：

| 账号 | 角色 |
|---|---|
| `admin@example.edu` | 赛事管理员 |
| `teacher@example.edu` | 指导教师 |
| `judge@example.edu` | 评审专家 |

### 前端

```powershell
cd app\frontend
pnpm install
pnpm dev
```

打开 <http://127.0.0.1:5173>。前端开发服务器已配置代理，`/api` 转发到 `http://127.0.0.1:8000`。

### 用 Docker 一键起（可选）

```powershell
cd app
docker compose up --build
```

- 前端 <http://127.0.0.1:5173>
- 接口文档 <http://127.0.0.1:8000/docs>

镜像只有一个（`mmcm-app:0.1.0`），用 `command` 区分角色：`api` 跑 uvicorn，`web` 跑 nginx 托管前端并反代 `/api`。数据库和上传文件挂在 `mmcm-data` 卷上，容器重建不丢数据。

暂不引入 Redis / Celery / MinIO —— 初版没有异步任务和对象存储依赖，加进去只增加启动负担。

### 冷启动自检

怀疑「换台机器跑不起来」时，跑这个脚本（它会自己造临时目录，不碰你的开发库）：

```powershell
cd app\backend
.\.venv\Scripts\python.exe scripts\cold_start_check.py
```

脚本会验证：嵌套目录自动创建 → 建表 → 写种子 → 真实 HTTP 登录 → 查赛事 → 读评分细则。

### 页面

| 页面 | 路径 | 谁能看 |
|---|---|---|
| 赛事列表 | `/competitions` | 所有登录用户 |
| 赛事详情 | `/competitions/:id` | 所有；状态迁移/审核/成绩按钮仅管理员 |
| 我的队伍 | `/my-team` | 队长、队员、指导教师 |
| 评审任务 | `/judge` | 评审专家、管理员 |
| 成绩查询 | `/results` | 所有；管理员额外可见草稿成绩 |
| 审计日志 | `/audit` | 仅管理员 |

---

## 接口总览

7 个路由模块，共 **33 个端点**：

| 模块 | 前缀 | 端点数 | 职责 |
|---|---|---|---|
| `auth` | `/api/auth` | 2 | 登录、当前用户 |
| `competitions` | `/api/competitions` | 9 | 赛事 CRUD、状态迁移、公告、题目 |
| `teams` | `/api/teams` | 4 | 建队、加成员、报名、报名审核 |
| `submissions` | `/api/submissions` | 5 | 提交单、版本上传、正式提交、撤回 |
| `reviews` | `/api/reviews` `/api/judges` | 7 | 专家管理、任务分配、匿名材料、打分、进度 |
| `results` | `/api/competitions/{id}/results` | 5 | 汇总、发布、查询 |
| `audit` | `/api/audit` | 1 | 审计日志查询 |

另有 3 个元数据端点：`/api/health`、`/api/meta/lifecycle`、`/api/meta/rubric`。

按 OpenAPI 实测：**33 条路径、40 个操作**（部分路径同时挂 GET/POST，故操作数多于端点数）。

---

## 技术选型落地情况

| 层 | [选型文档](../../docs/tech-stack/tech-stack-python.md) 写的 | 初版实际用的 | 为什么 |
|---|---|---|---|
| Web 框架 | FastAPI | FastAPI | ✅ 一致 |
| ORM | SQLAlchemy 2.0 async | SQLAlchemy 2.0 async | ✅ 一致 |
| 数据库 | PostgreSQL 16 | **SQLite（aiosqlite）** | 初版免装数据库，换 PG 只改 `DATABASE_URL` |
| 缓存/队列 | Redis 7 + Celery | 暂未接入 | 初版无异步任务，评审同步执行 |
| 对象存储 | MinIO | **本地文件系统** | 存储层已抽象成 `StorageBackend`，换 MinIO 只实现一个类 |
| 前端 | React 18 + Vite + TS + AntD 5 | 一致 | ✅ |
| 认证 | JWT | JWT（HS256） | ✅ |

**结论**：初版是「同一套架构的可单机运行形态」。所有为生产准备的抽象（存储后端、数据库 URL、会话管理）都已就位，替换基础设施不需要改业务代码。

---

## 已实现的范围

### P0 已完成

| 功能 | FR | 接口 |
|---|---|---|
| 用户登录与角色鉴权 | — | `POST /api/auth/login` |
| 创建/编辑赛事 | FR-001 | `POST/PATCH /api/competitions` |
| 赛事生命周期状态机 | FR-002 | `POST /api/competitions/{id}/transition` |
| 配置时间节点 | FR-003 | 赛事对象内嵌时间字段 |
| 发布题目与公告 | FR-004 | `POST /api/competitions/{id}/announcements` |
| 队伍注册 | FR-006 | `POST /api/teams` |
| 成员与教师绑定 | FR-007 | `POST /api/teams/{id}/members` |
| 报名资格审核 | FR-008 | `POST /api/enrollments/{id}/review` |
| 作品上传（版本化） | FR-009/010 | `POST /api/submissions/{id}/versions` |
| 提交与截止锁定 | FR-011 | `POST /api/submissions/{id}/submit` |
| 专家管理与回避 | FR-012 | `POST /api/review-tasks` 内置同校回避 |
| 评审任务分配 | FR-013 | `POST /api/review-tasks` |
| 匿名材料 | FR-014 | `GET /api/review-tasks/{id}/material` |
| 评分提交 | FR-015 | `POST /api/review-tasks/{id}/score` |
| 进度看板 | FR-016 | `GET /api/competitions/{id}/review-progress` |
| 成绩汇总 | FR-019 | `POST /api/competitions/{id}/results/calculate` |
| 结果发布 | FR-020 | `POST /api/competitions/{id}/results/publish` |
| 结果查看 | FR-021 | `GET /api/competitions/{id}/results` |
| 审计日志 | FR-024 | `GET /api/audit` + 各写操作自动留痕 |

### P1/P2 未做

FR-005（通知）、FR-017（评审异常处理）、FR-018（复核）、FR-022/023（申诉）、FR-025（导出归档）、FR-026（统计）、FR-027（协作空间）、FR-028（版本复审）。

---

## 三条不可动摇的纪律

这三条写在 [技术选型第 9 章](../../docs/tech-stack/tech-stack-python.md)，初版代码里逐条落实：

### 1. 全 async

所有路由 `async def`，所有数据库调用 `await`。没有一处 `def` 路由，没有一处同步 ORM 调用。

### 2. AI 不进加权

AI 预评级已接入，但**只做路由器，不做评委**。预评级结果写进 `ai_review_records`，`authority` 恒为 `ADVISORY`；人工评审分写 `ScoreRecord(authority=HUMAN)`，`aggregate_scores()` 显式排除 `ADVISORY`，所以 AI 分数永远不进最终加权。

实现路径（`app/services/ai.py` + `app/routers/ai_assessments.py`）：

- **两级评估**：L1 用纯规则提取章节齐备度、图表数、公式数、页数等轻量特征并标注风险；L2 只在命中风险标记的候选上跑结构化深评，默认 provider 为离线启发式，配 `AI_PROVIDER=openai_compatible` 可切 OpenAI 兼容端点。
- **强校验与降级**：L2 输出必须过 Pydantic（每条维度分至少一段原文证据），校验失败写 `FAILED` 转「无 AI 参考」模式，人工流程照常；PDF/DOCX 首版不解析正文，标 `OCR_REQUIRED` 交人工核实。
- **幂等**：`(version_id, model_id, prompt_version, input_hash)` 唯一键保证同一输入只评估一次；阈值版本来自 `rule_profile.ai_thresholds`，改动即视为新输入。
- **防锚定**：专家端 `GET /api/review-tasks/{id}/ai-risk-flags` 只返回风险标记清单，不返回 AI 分数或置信度。
- **确定性分流**：`evaluate_escalations()` 按 `SCORE_GAP / AI_HUMAN_GAP / LOW_CONFIDENCE / RISK_CONFIRMED / AWARD_BOUNDARY` 五条规则产生 `review_escalations` 留档，阈值可版本化，判定不交给模型。

### 3. 唯一约束进表

六条强制约束已写进 SQLAlchemy 模型：

| 约束 | 位置 |
|---|---|
| `(competition_id, name)` | `teams` |
| `(competition_id, team_id)` | `enrollments` |
| `(submission_id, reviewer_id)` | `review_tasks` |
| `(submission_id, version_no)` | `submission_versions` |
| `(md5, size_bytes)` | `blob_objects` |
| `(version_id, model_id, prompt_version, input_hash)` | `ai_review_records`（AI 预评级幂等键） |
| `(competition_id, submission_id, rule_code)` | `review_escalations`（同一作品同一规则只触发一次） |

---

## 测试

```powershell
cd app\backend
.\.venv\Scripts\python.exe -m pytest -q
```

当前 **110 个测试全绿**，分五层：

| 文件 | 测什么 | 数量 |
|---|---|---|
| `tests/test_rules.py` | 纯函数层：状态机、加权计算、聚合策略、并列名次、细则契约 | 26 |
| `tests/test_flow.py` | 全链路集成：走真实 HTTP 请求，覆盖正向流程与 403/409/415/422 负向边界 | 40 |
| `tests/test_anonymity.py` | 匿名评审的**对抗性**边界：专家之间的越权、身份反推、评分不可变 | 10 |
| `tests/test_contract.py` | 回归基线：12 状态、权重合计 100、AI 不进加权、匿名 schema 无身份字段 | 24 |
| `tests/test_storage.py` | 存储层：流式写入、超限清理、md5 去重 | 10 |

集成测试用独立临时 SQLite，不碰开发库。覆盖的边界包括：

- 状态机：非法跳转 409、强制归档需原因、终态不可编辑
- 报名：非报名期建队 409、同赛事重名 409、人数上限、重复报名 409
- 提交：扩展名白名单 415、空文件 400、无版本提交 409、重复提交 409、**截止后上传 409**
- 评审：同校回避 409、重复分配 409、评语不足 10 字 400、分数越界 422、非专家读材料 403
- 成绩：未汇总就发布 409、草稿成绩对参赛方不可见、跨队读提交 403
- 匿名性（对抗视角）：
  - 材料 payload 里没有队伍名、学校、角色、邮箱，也没有 `storage_key` / 路径 / `submission_id`
  - 专家 A 读不到、也打不了专家 B 的任务（403）
  - 专家拉不到赛事全量任务列表（403），`/review-tasks/mine` 只返回自己的
  - 同一任务二次打分被 409 拒绝（评分即最终意见）
  - 库里即便存在 `ADVISORY` 记录，汇总也不计入
- 上传：超限文件抛 413 且**磁盘上不留半成品**；恰好等于上限允许，多 1 字节拒绝；空文件 400

---

## 验证记录

以下是在真实进程上跑出来的结果（非单元测试）：

| 步骤 | 观察 |
|---|---|
| 状态迁移 | `DRAFT → … → SUBMISSION_OPEN` 逐条成功，非法跳转被 409 挡住 |
| 报名期拦截 | 在 `SUBMISSION_OPEN` 建队返回「当前不在报名开放期」 |
| 版本上传 | v1、v2 递增；同一文件二次上传复用了同一 `blob_id`（md5 秒传生效） |
| 匿名材料 | `problem_code` 为 `作品编号 548D9FE6D3EC`，payload 无队伍名 |
| 打分 | 三档 88/86/90 → 总分 `87.6`，`authority=HUMAN` |
| 汇总发布 | `computed=1`、`rank=1`、状态 `PUBLISHED` |
| 审计 | 记录到 `CREATE/LOGIN/PUBLISH/SCORE/SUBMIT/TRANSITION/UPDATE` 七类动作 |
| 冷启动 | 全新临时目录（库和上传目录都不存在）→ 自动建嵌套目录 → 建表 → 种子 3 用户/1 赛事 → 登录/查赛事/读细则全部 200 |

前端 `pnpm exec tsc --noEmit` 无错误，`vite build` 产出 1.2 MB（gzip 379 KB）。

### 已验证 / 未验证的边界

诚实地标注一下：`docker compose up` 这条路径**写完没跑**（本机没有 Docker daemon）。Dockerfile 和 compose 的逻辑按最小镜像原则写好，但首次使用请做好需要小修的准备。真正跑通过的是本地直起 + 冷启动脚本。

---

## 下一步

按 [实验三](../../experiments/exp3-OOD架构与MVP/README.md) 的遗留问题清单推进：

1. 补 `MaterialRef`，把匿名评审的映射关系正式建模（当前用 `material_ref` 随机串临时实现）
2. `ReviewTask` 与 `ScoreRecord` 是否合并，给出结论
3. 补 P1 功能：申诉、导出、通知
4. 换 PostgreSQL + MinIO，跑一遍压测
5. 前端按路由做代码分割（当前打包成单个 chunk）
