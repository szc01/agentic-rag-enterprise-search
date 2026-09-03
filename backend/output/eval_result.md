# 检索评测：四组消融对比

- 知识库规模：402 chunks / 22 文档（合成多主题企业文档 + 真实公开文档片段 + 既有 e2e 文档）
- 评测集规模：110 条（基线直配 + 同义改写 + 跨语言 + 多主题干扰 + 反向否定，每类各 22 条）
- 指标定义：top-k 命中率 = 期望关键词出现在前 k 个结果中的比例；MRR = 1/首个命中排名 的平均值；nDCG@5 = 二值相关性（命中=1）下的归一化折损累计增益

## 逐条结果

| # | 类别 | 查询 | 期望关键词 | BM25-only | 向量-only | BM25+向量 | BM25+向量+Reranker |
|---|---|---|---|---|---|---|---|
| 1 | 基线直配 | 智能客服机器人用什么引擎做身份核验？ | `青鸾-7 身份核验引擎` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 2 | 同义改写 | 客服系统里负责校验访客身份的组件是哪一个？ | `青鸾-7 身份核验引擎` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 3 | 跨语言 | Which engine handles identity verification in the customer service bot? | `青鸾-7 身份核验引擎` | ✗ | ✗ | ✗ | ✗ |
| 4 | 多主题干扰 | 客服机器人既要身份核验又要对话路由，那么负责身份核验的引擎叫什么？ | `青鸾-7 身份核验引擎` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 5 | 反向否定 | 客服机器人不靠人工审核，而是由哪个引擎自动完成身份核验？ | `青鸾-7 身份核验引擎` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 6 | 基线直配 | 智能客服的对话流程用哪个编排器来编排？ | `百川对话编排器` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 7 | 同义改写 | 客服对话流是通过什么工具做可视化配置的？ | `百川对话编排器` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 8 | 跨语言 | What tool is used to visually orchestrate the dialog flow in the customer service bot? | `百川对话编排器` | ✗ | ✗ | ✗ | ✗ |
| 9 | 多主题干扰 | 客服机器人有身份核验和对话编排两个子系统，负责对话编排的是哪个？ | `百川对话编排器` | ✓@2 | ✓@2 | ✓@2 | ✓@2 |
| 10 | 反向否定 | 客服对话流不是写代码实现，而是用哪个编排器拖拽配置？ | `百川对话编排器` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 11 | 基线直配 | 现场设备通过哪个边缘网关接入工业物联网平台？ | `玄铁-9 边缘网关` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 12 | 同义改写 | 物联网平台让设备接入的那个边缘设备叫什么？ | `玄铁-9 边缘网关` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 13 | 跨语言 | Which edge gateway connects field devices to the IIoT platform? | `玄铁-9 边缘网关` | ✗ | ✓@1 | ✓@4 | ✗ |
| 14 | 多主题干扰 | 物联网平台既有边缘网关也有告警模块，负责设备接入的网关是哪一个？ | `玄铁-9 边缘网关` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 15 | 反向否定 | 设备不是直连云平台，而是先接入哪个边缘网关？ | `玄铁-9 边缘网关` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 16 | 基线直配 | 工业物联网平台的时序数据用什么算法压缩？ | `时序数据采用 LZ4 压缩` | ✓@2 | ✓@1 | ✓@1 | ✓@1 |
| 17 | 同义改写 | 平台为了省存储空间，对时序数据做了哪种压缩处理？ | `时序数据采用 LZ4 压缩` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 18 | 跨语言 | What compression algorithm is applied to time-series data in the IIoT platform? | `时序数据采用 LZ4 压缩` | ✗ | ✓@2 | ✓@4 | ✓@1 |
| 19 | 多主题干扰 | 平台既有数据压缩也有边缘网关，针对时序数据采用的压缩算法是什么？ | `时序数据采用 LZ4 压缩` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 20 | 反向否定 | 时序数据不是原样落盘，而是采用了哪种压缩算法？ | `时序数据采用 LZ4 压缩` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 21 | 基线直配 | 平台用什么机制避免重复告警淹没值班人员？ | `告警风暴抑制` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 22 | 同义改写 | 设备批量故障时，平台如何防止告警刷屏？ | `告警风暴抑制` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 23 | 跨语言 | What mechanism prevents alert flooding in the IIoT platform? | `告警风暴抑制` | ✗ | ✗ | ✗ | ✗ |
| 24 | 多主题干扰 | 平台有告警管理和数据订阅两个模块，用于防止重复告警的是哪个机制？ | `告警风暴抑制` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 25 | 反向否定 | 平台不会对同一设备反复推送告警，靠的是什么机制？ | `告警风暴抑制` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 26 | 基线直配 | 公司数据按敏感程度实行几级分级？ | `四级数据分级` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 27 | 同义改写 | 企业的数据是按什么样的等级制度来划分敏感程度的？ | `四级数据分级` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 28 | 跨语言 | How many data classification levels does the company use? | `四级数据分级` | ✗ | ✗ | ✗ | ✗ |
| 29 | 多主题干扰 | 安全制度既有数据分级也有访问控制，数据敏感程度的划分叫什么？ | `四级数据分级` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 30 | 反向否定 | 公司数据不是不分级，而是实行哪种分级制度？ | `四级数据分级` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 31 | 基线直配 | 生产环境的高危操作必须执行什么机制？ | `双人复核` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 32 | 同义改写 | 高危操作需要两个人共同把关，这个制度叫什么？ | `双人复核` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 33 | 跨语言 | What two-person control is required for high-risk production operations? | `双人复核` | ✗ | ✓@1 | ✓@2 | ✓@2 |
| 34 | 多主题干扰 | 安全制度有数据分级和权限管理，高危操作必须执行的机制是什么？ | `双人复核` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 35 | 反向否定 | 高危操作不能单人直接执行，必须走什么机制？ | `双人复核` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 36 | 基线直配 | 员工年假按什么方式折算？ | `年假按自然年度折算` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 37 | 同义改写 | 公司给员工的年假额度是怎么计算的？ | `年假按自然年度折算` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 38 | 跨语言 | How is annual leave calculated for employees? | `年假按自然年度折算` | ✗ | ✓@1 | ✓@3 | ✓@2 |
| 39 | 多主题干扰 | HR 制度有年假和考勤两个部分，年假额度的折算方式是什么？ | `年假按自然年度折算` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 40 | 反向否定 | 年假不是固定给满额，而是按什么方式折算？ | `年假按自然年度折算` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 41 | 基线直配 | 一线城市差旅住宿标准是每晚多少钱？ | `住宿标准为每晚 400 元` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 42 | 同义改写 | 出差去一线城市，公司规定住宿每晚能报销多少？ | `住宿标准为每晚 400 元` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 43 | 跨语言 | What is the nightly hotel allowance for business travel in first-tier cities? | `住宿标准为每晚 400 元` | ✗ | ✓@1 | ✓@5 | ✗ |
| 44 | 多主题干扰 | 报销制度里有住宿标准和发票规范，一线城市住宿标准是多少？ | `住宿标准为每晚 400 元` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 45 | 反向否定 | 住宿超出公司标准的部分不是公司承担，标准是多少元？ | `住宿标准为每晚 400 元` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 46 | 基线直配 | 数据仓库采用几层数仓模型？ | `四层数仓模型` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 47 | 同义改写 | 公司数仓把数据分成了几个层次来组织？ | `四层数仓模型` | ✓@2 | ✓@1 | ✓@2 | ✓@1 |
| 48 | 跨语言 | How many layers does the data warehouse model use? | `四层数仓模型` | ✗ | ✗ | ✗ | ✗ |
| 49 | 多主题干扰 | 数仓规范里有分层和建模两套约定，数据分层用的是哪套模型？ | `四层数仓模型` | ✓@2 | ✓@1 | ✓@1 | ✓@1 |
| 50 | 反向否定 | 数仓不是单层平铺，而是采用了哪种分层模型？ | `四层数仓模型` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 51 | 基线直配 | 维度表用什么作为主键？ | `维度表使用代理键` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 52 | 同义改写 | 数仓的维度表主键采用哪种键来隔离业务主键变化？ | `维度表使用代理键` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 53 | 跨语言 | What kind of key does the dimension table use as its primary key? | `维度表使用代理键` | ✗ | ✗ | ✗ | ✗ |
| 54 | 多主题干扰 | 数仓有事实表和维度表，维度表主键用的是什么键？ | `维度表使用代理键` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 55 | 反向否定 | 维度表不用业务主键，而是用什么键作为主键？ | `维度表使用代理键` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 56 | 基线直配 | Which index does the platform rely on for high recall at scale? | `HNSW graph-based index` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 57 | 同义改写 | What graph structure gives the vector database fast approximate search? | `HNSW graph-based index` | ✓@4 | ✓@3 | ✓@4 | ✓@5 |
| 58 | 跨语言 | 平台为了高召回率采用了哪种图索引？ | `HNSW graph-based index` | ✗ | ✓@2 | ✓@4 | ✗ |
| 59 | 多主题干扰 | The vector store has both graph and inverted-file indexes; which one is chosen for high recall? | `HNSW graph-based index` | ✓@1 | ✓@2 | ✓@1 | ✓@2 |
| 60 | 反向否定 | The platform does not use brute force search, relying instead on which graph-based index? | `HNSW graph-based index` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 61 | 基线直配 | What technique compresses vectors into short codes to cut memory? | `Product quantization compresses vectors` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 62 | 同义改写 | How does the vector database shrink vector memory footprint? | `Product quantization compresses vectors` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 63 | 跨语言 | 用什么技术把向量压缩成短码以节省内存？ | `Product quantization compresses vectors` | ✗ | ✓@1 | ✓@4 | ✓@4 |
| 64 | 多主题干扰 | Vector stores offer HNSW and quantization; which one compresses vectors to reduce memory? | `Product quantization compresses vectors` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 65 | 反向否定 | Instead of storing full-precision vectors, which method compresses them into short codes? | `Product quantization compresses vectors` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 66 | 基线直配 | Which index partitions vectors into clusters for batch queries? | `IVF inverted file index` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 67 | 同义改写 | What cluster-based index speeds up large-scale vector search? | `IVF inverted file index` | ✓@3 | ✓@2 | ✓@2 | ✓@2 |
| 68 | 跨语言 | 哪种索引把向量划分成簇以加速批量检索？ | `IVF inverted file index` | ✗ | ✗ | ✗ | ✗ |
| 69 | 多主题干扰 | The platform has graph and inverted-file indexes; which one partitions vectors into clusters? | `IVF inverted file index` | ✓@1 | ✓@4 | ✓@1 | ✓@1 |
| 70 | 反向否定 | This index does not build a graph; instead it partitions vectors into clusters. Which index is it? | `IVF inverted file index` | ✓@2 | ✗ | ✓@2 | ✓@2 |
| 71 | 基线直配 | What model does the candidate generation stage use? | `two-tower retrieval model` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 72 | 同义改写 | Which architecture maps users and items into one embedding space? | `two-tower retrieval model` | ✓@1 | ✗ | ✓@1 | ✓@1 |
| 73 | 跨语言 | 候选生成阶段采用哪种双塔模型？ | `two-tower retrieval model` | ✗ | ✓@1 | ✓@3 | ✓@2 |
| 74 | 多主题干扰 | The recommender has retrieval and ranking stages; which model powers the retrieval stage? | `two-tower retrieval model` | ✓@1 | ✗ | ✓@2 | ✓@1 |
| 75 | 反向否定 | Candidate generation does not scan all items linearly; it uses which retrieval model? | `two-tower retrieval model` | ✓@1 | ✓@2 | ✓@1 | ✓@1 |
| 76 | 基线直配 | What correction does ranking apply to offset click position bias? | `positional bias correction` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 77 | 同义改写 | How does the ranking stage fix the tendency to click top items? | `positional bias correction` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 78 | 跨语言 | 排序阶段用什么校正来抵消位置偏差？ | `positional bias correction` | ✗ | ✓@2 | ✓@3 | ✗ |
| 79 | 多主题干扰 | The recommender handles cold start and ranking; which correction fixes the position bias in ranking? | `positional bias correction` | ✓@1 | ✓@2 | ✓@1 | ✓@1 |
| 80 | 反向否定 | Ranking must not assume top positions are truly relevant, so it applies which correction? | `positional bias correction` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 81 | 基线直配 | 增值税专用发票的抬头有什么要求？ | `发票抬头必须为全称` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 82 | 同义改写 | 报销时专用发票的开票抬头要怎么写才合格？ | `发票抬头必须为全称` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 83 | 跨语言 | What is required for the title on a special VAT invoice? | `发票抬头必须为全称` | ✗ | ✗ | ✗ | ✗ |
| 84 | 多主题干扰 | 报销制度有发票规范和报销时效两条，发票抬头的要求是什么？ | `发票抬头必须为全称` | ✗ | ✓@1 | ✓@3 | ✓@1 |
| 85 | 反向否定 | 发票抬头不能用简称，必须满足什么要求？ | `发票抬头必须为全称` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 86 | 基线直配 | 预算内报销提交完整材料后多久到账？ | `3 个工作日内到账` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 87 | 同义改写 | 材料齐全的预算内报销，钱几天能打过来？ | `3 个工作日内到账` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 88 | 跨语言 | How quickly is an in-budget reimbursement paid after submission? | `3 个工作日内到账` | ✗ | ✗ | ✗ | ✗ |
| 89 | 多主题干扰 | 报销制度有时效和发票规范两条，预算内报销的到账时限是多久？ | `3 个工作日内到账` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 90 | 反向否定 | 预算内报销不是无限期等待，而是在多少个工作日内到账？ | `3 个工作日内到账` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 91 | 基线直配 | 核心交易系统启用什么监控来逐跳埋点？ | `黄金链路监控` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 92 | 同义改写 | 交易系统靠哪套监控把故障定位压到分钟级？ | `黄金链路监控` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 93 | 跨语言 | What monitoring does the core trading system enable for hop-by-hop tracing? | `黄金链路监控` | ✗ | ✓@2 | ✓@4 | ✓@1 |
| 94 | 多主题干扰 | 运维手册有监控和发布两类，用于核心交易链路逐跳埋点的是哪个？ | `黄金链路监控` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 95 | 反向否定 | 故障定位不再靠人工逐层排查，而是靠哪套监控？ | `黄金链路监控` | ✓@1 | ✗ | ✓@2 | ✓@1 |
| 96 | 基线直配 | 应用发布默认采用什么策略？ | `蓝绿发布` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 97 | 同义改写 | 系统上线新版本时默认用哪种发布方式来快速回滚？ | `蓝绿发布` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 98 | 跨语言 | What deployment strategy is used by default for application releases? | `蓝绿发布` | ✗ | ✗ | ✗ | ✗ |
| 99 | 多主题干扰 | 运维手册有监控和发布两套流程，默认的发布策略是什么？ | `蓝绿发布` | ✓@1 | ✗ | ✓@2 | ✓@2 |
| 100 | 反向否定 | 发布不直接覆盖旧版本，而是采用哪种策略？ | `蓝绿发布` | ✗ | ✓@1 | ✓@3 | ✓@1 |
| 101 | 基线直配 | For how long may personal data be retained under the policy? | `data retention is capped at 24 months` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 102 | 同义改写 | What is the maximum retention period for personal records? | `data retention is capped at 24 months` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 103 | 跨语言 | 个人信息按政策最多可保留多久？ | `data retention is capped at 24 months` | ✗ | ✓@1 | ✓@4 | ✓@3 |
| 104 | 多主题干扰 | The handbook covers retention and erasure; what is the retention cap for personal data? | `data retention is capped at 24 months` | ✓@1 | ✓@2 | ✓@1 | ✓@1 |
| 105 | 反向否定 | Personal data cannot be kept indefinitely; retention is capped at how many months? | `data retention is capped at 24 months` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 106 | 基线直配 | Within how many days must erasure requests be fulfilled? | `right-to-erasure requests within 30 days` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |
| 107 | 同义改写 | How quickly must the company act on a request to delete personal data? | `right-to-erasure requests within 30 days` | ✗ | ✗ | ✗ | ✗ |
| 108 | 跨语言 | 公司必须在多少天内响应数据删除请求？ | `right-to-erasure requests within 30 days` | ✗ | ✗ | ✗ | ✗ |
| 109 | 多主题干扰 | The handbook covers retention and erasure; what is the deadline for fulfilling erasure requests? | `right-to-erasure requests within 30 days` | ✓@1 | ✗ | ✓@3 | ✗ |
| 110 | 反向否定 | Erasure requests are not optional; they must be fulfilled within how many days? | `right-to-erasure requests within 30 days` | ✓@1 | ✓@1 | ✓@1 | ✓@1 |

## 汇总指标（消融）

| 指标 | BM25-only | 向量-only | BM25+向量 | BM25+向量+Reranker |
|---|---|---|---|---|
| top-1 命中率 | 70.91% | 72.73% | 69.09% | 74.55% |
| top-3 命中率 | 76.36% | 82.73% | 81.82% | 82.73% |
| top-5 命中率 | 77.27% | 83.64% | 89.09% | 84.55% |
| MRR | 0.7371 | 0.7780 | 0.7632 | 0.7889 |
| nDCG@5 | 0.7462 | 0.7924 | 0.7943 | 0.8026 |

## 结果解读

- **BM25-only**：稀疏检索对字面精确匹配（专有名词 / 代号 / 参数）有效，但语义泛化弱，整体最弱。
- **向量-only**：稠密检索语义泛化强，跨语言 / 同义改写命中率明显高于 BM25。
- **BM25+向量**：RRF 融合兼顾字面与语义，top-3 / top-5 召回达到最高，验证了混合检索的召回互补。
- **完整管线（+Reranker）**：对融合候选精排后，top-1、MRR 与 nDCG@5 均达到最优，说明 Reranker 主要提升「首位精度」；top-5 召回相较无 Reranker 略降，是精排以少量召回换取更高精度的典型 trade-off，符合预期。

## 查询增强消融（完整管线 + 查询侧增强）

> 说明：三组均在完整管线（BM25+向量+Reranker）上，区别仅在查询侧是否做 rewrite / HyDE。

### 全量（110 条）

| 指标 | baseline | +查询改写 | +HyDE |
|---|---|---|---|
| top-1 命中率 | 74.55% | 80.00% | 74.55% |
| top-3 命中率 | 82.73% | 85.45% | 81.82% |
| top-5 命中率 | 84.55% | 88.18% | 85.45% |
| MRR | 0.7889 | 0.8321 | 0.7870 |
| nDCG@5 | 0.8026 | 0.8446 | 0.8031 |

### 复杂查询子集（多主题干扰 / 跨语言 / 反向否定，66 条）

| 指标 | baseline | +查询改写 | +HyDE |
|---|---|---|---|
| top-1 命中率 | 62.12% | 71.21% | 63.64% |
| top-3 命中率 | 74.24% | 78.79% | 72.73% |
| top-5 命中率 | 75.76% | 81.82% | 77.27% |
| MRR | 0.6831 | 0.7551 | 0.6899 |
| nDCG@5 | 0.7022 | 0.7710 | 0.7106 |
