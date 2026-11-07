# 业务对象识别与 CRC 卡片

## 1. 分析范围与来源

本次对象识别以实验一《功能性需求描述表》FR-01～FR-10 为输入，命题为“数学建模论文评审与优化服务平台”。对象识别遵循名词法：先完整记录名词短语，再依据“独立身份、拥有属性、需要被系统持续跟踪”三个条件筛选。

本节的抽取、筛选和 CRC 卡片均为人工完成，AI 未参与对象选择。

## 2. 名词短语抽取

| 需求 | 主要名词短语 | 初步判断 |
|---|---|---|
| FR-01 用户与团队登录 | 用户、团队、论文、量表、任务、报告、账号、密码、验证码、角色权限 | 用户、团队、论文、量表、任务、报告进入候选；账号、密码、验证码、角色权限作为属性或安全概念 |
| FR-02 论文批量导入与解析 | 论文、批次文件、文件、格式、指纹、论文资产、赛题信息、解析状态、错误提示 | 论文资产、赛题信息进入候选；文件格式、指纹、解析状态作为属性 |
| FR-03 评审服务选择与任务创建 | 评审服务、基础诊断、深度评审、团队评审、论文、量表、任务、订单、服务状态 | 评审任务、量表进入候选；服务类型和订单状态作为任务属性 |
| FR-04 评价标准管理 | 教师、运营人员、指标、权重、评分说明、量表、量表版本 | 量表、量表版本进入候选；指标、权重和评分说明作为量表属性 |
| FR-05 七阶段论文评审 | 论文、问题识别、问题表述、假设、模型构建、求解、代码实现、结果分析、阶段结果、评分候选、证据引用 | 阶段结果、证据块进入候选；七阶段名称是评审维度 |
| FR-06 任务队列与进度管理 | 任务、状态、等待、运行、完成、失败、重试、阶段、错误信息 | 评审任务进入候选；状态、错误信息和进度作为属性 |
| FR-07 评审问题与证据定位 | Finding、Claim、Obligation、论文、页码、段落、证据块、判断理由、待人工核实标记 | 评审发现、证据块进入候选；页码、段落和标记作为定位属性 |
| FR-08 优化建议生成与人工复核 | 评审问题、修改动作、优先级、验收方法、教师、学生、人工意见、建议清单、编辑记录 | 优化建议、建议编辑记录进入候选；优先级和验收方法作为属性 |
| FR-09 修改稿复审与报告导出 | 修改稿、历史任务、问题解决状态、版本对比、评审报告、Markdown、JSON | 论文资产、评审报告进入候选；格式和解决状态作为属性 |
| FR-10 预测与运营审计 | 论文特征、获奖等级预测辅助信息、建议生成轨迹、任务统计、系统审计记录、报表 | 审计记录、统计报表进入候选；预测信息作为后续扩展数据 |

## 3. 候选业务对象筛选

| 候选名词 | 结论 | 筛选依据 |
|---|---|---|
| 用户 | 保留 | 有身份、角色和访问权限，系统需要持续跟踪 |
| 团队 | 保留 | 有独立的授权关系和共享范围 |
| 论文资产 | 保留 | 有指纹、版本、解析状态和生命周期 |
| 证据块 | 保留 | 有稳定编号、页码/段落定位和引用关系 |
| 评价量表 | 保留 | 有版本、指标、权重和发布状态 |
| 评审任务 | 保留 | 有任务编号、状态、输入绑定和运行生命周期 |
| 阶段结果 | 保留 | 对应七阶段评审，有分数、理由和证据引用 |
| 评审发现 | 保留 | 有严重级别、结论、证据和处理状态 |
| 优化建议 | 保留 | 有动作、验收标准、优先级和编辑历史 |
| 评审报告 | 保留 | 有报告编号、生成时间、版本和导出格式 |
| 页码、段落、权重、评分值 | 删除 | 纯属性值，不具备独立业务身份 |
| 登录、上传、解析、评审、导出 | 删除 | 动作或服务，不是实体对象 |
| PDF、DOCX、Markdown、JSON | 删除 | 外部格式，不是业务实体 |
| API、数据库、浏览器、模型接口 | 删除 | 技术实现对象，不属于业务分析层 |

## 4. 确认后的业务对象清单

`User`、`Team`、`PaperAsset`、`EvidenceBlock`、`RubricProfile`、`ReviewJob`、`StageResult`、`Finding`、`Recommendation`、`ReviewReport`。

## 5. CRC 卡片

### 5.1 User（用户）

| Class | Responsibilities | Collaborators |
|---|---|---|
| User | 保存身份和角色；发起论文导入；查看本人有权限的评审结果；提交人工复核意见 | Team、PaperAsset、ReviewJob、ReviewReport |

属性：`userId`、`name`、`role`、`contact`、`status`。

### 5.2 Team（团队）

| Class | Responsibilities | Collaborators |
|---|---|---|
| Team | 保存团队成员；管理论文和任务共享授权；记录团队所属命题 | User、PaperAsset、ReviewJob |

属性：`teamId`、`teamName`、`members`、`projectName`。

### 5.3 PaperAsset（论文资产）

| Class | Responsibilities | Collaborators |
|---|---|---|
| PaperAsset | 接收论文文件；记录 SHA-256 指纹和版本；维护解析状态；提供证据块索引 | User、Team、EvidenceBlock、ReviewJob |

属性：`assetId`、`title`、`fileType`、`sha256`、`version`、`parseStatus`。

### 5.4 EvidenceBlock（证据块）

| Class | Responsibilities | Collaborators |
|---|---|---|
| EvidenceBlock | 保存论文原文片段；提供页码、段落或行号定位；支持 Finding 和 StageResult 引用 | PaperAsset、StageResult、Finding |

属性：`blockId`、`text`、`page`、`paragraph`、`lineStart`、`lineEnd`、`quoteHash`。

### 5.5 RubricProfile（评价量表）

| Class | Responsibilities | Collaborators |
|---|---|---|
| RubricProfile | 保存评价指标和权重；校验权重总和；发布并冻结可用版本 | User、ReviewJob、ReviewReport |

属性：`rubricId`、`name`、`version`、`criteria`、`weights`、`published`。

### 5.6 ReviewJob（评审任务）

| Class | Responsibilities | Collaborators |
|---|---|---|
| ReviewJob | 绑定论文和量表；推进评审生命周期；保存进度、失败和重试信息；汇总阶段结果 | User、PaperAsset、RubricProfile、StageResult、Finding、Recommendation |

属性：`reviewId`、`status`、`serviceType`、`createdAt`、`updatedAt`、`inputHash`。

### 5.7 StageResult（阶段结果）

| Class | Responsibilities | Collaborators |
|---|---|---|
| StageResult | 保存七阶段中的一个阶段结果；记录分数、理由、证据引用和 stale 状态 | ReviewJob、EvidenceBlock、Finding |

属性：`stageId`、`score`、`rationale`、`evidenceIds`、`stale`。

### 5.8 Finding（评审发现）

| Class | Responsibilities | Collaborators |
|---|---|---|
| Finding | 描述论文问题；标记严重级别和结论；绑定证据；提供后续建议入口 | ReviewJob、EvidenceBlock、Recommendation |

属性：`findingId`、`title`、`severity`、`verdict`、`evidenceIds`、`resolvedStatus`。

### 5.9 Recommendation（优化建议）

| Class | Responsibilities | Collaborators |
|---|---|---|
| Recommendation | 给出修改动作；定义验收标准；保存优先级和人工编辑历史 | Finding、User、ReviewJob |

属性：`recommendationId`、`action`、`acceptance`、`priority`、`owner`、`history`。

### 5.10 ReviewReport（评审报告）

| Class | Responsibilities | Collaborators |
|---|---|---|
| ReviewReport | 汇总评审结果；展示证据和建议；支持 Markdown/JSON 导出；记录生成版本 | ReviewJob、RubricProfile、User |

属性：`reportId`、`reviewId`、`format`、`generatedAt`、`reportVersion`。

## 6. 主事件流

1. 用户登录并选择拥有权限的论文资产。
2. 系统检查文件格式、大小和 SHA-256 指纹。
3. 系统将论文解析为带页码、段落或行号的证据块。
4. 用户选择已发布的评价量表和评审服务，创建评审任务。
5. 系统冻结论文资产、量表版本和输入哈希。
6. 评审任务按问题识别、问题表述、假设、模型构造、求解、代码实现、结果分析顺序执行。
7. 每个阶段保存分数、理由、证据引用和阶段状态。
8. 系统汇总 Finding、Claim、Obligation 和 Recommendation。
9. 用户查看 Finding，并跳转到证据块定位。
10. 用户编辑论文后上传新版本，系统创建新的资产版本并进行复审。
11. 系统展示历史问题的已解决/未解决状态，并导出评审报告。

