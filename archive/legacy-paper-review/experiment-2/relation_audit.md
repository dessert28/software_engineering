# 类间关系审查

## 1. 审查范围

本次审查覆盖 `initial_class_diagram.puml` 中的继承、聚合和关联关系。审查依据是 CRC 卡片和业务语义，而不是代码实现便利性。

## 2. 关系审查表

| 关系 | 初始判断 | 人工审查结论 | 判断依据 |
|---|---|---|---|
| User—Student | 继承 | 保留 | Student“是一种”User，继承用户身份和权限基础属性 |
| User—Teacher | 继承 | 保留 | Teacher“是一种”User，具有教师专属量表管理职责 |
| User—Operator | 继承 | 保留 | Operator“是一种”User，具有任务和审计管理职责 |
| PaperAsset—EvidenceBlock | 聚合 | 保留为组合/聚合 | EvidenceBlock 是论文解析后的组成部分；脱离论文资产不能作为独立业务资产使用 |
| ReviewJob—StageResult | 聚合 | 保留 | StageResult 是某个评审任务的阶段结果，任务删除或重建时结果生命周期随任务管理 |
| ReviewJob—Finding | 聚合 | 保留 | Finding 由评审任务产生并归属于该任务 |
| ReviewJob—Recommendation | 聚合 | 保留 | Recommendation 服务于任务中的 Finding，并随任务版本追踪 |
| ReviewJob—PaperAsset | 关联 | 保留为关联 | 论文资产可以被多个版本任务引用，二者不是继承关系，也不表示整体—部分 |
| ReviewJob—RubricProfile | 关联 | 保留为关联 | 任务绑定量表版本，但量表可以独立发布和复用 |
| Finding—EvidenceBlock | 关联 | 保留为关联 | 一个证据块可以支撑多个 Finding，证据块不属于某一条 Finding |
| Recommendation—Finding | 关联 | 保留为关联 | 建议针对 Finding，但建议有独立编辑历史和生命周期 |
| ReviewReport—ReviewJob | 关联 | 保留为关联 | 报告汇总任务结果，可重新生成，不是任务的组成实体 |

## 3. 重点误判检查

### 3.1 继承 vs 聚合

判断问题是“子对象是否是一种父对象”。

- `Student` 是一种 `User`，因此使用继承。
- `Teacher` 是一种 `User`，因此使用继承。
- `PaperAsset` 不是 `EvidenceBlock`，`EvidenceBlock` 也不是 `PaperAsset`，二者只能是整体—部分关系。
- `ReviewJob` 不是 `StageResult`，阶段结果也不是任务的一种，因此不能使用继承。

### 3.2 聚合 vs 关联

判断问题是“整体销毁或失效时，部分对象是否仍有独立业务意义”。

- 论文资产解析产生的证据块依赖该论文版本，采用聚合/组合语义。
- 评审任务产生的阶段结果、Finding 和建议属于该次任务，采用聚合语义。
- 量表可以脱离任务独立发布和复用，因此 `ReviewJob—RubricProfile` 是关联。
- 证据块可以被多条 Finding 引用，因此 `Finding—EvidenceBlock` 是关联，不是聚合。

## 4. 多重性检查

- 一个 `User` 可以属于多个 `Team`，一个 `Team` 至少包含一个 `User`。
- 一个 `PaperAsset` 可以包含零到多个 `EvidenceBlock`。
- 一个 `ReviewJob` 绑定一个 `PaperAsset` 和一个 `RubricProfile`。
- 一个 `ReviewJob` 包含七个或部分已完成的 `StageResult`。
- 一个 `ReviewJob` 可以产生零到多个 `Finding` 和 `Recommendation`。
- 一个 `Finding` 可以引用多个 `EvidenceBlock`，一个证据块也可以被多个 Finding 引用。
- 一个 `ReviewJob` 可以生成零到多个 `ReviewReport`。

## 5. 审查结论

初始类图中的关系均符合业务语义。审查重点是避免把“属于某个任务”误写为继承，也避免把可独立存在的量表和证据块误写为聚合。最终类图只保留业务分析层需要的关系，不引入数据库外键、API 客户端等实现关系。

