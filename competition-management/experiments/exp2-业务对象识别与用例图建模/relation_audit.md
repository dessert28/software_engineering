# 类间关系审查

> 命题：数学建模比赛管理系统。本文件为 AI 辅助整理的关系审查草稿，最终关系判断须由小组人工确认。

## 1. 审查范围

本次审查覆盖 `initial_class_diagram.puml` 中的继承、聚合和关联关系。审查依据是 CRC 卡片和业务语义，而不是代码实现便利性。

## 2. 关系审查表

| 关系 | 初始判断 | 人工审查结论 | 判断依据 |
|---|---|---|---|
| User—Admin | 继承 | 保留 | Admin"是一种"User，继承身份和权限基础属性 |
| User—Expert | 继承 | 保留 | Expert"是一种"User，具有评审职责 |
| User—Advisor | 继承 | 保留 | Advisor"是一种"User，只读查看授权队伍 |
| User—Leader | 继承 | 保留 | Leader"是一种"User，负责报名与提交 |
| User—Member | 继承 | 保留 | Member"是一种"User，参与队伍协作 |
| Team—Member/Leader/Advisor | 聚合 | 保留 | 成员是队伍的一部分，脱离队伍身份失去赛事内意义 |
| Competition—RuleProfile | 聚合 | 保留 | 规则版本属于某赛事，赛事删除时规则失去意义 |
| Competition—Announcement/ProblemSet | 聚合 | 保留 | 公告和赛题归属于赛事 |
| Team—SubmissionAsset | 聚合 | 保留 | 提交资产属于队伍，赛队伍删除时提交记录生命周期随队伍管理 |
| SubmissionAsset—SubmissionVersion | 组合 | 保留 | 版本是提交资产内部的组成部分，脱离资产不独立存在 |
| ReviewTask—ScoreRecord | 聚合 | 保留 | 评分记录属于某个评审任务 |
| CompetitionResult—ScoreRecord | 关联 | 保留为关联 | 成绩聚合多个评分，但评分记录本身属于评审任务 |
| ReviewTask—Expert | 关联 | 保留 | 专家可以承接多个任务，任务绑定专家承担人 |
| ReviewTask—RubricProfile | 关联 | 保留为关联 | 评分表可独立发布和复用 |
| Appeal—CompetitionResult | 关联 | 保留 | 申诉针对结果，但结果可独立存在 |
| AuditLog—Competition/User | 关联 | 保留 | 审计日志引用对象和操作者，不是整体—部分关系 |
| ArchiveRecord—Competition | 关联 | 保留 | 归档可重新生成，不是赛事的组成实体 |

## 3. 重点误判检查

### 3.1 继承 vs 聚合

判断问题是"子对象是否是一种父对象"。

- `Admin/Expert/Advisor/Leader/Member` 都是 `User` 的一种，使用继承。
- `Team` 不是 `User`，`Competition` 不是 `RuleProfile`，二者只能是整体—部分或关联。

### 3.2 聚合 vs 关联与组合

- `SubmissionVersion` 是 `SubmissionAsset` 的组成部分，采用组合语义。
- `ScoreRecord` 属于 `ReviewTask`，采用聚合语义。
- `RubricProfile` 可脱离任务独立发布和复用，与 `ReviewTask` 是关联。
- `CompetitionResult` 聚合多个 `ScoreRecord`，但 `ScoreRecord` 本身归属 `ReviewTask`，因此聚合关系以任务为主线。
- `Appeal`、`AuditLog`、`ArchiveRecord` 依赖结果/赛事但可独立查询和追溯，是关联。

## 4. 多重性检查

- 一个 `Team` 可包含一到多个 `User`，一个 `User` 可属于多个 `Team`。
- 一个 `Competition` 有一个或多个 `RuleProfile` 版本，可发布多个 `Announcement` 和 `ProblemSet`。
- 一个 `Team` 有一个 `SubmissionAsset`，一个资产有多个 `SubmissionVersion`。
- 一个 `SubmissionVersion` 可被多个 `ReviewTask` 评审。
- 一个 `ReviewTask` 绑定一个 `Expert` 和一个 `RubricProfile`，可产生一个 `ScoreRecord`。
- 一个 `CompetitionResult` 聚合多个 `ScoreRecord`，一个结果可被多个 `Appeal` 挑战。
- 一个 `Competition` 有多个 `AuditLog` 和 `ArchiveRecord` 记录。

## 5. 审查结论

初始类图中的关系均符合"数学建模比赛管理系统"的业务语义。审查重点是避免把"属于某赛事/某任务"误写为继承，也避免把可独立发布的评分表和可追溯的审计/归档记录误写为聚合。最终类图只保留业务分析层需要的关系，不引入数据库外键、API 客户端等实现关系。
