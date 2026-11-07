# 业务对象识别与 CRC 卡片

> 命题：数学建模比赛管理系统（自 `competition-management/` 方向切换后的实验一 FR-01～FR-14 为输入）

## 1. 分析范围与来源

本次对象识别以实验一《功能性需求描述表》FR-01～FR-14 为输入，命题为"数学建模比赛管理系统"。对象识别遵循名词法：先完整记录名词短语，再依据"独立身份、拥有属性、需要被系统持续跟踪"三个条件筛选。

> 说明：本文件为 AI 辅助整理的草稿，最终对象选取、筛选和 CRC 卡片须经小组人工复核后作为人工结论。

## 2. 名词短语抽取

| 需求 | 主要名词短语 | 初步判断 |
|---|---|---|
| FR-01 创建与发布赛事 | 赛事、赛事草稿、名称、届次、主办方、时间范围、赛事状态 | 赛事进入候选；名称、届次、主办方、时间范围作为属性 |
| FR-02 配置规则与时间节点 | 规则、时间节点、报名、提交、评审、申诉、规则版本、时间表 | 规则版本进入候选；报名/提交/评审/申诉时间点为节点属性 |
| FR-03 发布题目与公告 | 赛题、附件、公告、可见范围 | 赛题、公告进入候选；附件与可见范围作为属性 |
| FR-04 注册队伍与资格审核 | 队伍、成员、报名申请、审核意见、报名状态 | 队伍、报名申请进入候选；成员为队伍属性，审核意见为申请属性 |
| FR-05 上传与管理论文版本 | 论文、附件、版本、提交状态、当前提交 | 提交资产、提交版本进入候选；格式、大小、状态作为属性 |
| FR-06 提交、撤回与截止锁定 | 当前版本、提交回执、状态、截止时间 | 提交版本进入候选；回执与锁定状态作为属性 |
| FR-07 分配评审任务与回避 | 评审任务、专家、专业标签、回避关系、评分表、截止时间 | 评审任务、评分表进入候选；专业标签与回避关系作为专家/任务属性 |
| FR-08 匿名评审与评分提交 | 匿名材料、评分、评语、分值范围、评审结果 | 评分记录进入候选；评语与分值作为评分属性 |
| FR-09 评审进度监控与异常处理 | 任务状态、进度看板、逾期、异常记录 | 异常记录进入候选；进度与逾期作为任务属性 |
| FR-10 成绩汇总与结果发布 | 成绩、获奖名单、结果、评分数据 | 比赛结果进入候选；成绩、名单作为结果属性 |
| FR-11 申诉处理与复核 | 申诉单、证据、处理意见、申诉状态 | 申诉单进入候选；证据与处理意见作为属性 |
| FR-12 操作日志与审计 | 操作日志、审计记录、对象、前后值、操作者 | 审计日志进入候选；前后值与操作者为字段 |
| FR-13 数据导出与赛事归档 | 导出、归档包、CSV、JSON、只读 | 归档记录进入候选；导出格式为属性 |
| FR-14 团队协作空间 | 协作记录、任务、备注、材料、权限 | 协作记录进入候选；备注与材料作为属性 |

## 3. 候选业务对象筛选

| 候选名词 | 结论 | 筛选依据 |
|---|---|---|
| User | 保留 | 有身份、角色和访问权限，系统需要持续跟踪 |
| Competition | 保留 | 有生命周期、规则、题目和结果，是系统核心实体 |
| RuleProfile | 保留 | 有规则版本、时间节点和发布状态 |
| Announcement | 保留 | 有标题、内容、可见范围和撤回状态 |
| ProblemSet | 保留 | 有题目文本、附件和绑定赛事的版本 |
| Team | 保留 | 有成员、指导教师和共享范围 |
| Enrollment | 保留 | 有报名申请状态、审核意见和截止约束 |
| SubmissionAsset | 保留 | 有论文/附件和提交记录 |
| SubmissionVersion | 保留 | 有版本号、锁定状态和提交回执 |
| ReviewTask | 保留 | 有任务状态、截止时间、专家和评分表绑定 |
| RubricProfile | 保留 | 有评分指标、权重和版本 |
| ScoreRecord | 保留 | 对应匿名评审的一次提交评分与评语 |
| CompetitionResult | 保留 | 汇总成绩、获奖名单和发布状态 |
| Appeal | 保留 | 有申诉单、证据、处理意见和状态 |
| AuditLog | 保留 | 记录关键操作的对象、前后值、操作者、时间 |
| ArchiveRecord | 保留 | 记录赛事导出归档与只读状态 |
| CollaborationNote | 保留 | 记录队内协作且不影响正式提交版本 |
| 名称、届次、主办方、时间范围 | 删除 | 纯属性值，不具备独立业务身份 |
| 发布、审核、分配、提交、汇总、导出 | 删除 | 动作，不是实体对象 |
| 评分、评语、前后值、附件 | 删除 | 属性值，不是独立业务实体 |
| PDF、DOCX、ZIP、CSV、JSON | 删除 | 外部格式，不是业务实体 |
| API、数据库、浏览器 | 删除 | 技术实现对象，不属于业务分析层 |

## 4. 确认后的业务对象清单

`User`、`Competition`、`RuleProfile`、`Announcement`、`ProblemSet`、`Team`、`Enrollment`、`SubmissionAsset`、`SubmissionVersion`、`ReviewTask`、`RubricProfile`、`ScoreRecord`、`CompetitionResult`、`Appeal`、`AuditLog`、`ArchiveRecord`、`CollaborationNote`。

## 5. CRC 卡片

### 5.1 User（用户）

| Class | Responsibilities | Collaborators |
|---|---|---|
| User | 保存身份和角色；登录并访问有权限的赛事数据 | Team、Competition |

属性：`userId`、`name`、`role`、`contact`、`status`。

### 5.2 Competition（赛事）

| Class | Responsibilities | Collaborators |
|---|---|---|
| Competition | 保存赛事基础信息和生命周期；组织规则、题目、队伍、评审和结果 | RuleProfile、Announcement、ProblemSet、Team、CompetitionResult、AuditLog |

属性：`competitionId`、`name`、`edition`、`organizer`、`lifecycle`、`dateRange`。

### 5.3 RuleProfile（规则版本）

| Class | Responsibilities | Collaborators |
|---|---|---|
| RuleProfile | 保存报名/提交/评审/申诉时间节点；校验时间不冲突；发布规则版本 | Competition |

属性：`ruleId`、`competitionId`、`version`、`deadlines`、`published`。

### 5.4 Announcement（公告）

| Class | Responsibilities | Collaborators |
|---|---|---|
| Announcement | 保存公告标题与内容；控制可见范围；支持撤回 | Competition |

属性：`announcementId`、`title`、`content`、`scope`、`status`。

### 5.5 ProblemSet（赛题）

| Class | Responsibilities | Collaborators |
|---|---|---|
| ProblemSet | 保存赛题文本和附件；绑定赛事与版本；控制可见范围 | Competition |

属性：`problemId`、`competitionId`、`text`、`attachments`、`version`。

### 5.6 Team（队伍）

| Class | Responsibilities | Collaborators |
|---|---|---|
| Team | 保存团队成员和指导教师；维护报名与提交关系 | User、Enrollment、SubmissionAsset |

属性：`teamId`、`teamName`、`members`、`advisor`、`competitionId`。

### 5.7 Enrollment（报名申请）

| Class | Responsibilities | Collaborators |
|---|---|---|
| Enrollment | 保存报名申请状态；记录审核意见和审核人 | Team、User、AuditLog |

属性：`enrollmentId`、`teamId`、`status`、`reviewComment`、`reviewer`。

### 5.8 SubmissionAsset（提交资产）

| Class | Responsibilities | Collaborators |
|---|---|---|
| SubmissionAsset | 保存论文/附件；管理版本；校验格式、大小和截止时间 | Team、SubmissionVersion |

属性：`submissionId`、`teamId`、`fileType`、`sha256`、`versions`。

### 5.9 SubmissionVersion（提交版本）

| Class | Responsibilities | Collaborators |
|---|---|---|
| SubmissionVersion | 保存版本号和提交回执；截止后锁定；记录撤回理由 | SubmissionAsset、AuditLog |

属性：`versionId`、`submissionId`、`version`、`locked`、`submittedAt`。

### 5.10 ReviewTask（评审任务）

| Class | Responsibilities | Collaborators |
|---|---|---|
| ReviewTask | 绑定匿名材料、专家和评分表；推进任务状态；支持替换与延期 | User、SubmissionVersion、RubricProfile、ScoreRecord |

属性：`taskId`、`reviewer`、`materialRef`、`rubric`、`status`、`dueAt`。

### 5.11 RubricProfile（评分表）

| Class | Responsibilities | Collaborators |
|---|---|---|
| RubricProfile | 保存评分指标和权重；结算总分；发布可用版本 | Competition、ReviewTask |

属性：`rubricId`、`name`、`version`、`criteria`、`weights`、`published`。

### 5.12 ScoreRecord（评分记录）

| Class | Responsibilities | Collaborators |
|---|---|---|
| ScoreRecord | 保存匿名评审的评分与评语；校验分值范围和必填项 | ReviewTask、RubricProfile |

属性：`scoreId`、`taskId`、`score`、`comment`、`submittedAt`。

### 5.13 CompetitionResult（比赛结果）

| Class | Responsibilities | Collaborators |
|---|---|---|
| CompetitionResult | 汇总评分生成成绩；发布获奖名单；支持结果修改留痕 | Competition、ScoreRecord、Appeal、AuditLog |

属性：`resultId`、`competitionId`、`scores`、`awards`、`publishedAt`。

### 5.14 Appeal（申诉单）

| Class | Responsibilities | Collaborators |
|---|---|---|
| Appeal | 保存申诉内容与证据；分派、调查、裁决并关闭；保留处理记录 | CompetitionResult、User、AuditLog |

属性：`appealId`、`resultId`、`content`、`evidence`、`status`、`resolution`。

### 5.15 AuditLog（审计日志）

| Class | Responsibilities | Collaborators |
|---|---|---|
| AuditLog | 记录对象、前后值、操作者、时间和原因；支持按赛事筛选查询 | Competition、User |

属性：`logId`、`object`、`beforeValue`、`afterValue`、`operator`、`time`、`reason`。

### 5.16 ArchiveRecord（归档记录）

| Class | Responsibilities | Collaborators |
|---|---|---|
| ArchiveRecord | 生成导出归档包；记录导出格式、时间与权限范围；标记只读 | Competition、AuditLog |

属性：`archiveId`、`competitionId`、`files`、`format`、`readOnly`、`createdAt`。

### 5.17 CollaborationNote（协作记录）

| Class | Responsibilities | Collaborators |
|---|---|---|
| CollaborationNote | 保存队内协作备注；与正式提交版本隔离 | Team、User |

属性：`noteId`、`teamId`、`content`、`author`、`createdAt`。

## 6. 主事件流

1. 管理员创建赛事并发布规则版本、题目和公告。
2. 队长注册队伍，维护成员，管理员审核报名资格。
3. 队长上传论文/附件并管理版本，截止后锁定。
4. 管理员按专业标签和回避关系分配匿名评审任务。
5. 评审专家查看匿名材料，提交评分与评语，系统校验。
6. 管理员监控评审进度，处理逾期/拒评/冲突异常。
7. 系统汇总成绩、发布获奖名单，队伍查看结果。
8. 队长提交申诉单，管理员分派、调查、裁决并关闭。
9. 管理员导出报名/提交/评审/成绩/日志并归档为只读。
10. 系统全程记录关键操作的审计日志。
