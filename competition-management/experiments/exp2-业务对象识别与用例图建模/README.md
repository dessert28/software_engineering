# 实验二 · 业务对象识别与用例图建模

> 比赛管理系统方向的实验二交付物。2026-10-28 方向切换后重做。

---

## 实验信息

| 项 | 内容 |
|---|---|
| 课程 | 软件工程 |
| 实验 | 实验二：业务对象识别与用例图建模 |
| 学时 / 类型 | 3 学时 / 综合型 |
| 对应章节 | Ch4 §4.4-4.10 + Ch5 §5.1-5.6 |
| 组别 | 两人组 |
| 命题 | 数学建模比赛管理系统（沿用实验一，不得更换） |

---

## 交付物清单

### 报告

| 文件 | 说明 |
|---|---|
| `实验二_业务对象识别与用例图建模_两人组_比赛管理系统.docx` | 正式提交的实验报告（162KB，含图） |

### 过程文档

| 文件 | 内容 |
|---|---|
| `business_objects.md` | **17 个业务对象**识别 + CRC 卡片（10.7KB，本实验核心产出） |
| `usecase_specs.md` | UC-001～UC-005 用例规约（6.1KB） |
| `usecase_diagram.puml` | 用例图 PlantUML 源文件（2.2KB） |
| `initial_class_diagram.puml` | 初始类图 PlantUML 源文件（4KB） |
| `relation_audit.md` | 类之间关系的审查记录（4KB） |
| `ai_log.md` | AI 使用记录 |
| `group_roles.md` | 两人分工表 |

### 质量审查产物

| 路径 | 内容 |
|---|---|
| `qa/_qa_report.pdf` 等 6 份 | 报告渲染检查的 PDF 版本（约 7.3MB） |
| `qa/pages/_qa_*_pages/` | 报告逐页 PNG 截图，用于检查图片、表格、分页（8 个目录，约 12MB） |

> `qa/` 是自查产物，不是提交内容。保留是为了复现「为什么这版排版是对的」。

---

## 17 个业务对象

这是实验二最重要的输出，实验三的类图、数据库表设计都从这里出发。

| # | 对象 | 职责 |
|---|---|---|
| 1 | `User` | 平台用户（学生 / 教师 / 评委 / 管理员） |
| 2 | `Competition` | 赛事，含生命周期状态 |
| 3 | `RuleProfile` | 赛事规则配置快照（评分细则、评审规则、复审阈值） |
| 4 | `Announcement` | 通知公告 |
| 5 | `ProblemSet` | 赛题 |
| 6 | `Team` | 参赛队伍 |
| 7 | `Enrollment` | 报名记录（队伍参加某赛事） |
| 8 | `SubmissionAsset` | 提交物（一个赛题下的作品载体） |
| 9 | `SubmissionVersion` | 提交版本（同一 asset 的多次提交） |
| 10 | `ReviewTask` | 评审任务（某专家评某作品） |
| 11 | `RubricProfile` | 评分细则模板 |
| 12 | `ScoreRecord` | 评分记录 |
| 13 | `CompetitionResult` | 赛事结果汇总 |
| 14 | `Appeal` | 申诉单 |
| 15 | `AuditLog` | 审计日志（只 INSERT） |
| 16 | `ArchiveRecord` | 归档记录 |
| 17 | `CollaborationNote` | 协作备注 |

CRC 卡片详见 [business_objects.md](business_objects.md)。

---

## 用例规约

5 个核心用例：

| 编号 | 用例 | 主要参与者 |
|---|---|---|
| UC-001 | 报名参赛 | 学生（队长） |
| UC-002 | 提交作品 | 学生（队长） |
| UC-003 | 评审作品 | 评审专家 |
| UC-004 | 发布成绩 | 平台管理员 |
| UC-005 | 处理申诉 | 平台管理员 |

详见 [usecase_specs.md](usecase_specs.md)。

---

## 图的渲染方式

两份 `.puml` 用 PlantUML 渲染。三种方式任选：

```powershell
# 方式一：VS Code 装 PlantUML 插件，打开 .puml 按 Alt+D
# 方式二：在线渲染
#   把 .puml 内容粘贴到 https://www.plantuml.com/plantuml/uml/

# 方式三：本地 jar
java -jar plantuml.jar usecase_diagram.puml
java -jar plantuml.jar initial_class_diagram.puml
```

---

## 过程审查

`relation_audit.md` 记录了类之间关系的自查过程，重点检查了三类问题：

1. **多对多是否有中间实体** — `Team` 与 `User` 之间是 `TeamMember`；`Competition` 与 `Team` 之间是 `Enrollment`
2. **是否混入了实现细节** — 例如 `SubmissionVersion` 不应直接持有文件路径，而应引用 `BlobObject`
3. **生命周期相关的对象是否独立** — `RuleProfile` 必须独立成对象，因为规则会版本化，不能塞进 `Competition` 字段

---

## AI 参与范围声明

| 环节 | 人工 | AI 辅助 |
|---|---|---|
| 名词法识别对象 | 通读需求表逐句标注 | 生成候选名词池，人工筛选 |
| CRC 卡片 | 职责与协作者判定 | 生成卡片骨架 |
| 用例图 / 类图 | 确定关系与多重性 | 生成 PlantUML 代码 |
| 关系审查 | **人工逐条核对**（`relation_audit.md`） | 无 |
| 报告排版 | 人工定稿 | 辅助生成表格 |

---

## 待实验三处理的问题

1. **`CollaborationNote` 的边界模糊** — 它是「队员之间」还是「管理员与队伍之间」的协作？实验二未定，实验三的类图必须明确。
2. **`ReviewTask` 与 `ScoreRecord` 是否要合并** — 现在分开是为了支持「一个任务可能多次改分」，但会增加查询复杂度，实验三需权衡。
3. **匿名评审的映射关系没有建模** — 专家看到的材料需要与真实 `SubmissionVersion` 建立映射，实验二没建这个对象，实验三要补（技术选型里叫 `materialRef`）。

---

## 相关文档

- [实验一](../exp1-功能性需求分析/README.md) — 需求来源
- [完整功能需求 FR-001～FR-028](../../docs/functional-requirements.md) — 每个对象对应哪些 FR
- [系统边界](../../docs/boundary.md) — 生命周期与权限约束
- [技术选型](../../docs/tech-stack/tech-stack-python.md) — 17 个对象如何落成数据库表
