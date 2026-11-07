# 实验三 · OOD 系统架构 / MVP / 类图

> **状态：待开始**

---

## 实验信息

| 项 | 内容 |
|---|---|
| 课程 | 软件工程 |
| 实验 | 实验三：面向对象设计（OOD）系统架构 / MVP / 类图 |
| 组别 | 两人组 |
| 命题 | 数学建模比赛管理系统（沿用实验一、二，不得更换） |

---

## 已备好的输入

写这个实验需要的材料都已经在仓库里：

| 输入 | 位置 | 用途 |
|---|---|---|
| 17 个业务对象 + CRC 卡片 | [exp2/business_objects.md](../exp2-业务对象识别与用例图建模/business_objects.md) | 类图的直接来源 |
| 初始类图 | [exp2/initial_class_diagram.puml](../exp2-业务对象识别与用例图建模/initial_class_diagram.puml) | 在此基础上细化 |
| 5 个用例规约 | [exp2/usecase_specs.md](../exp2-业务对象识别与用例图建模/usecase_specs.md) | 时序图与职责分配的依据 |
| 28 条功能需求 | [docs/functional-requirements.md](../../docs/functional-requirements.md) | 确认架构覆盖全部 P0 |
| 12 态生命周期 | [docs/boundary.md](../../docs/boundary.md) | 状态机设计 |
| 纯 Python 架构 | [docs/tech-stack/tech-stack-python.md](../../docs/tech-stack/tech-stack-python.md) | 分层与模块划分 |

---

## 必须解决的五个遗留问题

这五个问题从实验一、二的 README 里累积下来，实验三必须给出结论：

| # | 问题 | 来源 | 建议方向 |
|---|---|---|---|
| 1 | `CollaborationNote` 的边界：队员之间，还是管理员与队伍之间？ | 实验二 | 拆成两个对象，或明确只保留一种语义 |
| 2 | `ReviewTask` 与 `ScoreRecord` 是否合并 | 实验二 | 若支持多次改分则保留分离；若只记最终分则合并 |
| 3 | **匿名评审的映射关系未建模** | 实验二 | 新增 `MaterialRef`，专家侧只见随机 UUID，与 `SubmissionVersion` 的映射表仅管理员可读 |
| 4 | 实验一的需求表只有 14 条，完整版 28 条 | 实验一 | 在架构的模块划分里确认每条 FR 都有落点（对照表） |
| 5 | 原型只有首页 | 实验一 | MVP 设计需补：个人中心四态、评审工作台、管理端看板 |

---

## 预期交付物

```
exp3-OOD架构与MVP/
├── README.md                    # 交付物索引（写好 AI 参与声明）
├── 实验三_xxx_两人组_比赛管理系统.docx
├── architecture.md              # 架构设计说明：分层、模块、部署
├── architecture_diagram.puml    # 架构图（分层图 / 部署图）
├── class_diagram.puml           # 细化后的完整类图
├── sequence_*.puml              # 关键用例的时序图（至少 3 个）
├── state_machine.puml           # 赛事生命周期状态机
├── mvp_scope.md                 # MVP 范围划定：哪些 FR 进 MVP
├── prototype/                   # 补全的界面原型
├── ai_log.md
└── group_roles.md
```

---

## 建议的推进顺序

```mermaid
flowchart LR
    A["① 定 MVP 范围<br/>从 28 条 FR 里挑 P0"] --> B["② 画状态机<br/>12 态与转换条件"]
    B --> C["③ 细化类图<br/>解决 5 个遗留问题"]
    C --> D["④ 画时序图<br/>报名·提交·评审三条主线"]
    D --> E["⑤ 写架构说明<br/>分层与模块落点"]
    E --> F["⑥ 补原型<br/>个人中心四态·评审台"]
```

先定 MVP 范围再画图，否则类图会画进 V2 的东西，返工成本高。

---

## 验收自检

- [ ] 28 条 FR 每条都能在架构里找到落点（做一张对照表）
- [ ] 12 态生命周期的每个转换都有触发条件与权限约束
- [ ] 5 个遗留问题都有明确结论（不是「待定」）
- [ ] 类图里没有实现细节泄漏（如文件路径、HTTP 状态码）
- [ ] 时序图至少覆盖：报名（含并发抢名额）、提交（含截止锁定）、评审（含匿名）
- [ ] 原型覆盖个人中心四态
- [ ] AI 参与范围声明与 `ai_log.md` 一致
