# archive · 历史归档区

> 这里的内容**不再维护、不再作为后续实验基础**。保留是为了留痕与可追溯，不是因为还会用到。

---

## 为什么有这个目录

2026-10-28，课程实验方向从「**数学建模论文评审与优化服务平台**」切换为「**数学建模比赛管理系统**」。

切换后，旧方向产生的以下内容失去了继续演进的必要：

- 旧方向的需求分析、SRS、Demo 原型（实验一 ×3 份不同版本）
- 旧方向的业务对象与用例建模（实验二）
- 旧方向的可运行产品代码（本地论文评审工作台）
- 旧方向的数模分析脚本包

同时，仓库根目录还散落着一批空白报告模板、课程资料压缩包、与两个方向都无关的参考样例。这些一并收进本目录，让根目录只剩「主线 + 课程资料 + 归档」三块。

---

## 目录说明

### `legacy-paper-review/` — 旧方向「论文评审平台」

| 子路径 | 内容 | 备注 |
|---|---|---|
| `experiment-1-draft/` | 实验一完成稿 + `exp1/` 过程文档（10 个文件） | 内容最简的一版 |
| `experiment-1-team3/` | 实验一完成稿 + `exp1/` 过程文档（11 个文件） | `srs_manual.md` 11.1KB，是四版里最详实的 |
| `experiment-1-copy/` | 实验一完成稿 + `exp1/` 过程文档（10 个文件） | 「另存」版本 |
| `experiment-2/` | 实验二业务对象与用例建模（7 个文件） | 与主线版本的 `business_objects.md` 内容不同（8.5KB vs 10.7KB） |
| `product-source/` | 旧方向产品源码 `Evaluation-of-Mathematical-Modeling-Papers` | **内含独立 `.git`**，remote 指向 `git@github.com:dessert28/Evaluation-of-Mathematical-Modeling-Papers.git` |
| `product-package/` | 旧方向产品的整理副本 `math-modeling-paper-review` | 无 `.git`，便于移交的打包版 |
| `mathematical-modeling.zip` | 452MB，57758 个条目 | 旧方向的数模分析脚本 + Excel 结果，含 `.venv/`（占绝大部分体积）与 `.idea/` |
| `可行性分析与Agent接入方案.md` | 旧方向技术可行性分析 | — |
| `实验一功能性需求分析_填写指南.md` | 旧方向报告填写指南 | 开头明确写「项目方向：数学建模论文评审与优化服务平台」 |
| `用户说明书_V1.0.pdf` | 旧方向产品说明书 | 8.8MB |
| `manual_extracted.txt` | 从说明书中抽取的文本 | 中间产物 |

> 三份实验一目录的 MD5 聚合值互不相同（已逐文件哈希验证），因此**没有合并**，全部保留。

### `course-templates/` — 空白实验报告模板

4 份 `实验一/实验二` 的空白模板 docx。正文是「一、实验目的…」的标准模板结构，**不是完成稿**。已交付的完成稿在 `competition-management/experiments/` 下。

### `references/` — 无关参考样例

`图书借阅系统用例图与用例说明.docx`，与两个方向都无关，仅作 UML 画法参考。

### `packages/` — 原始压缩包

已完成解压、内容已在别处的压缩包：`软件工程实验资料.zip`（90MB）、`实验二（材料）.rar`（13.7MB）。

### `_acl-recovery/` — 权限诊断报告

整理过程中有一次 Windows 文件权限被拒绝，此目录保存当时的诊断报告，可删除。

---

## 恢复方法

### 恢复旧方向产品源码的 git 仓库

```powershell
cd archive\legacy-paper-review\product-source
git remote -v          # 应显示 origin git@github.com:dessert28/Evaluation-of-Mathematical-Modeling-Papers.git
git status
git log --oneline -5
```

移动目录不影响 remote 关联（remote 是绝对 URL），提交历史完整保留。

### 把某个归档内容移回主线

```powershell
Move-Item -LiteralPath "archive\legacy-paper-review\experiment-2" -Destination "competition-management\experiments\exp2-legacy-对照版"
```

移回前请先确认它确实要参与后续工作，否则不如继续留在归档区。

### 从大包里取单个文件

```powershell
# mathematical-modeling.zip 里只有 .py 和 .xlsx，去掉 .venv 后约几 MB
Add-Type -AssemblyName System.IO.Compression.FileSystem
$z = [System.IO.Compression.ZipFile]::OpenRead("archive\legacy-paper-review\mathematical-modeling.zip")
$z.Entries | Where-Object { $_.FullName -notmatch '\.venv|\.idea' } | Select-Object FullName, Length
$z.Dispose()
```

---

## 为什么这些没有直接删掉

1. **课程留痕**：方向切换是真实发生过的决策，旧材料是决策依据的一部分
2. **可复用的部分**：旧方向的 `srs_manual.md`、`business_objects.md` 结构比主线版本更完整，写实验三时可能参考
3. **产品代码有价值**：`product-source/` 是一个能跑起来的 Python + React 本地应用，其中的 PDF 解析、LLM 调用封装可以直接搬到比赛平台的 `docproc` 队列里
4. **删除不可逆**：留在磁盘上的成本远低于误删的代价
