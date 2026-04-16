# ClinicalTrials.gov 与 PubMed 开放能力调研

## 1. 文档目的

本文档用于回答两个问题：

1. `ClinicalTrials.gov` 与 `PubMed` 官方公开接口/文档，实际开放了哪些能力与信息
2. 针对当前系统要完成的四类任务，这些信息里哪些真正有价值

本文档的目的不是立刻冻结最终 schema，而是先做“来源能力摸底”。在这一步完成之前，不建议过早确定规范化记录与聚合对象的字段设计。

## 2. 调研范围与结论先行

本次调研聚焦官方公开文档，不依赖第三方博客或二手整理。

截至本次调研，结论可以先概括为：

- `ClinicalTrials.gov` 非常适合支撑“在研管线概览”与竞争态势基础盘点
- `PubMed` 非常适合支撑“近期研究动态”，也可以部分支撑“靶点概述”
- 两者联合后，已经足以完成 V1 的核心链路
- 但如果希望“靶点概述”中的“基本信息与作用机制”更加稳定、规范、接近知识卡片，而不只是文献总结，则后续大概率仍需补充一个靶点知识型数据源
- 因此，当前阶段更适合先定义“字段候选池”和“任务-字段映射”，而不是直接拍板最终 schema

## 3. 当前四类任务

当前目标任务为：

- **靶点概述**：靶点的基本信息与作用机制
- **在研管线概览**：按研发阶段分布的在研项目统计，主要竞争企业及其产品
- **近期研究动态**：近期关键文献发现的摘要与解读
- **竞争格局判断**：当前竞争态势、潜在风险与机会

后续的 schema 是否合理，应以这四类任务是否能被稳定支持为判断标准，而不是以“某个源返回了哪些字段”为标准。

## 4. ClinicalTrials.gov

### 4.1 官方开放方式

ClinicalTrials.gov 提供官方 API，并公开了以下文档：

- API 总览
- OpenAPI 描述
- Study Data Structure
- Search Areas 说明

从官方文档看，ClinicalTrials.gov 的核心能力是：

- 按研究条件、疾病、干预、试验状态等维度检索 study
- 获取结构化的 study record
- 获取试验状态、阶段、申办方、设计、地点、结局等完整字段
- 判断数据更新时间

官方还说明其 API 数据在工作日按日刷新，可通过版本接口中的 `dataTimestamp` 观察数据刷新状态。

### 4.2 对四类任务最有价值的信息类别

以下是从任务视角出发，当前最值得关注的信息类别。

#### A. 试验身份与描述

- `NCT ID`
- `briefTitle`
- `officialTitle`
- `acronym`
- `briefSummary`
- `detailedDescription`

价值：

- 用于报告中的基础说明
- 用于后续证据追溯
- 用于生成“该项目在研究什么”的自然语言摘要

#### B. 竞争主体

- `leadSponsor`
- `collaborators`

价值：

- 直接支撑“主要竞争企业及其产品”
- 可用于聚合 sponsor 维度的管线分布

#### C. 管线状态与阶段

- `overallStatus`
- `lastKnownStatus`
- `studyType`
- `phase`

价值：

- 是“在研管线概览”的核心结构化基础
- 是竞争格局判断的重要输入

#### D. 时间轴信息

- `startDate`
- `primaryCompletionDate`
- `completionDate`
- `studyFirstPostDate`
- 其他更新时间相关字段

价值：

- 用于判断项目新旧、推进速度与是否仍具活跃度
- 有助于竞争态势中的“快慢、密度、时间窗口”判断

#### E. 干预与产品信息

- `interventions`
- `intervention type`
- `intervention name`
- `other intervention names`
- `armGroups`

价值：

- 直接支撑“主要竞争产品”识别
- 有助于区分抗体、小分子、联合治疗等不同技术路径

#### F. 疾病与适应症上下文

- `conditions`
- `keywords`
- `conditionBrowseModule`
- `interventionBrowseModule`

价值：

- 用于限定检索上下文
- 有助于做适应症层面的竞争分析
- `browse` / MeSH 相关结构对后续标准化与去歧义很有帮助

#### G. 规模与地域

- `enrollment`
- `locations`
- 国家、地区、site 状态

价值：

- 用于判断试验规模、全球化程度与执行广度
- 可以辅助竞争格局分析中的“扩张速度”和“区域覆盖”

#### H. 临床结局与结果

- `primaryOutcome`
- `secondaryOutcome`
- `hasResults`
- results section 中的 baseline、outcome、adverse events 等

价值：

- 对“竞争格局判断”价值很高
- 如果有 posted results，可辅助判断项目质量、疗效信号与风险信号

### 4.3 ClinicalTrials.gov 的适配性判断

对于当前四类任务，ClinicalTrials.gov 的适配性可以概括为：

- 对“在研管线概览”是主力来源
- 对“竞争格局判断”是主力来源之一
- 对“近期研究动态”价值有限，更多是试验动态，不是学术研究动态
- 对“靶点概述”只能提供间接上下文，不能替代机制知识来源

## 5. PubMed

### 5.1 官方开放方式

PubMed 官方开放方式并不是单一“PubMed REST API”，而是 NCBI E-utilities 体系。典型用法一般是：

- `ESearch`：先检索 PMID 列表
- `ESummary`：获取摘要级 metadata
- `EFetch`：获取更完整的记录
- `ELink`：获取关联关系

官方文档还说明了：

- 不带 API key 时，建议每秒不超过 `3` 个请求
- 带 API key 时，默认可到每秒 `10` 个请求
- 大批量任务建议安排在周末或美东夜间执行

### 5.2 对四类任务最有价值的信息类别

#### A. 文献身份与来源

- `PMID`
- DOI 或其他 article identifier
- journal
- publication date

价值：

- 作为文献证据的稳定主键
- 支撑时间排序、来源可信度描述和报告引用

#### B. 文献主体内容

- `ArticleTitle`
- `AbstractText`
- `OtherAbstract`

价值：

- 是“近期研究动态”生成的核心材料
- 也是“靶点概述”中作用机制总结的主要输入

说明：

官方 XML 文档显示 `AbstractText` 可带 label 等结构信息，这意味着结构化摘要是可以直接利用的。

#### C. 作者与机构

- `AuthorList`
- `Affiliation`

价值：

- 可辅助判断主要研究团队、机构与潜在学术竞争格局
- 有助于发现某一方向由哪些研究中心主导

#### D. 主题语义

- `MeshHeadingList`
- `KeywordList`
- 搜索标签如 `[tiab]`、`[mh]`、`[majr]`、`[ot]`

价值：

- 对于靶点检索、主题归类和去歧义非常重要
- 是后续做主题聚类或机制方向归纳的重要基础

#### E. 文献类型

- `PublicationTypeList`

价值：

- 可区分 review、clinical trial、systematic review 等不同证据类型
- 有助于控制“近期研究动态”中不同文献类型的权重

#### F. 资助与外部资源

- `GrantList`
- `DataBankList`

价值：

- `GrantList` 可辅助识别资助来源与研究背景
- `DataBankList` 很重要，因为官方文档明确存在外部 databank 信息，其中包括 `ClinicalTrials.gov` 与 `NCT` accession number 的场景

这意味着：

- 文献与试验之间有机会做结构化关联
- 对后续“文献证据回挂到具体试验”非常有帮助

#### G. 纠错与关联文献

- `CommentsCorrectionsList`
- `ELink` 关联

价值：

- 可辅助识别更正、评论、相关研究链条
- 对研究动态和证据质量判断有辅助价值

### 5.3 PubMed 的适配性判断

对于当前四类任务，PubMed 的适配性可以概括为：

- 对“近期研究动态”是主力来源
- 对“靶点概述”可提供主要内容素材
- 对“竞争格局判断”提供辅助证据，尤其是方向热度、研究类型和关联试验信息
- 对“在研管线概览”不是主力，因为其结构化的管线、阶段、状态信息远不如 ClinicalTrials.gov 稳定

## 6. 两源联合后的价值

ClinicalTrials.gov 与 PubMed 联合后，形成的是“注册试验视角 + 学术文献视角”的互补关系：

- ClinicalTrials.gov 负责结构化管线、阶段、状态、竞争主体
- PubMed 负责研究内容、研究动态、机制线索、文献证据
- 两者通过靶点词、干预词、疾病词和可能的 `NCT` 号建立关联

这对系统设计的启发是：

- V1 不应只做“统一字段平铺”
- 更应该重视“跨来源证据关联”和“任务导向的中间表示”

## 7. 对 schema 设计的直接启发

### 7.1 为什么现在不适合定死字段

当前不建议直接冻结 `TrialRecord`、`LiteratureRecord`、`EvidenceBundle` 的最终字段，原因有三点：

- 还没有完成“任务 -> 字段候选 -> 来源”的映射
- 还没有验证哪些字段在官方接口里稳定可得
- 还没有区分“源字段”“中间标准化字段”“分析派生字段”三种不同层次

### 7.2 当前更合理的做法

在总体技术方案中，建议把这几类对象先标记为 `TBD`：

- 规范化试验记录 schema：`TBD`
- 规范化文献记录 schema：`TBD`
- 聚合对象 schema：`TBD`

同时，在设计层先冻结三层概念，而不是冻结具体字段：

- `source_raw`
  - 原始响应、来源、抓取时间、查询上下文
- `source_normalized`
  - 用于跨源整理的中间结构，字段待调研后确定
- `analysis_ready`
  - 面向四类任务的派生特征，字段待任务映射后确定

### 7.3 下一步最值得做的事

下一步最值得做的不是继续猜 schema，而是先产出一张“任务-字段候选矩阵”，至少回答：

- 哪个任务需要哪些信息
- 这些信息来自哪个源
- 官方是否稳定开放
- 是原始字段，还是后续派生特征

只有这一步完成后，schema 才值得正式落地。

## 8. 当前阶段的几个明确风险

### 8.1 把文献字段当成结构化管线字段

风险：

- 容易用 PubMed 去承担它并不擅长的“管线/状态/阶段”职责

应对：

- 明确 PubMed 主要用于研究动态、机制线索和关联证据，不作为主管线源

### 8.2 把试验注册字段当成机制知识字段

风险：

- 容易高估 ClinicalTrials.gov 对靶点作用机制说明的能力

应对：

- 把 ClinicalTrials.gov 作为竞争与管线源，而不是机制知识源

### 8.3 过早冻结 schema

风险：

- 设计出的字段表可能只是“源字段拷贝”，并不真正服务最终报告任务

应对：

- 先保留 `TBD`
- 先做任务-字段映射

## 9. 官方参考文档

### ClinicalTrials.gov

- API 总览：<https://clinicaltrials.gov/data-about-studies/learn-about-api>
- Study Data Structure：<https://clinicaltrials.gov/data-api/about-api/study-data-structure>
- Search Areas：<https://clinicaltrials.gov/data-api/about-api/search-areas>

### NCBI / PubMed

- NCBI APIs 总览：<https://www.ncbi.nlm.nih.gov/home/develop/api/>
- E-utilities 总体说明：<https://www.ncbi.nlm.nih.gov/books/NBK25497/>
- E-utilities 参数细节：<https://www.ncbi.nlm.nih.gov/books/NBK25499/>
- PubMed User Guide：<https://pubmed.ncbi.nlm.nih.gov/help/>
- PubMed XML 文档首页：<https://dtd.nlm.nih.gov/ncbi/pubmed/doc/out/250101/index.html>
- `AbstractText`：<https://dtd.nlm.nih.gov/ncbi/pubmed/doc/out/250101/el-AbstractText.html>
- `DataBank`：<https://dtd.nlm.nih.gov/ncbi/pubmed/doc/out/250101/el-DataBank.html>
- `GrantList`：<https://dtd.nlm.nih.gov/ncbi/pubmed/doc/out/250101/el-GrantList.html>
- `PublicationTypeList`：<https://dtd.nlm.nih.gov/ncbi/pubmed/doc/out/250101/el-PublicationTypeList.html>

## 10. 小结

如果只看 V1，可先把这两源作为核心输入跑通系统：

- `ClinicalTrials.gov` 负责管线和竞争结构
- `PubMed` 负责研究动态和机制语义材料

但从设计角度，当前最重要的不是继续细化 schema，而是把 schema 暂时保留为 `TBD`，并优先完成“任务-字段候选矩阵”。只有这样，后续的标准化对象与聚合对象才不会偏离最终报告目标。
