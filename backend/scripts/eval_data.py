"""Day 7 合成企业知识库 + 检索评测集（统一数据源）

职责：
  1. 生成 300-500 个 chunk 的合成企业知识库（多主题、互不相关，制造检索干扰）。
  2. 生成 100+ 条评测样本，覆盖 5 类难度：
     基线直配 / 同义改写 / 跨语言 / 多主题干扰 / 反向否定。

约定：
  - 每个事实（FACT）带一个 `key`（锚点短语），`key` 必须是库内 chunk 的真实子串，
    用作检索相关性标签（命中判断）。`statement` 是含 `key` 的完整句子，被写入文档正文。
  - 每事实派生 5 条评测样本（5 类各一），故 EVAL_ITEMS = 5 × len(FACTS)。

注意：这是实验用的合成语料，内容为程序化生成的企业文档模板，非真实客户数据。
"""
from __future__ import annotations

import random

# ── 领域定义（多主题、互不相关）────────────────────────────────────────
# lang 决定文档与 filler 的语言；terms 用于生成逼真的填充段落。
DOMAINS = [
    {"id": "cs", "title": "智能客服机器人产品手册", "category": "产品手册", "lang": "zh",
     "terms": ["意图识别", "槽位填充", "多轮澄清", "工单流转", "知识库同步", "坐席接管",
               "情绪识别", "会话质检", "转人工策略", "对话日志"]},
    {"id": "iot", "title": "工业物联网平台技术白皮书", "category": "技术白皮书", "lang": "zh",
     "terms": ["边缘计算", "协议适配", "设备影子", "规则引擎", "断点续传", "数据订阅",
               "批量导入", "远程升级", "告警通知", "可视化大屏"]},
    {"id": "sec", "title": "信息安全管理制度", "category": "制度规范", "lang": "zh",
     "terms": ["访问控制", "密码策略", "审计日志", "漏洞扫描", "应急响应", "权限回收",
               "加密传输", "堡垒机", "最小权限", "离职交接"]},
    {"id": "hr", "title": "人力资源与薪酬常见问题", "category": "FAQ", "lang": "zh",
     "terms": ["考勤打卡", "调休申请", "加班审批", "绩效面谈", "社保基数", "公积金",
               "入职材料", "转正答辩", "晋升答辩", "离职手续"]},
    {"id": "dw", "title": "数据仓库分层与建模规范", "category": "研发文档", "lang": "zh",
     "terms": ["贴源层", "明细层", "汇总层", "应用层", "维度建模", "事实表", "缓慢变化维",
               "数据血缘", "任务调度", "质量校验"]},
    {"id": "vecdb", "title": "Vector Database Selection Whitepaper", "category": "技术白皮书", "lang": "en",
     "terms": ["graph index", "inverted file", "quantization", "recall", "latency",
               "throughput", "sharding", "replication", "distance metric", "filter pushdown"]},
    {"id": "recsys", "title": "Recommendation System Architecture", "category": "研发文档", "lang": "en",
     "terms": ["candidate generation", "ranking model", "feature store", "online serving",
               "cold start", "exploration", "re-ranking", "click-through rate", "embedding", "evaluation"]},
    {"id": "fin", "title": "财务报销与费用管理制度", "category": "制度规范", "lang": "zh",
     "terms": ["差旅报销", "招待费", "发票校验", "预算控制", "对公付款", "备用金",
               "费用分摊", "季度预算", "报销周期", "超标审批"]},
    {"id": "ops", "title": "IT 运维故障排查手册", "category": "FAQ", "lang": "zh",
     "terms": ["服务降级", "熔断", "限流", "链路追踪", "日志检索", "容量评估",
               "应急预案", "值班制度", "变更管理", "故障复盘"]},
    {"id": "legal", "title": "Data Privacy Compliance Handbook", "category": "制度规范", "lang": "en",
     "terms": ["data subject", "consent", "retention", "erasure", "anonymization",
               "data mapping", "breach notification", "processor agreement", "DPIA", "cross-border transfer"]},
]

# ── 事实（锚点 + 5 类问题）─────────────────────────────────────────────
# key 必须是 statement 的连续子串（也即库内某 chunk 的真实子串）。
FACTS = [
    # cs 智能客服
    {"doc": "cs", "lang": "zh", "topic": "身份核验", "key": "青鸾-7 身份核验引擎",
     "statement": "智能客服机器人的身份核验由青鸾-7 身份核验引擎统一完成，该引擎支持人脸、短信与工牌三种核验方式，平均核验耗时低于 180 毫秒。",
     "q_direct": "智能客服机器人用什么引擎做身份核验？",
     "q_para": "客服系统里负责校验访客身份的组件是哪一个？",
     "q_cross": "Which engine handles identity verification in the customer service bot?",
     "q_distract": "客服机器人既要身份核验又要对话路由，那么负责身份核验的引擎叫什么？",
     "q_neg": "客服机器人不靠人工审核，而是由哪个引擎自动完成身份核验？"},
    {"doc": "cs", "lang": "zh", "topic": "对话编排", "key": "百川对话编排器",
     "statement": "对话流程由百川对话编排器以可视化拖拽方式编排，支持意图识别、槽位填充与多轮澄清三种节点类型。",
     "q_direct": "智能客服的对话流程用哪个编排器来编排？",
     "q_para": "客服对话流是通过什么工具做可视化配置的？",
     "q_cross": "What tool is used to visually orchestrate the dialog flow in the customer service bot?",
     "q_distract": "客服机器人有身份核验和对话编排两个子系统，负责对话编排的是哪个？",
     "q_neg": "客服对话流不是写代码实现，而是用哪个编排器拖拽配置？"},

    # iot 工业物联网
    {"doc": "iot", "lang": "zh", "topic": "边缘网关", "key": "玄铁-9 边缘网关",
     "statement": "现场设备通过玄铁-9 边缘网关接入平台，该网关支持 Modbus、OPC-UA 与 MQTT 三种协议，并内置本地断点续传能力。",
     "q_direct": "现场设备通过哪个边缘网关接入工业物联网平台？",
     "q_para": "物联网平台让设备接入的那个边缘设备叫什么？",
     "q_cross": "Which edge gateway connects field devices to the IIoT platform?",
     "q_distract": "物联网平台既有边缘网关也有告警模块，负责设备接入的网关是哪一个？",
     "q_neg": "设备不是直连云平台，而是先接入哪个边缘网关？"},
    {"doc": "iot", "lang": "zh", "topic": "数据压缩", "key": "时序数据采用 LZ4 压缩",
     "statement": "为降低存储成本，时序数据采用 LZ4 压缩算法写入列式存储，压缩比可达 8 比 1，同时保留按时间范围快速扫描的能力。",
     "q_direct": "工业物联网平台的时序数据用什么算法压缩？",
     "q_para": "平台为了省存储空间，对时序数据做了哪种压缩处理？",
     "q_cross": "What compression algorithm is applied to time-series data in the IIoT platform?",
     "q_distract": "平台既有数据压缩也有边缘网关，针对时序数据采用的压缩算法是什么？",
     "q_neg": "时序数据不是原样落盘，而是采用了哪种压缩算法？"},
    {"doc": "iot", "lang": "zh", "topic": "告警管理", "key": "告警风暴抑制",
     "statement": "平台内置告警风暴抑制机制，同一设备 5 分钟内重复告警只推送一次，避免瞬时故障淹没值班人员。",
     "q_direct": "平台用什么机制避免重复告警淹没值班人员？",
     "q_para": "设备批量故障时，平台如何防止告警刷屏？",
     "q_cross": "What mechanism prevents alert flooding in the IIoT platform?",
     "q_distract": "平台有告警管理和数据订阅两个模块，用于防止重复告警的是哪个机制？",
     "q_neg": "平台不会对同一设备反复推送告警，靠的是什么机制？"},

    # sec 信息安全
    {"doc": "sec", "lang": "zh", "topic": "数据分级", "key": "四级数据分级",
     "statement": "公司数据按敏感程度实行四级数据分级：公开、内部、机密与绝密，其中机密及以上数据禁止明文落地到个人终端。",
     "q_direct": "公司数据按敏感程度实行几级分级？",
     "q_para": "企业的数据是按什么样的等级制度来划分敏感程度的？",
     "q_cross": "How many data classification levels does the company use?",
     "q_distract": "安全制度既有数据分级也有访问控制，数据敏感程度的划分叫什么？",
     "q_neg": "公司数据不是不分级，而是实行哪种分级制度？"},
    {"doc": "sec", "lang": "zh", "topic": "权限管理", "key": "双人复核",
     "statement": "生产环境的高危操作必须执行双人复核，即由操作人发起、授权人审批后方可执行，全程留存操作审计记录。",
     "q_direct": "生产环境的高危操作必须执行什么机制？",
     "q_para": "高危操作需要两个人共同把关，这个制度叫什么？",
     "q_cross": "What two-person control is required for high-risk production operations?",
     "q_distract": "安全制度有数据分级和权限管理，高危操作必须执行的机制是什么？",
     "q_neg": "高危操作不能单人直接执行，必须走什么机制？"},

    # hr 人力资源
    {"doc": "hr", "lang": "zh", "topic": "年假", "key": "年假按自然年度折算",
     "statement": "员工年假按自然年度折算，入职未满一年的按在职月份比例折算，每年 1 月 1 日统一刷新额度。",
     "q_direct": "员工年假按什么方式折算？",
     "q_para": "公司给员工的年假额度是怎么计算的？",
     "q_cross": "How is annual leave calculated for employees?",
     "q_distract": "HR 制度有年假和考勤两个部分，年假额度的折算方式是什么？",
     "q_neg": "年假不是固定给满额，而是按什么方式折算？"},
    {"doc": "hr", "lang": "zh", "topic": "差旅标准", "key": "住宿标准为每晚 400 元",
     "statement": "一线城市差旅住宿标准为每晚 400 元，超出部分需由员工自行承担，并在报销时附住宿水单。",
     "q_direct": "一线城市差旅住宿标准是每晚多少钱？",
     "q_para": "出差去一线城市，公司规定住宿每晚能报销多少？",
     "q_cross": "What is the nightly hotel allowance for business travel in first-tier cities?",
     "q_distract": "报销制度里有住宿标准和发票规范，一线城市住宿标准是多少？",
     "q_neg": "住宿超出公司标准的部分不是公司承担，标准是多少元？"},

    # dw 数据仓库
    {"doc": "dw", "lang": "zh", "topic": "分层模型", "key": "四层数仓模型",
     "statement": "数据仓库采用四层数仓模型，自下而上依次为 ODS 贴源层、DWD 明细层、DWS 汇总层与 ADS 应用层。",
     "q_direct": "数据仓库采用几层数仓模型？",
     "q_para": "公司数仓把数据分成了几个层次来组织？",
     "q_cross": "How many layers does the data warehouse model use?",
     "q_distract": "数仓规范里有分层和建模两套约定，数据分层用的是哪套模型？",
     "q_neg": "数仓不是单层平铺，而是采用了哪种分层模型？"},
    {"doc": "dw", "lang": "zh", "topic": "维度建模", "key": "维度表使用代理键",
     "statement": "维度表使用代理键作为主键，以隔离业务系统主键变更对历史数据回刷造成的影响。",
     "q_direct": "维度表用什么作为主键？",
     "q_para": "数仓的维度表主键采用哪种键来隔离业务主键变化？",
     "q_cross": "What kind of key does the dimension table use as its primary key?",
     "q_distract": "数仓有事实表和维度表，维度表主键用的是什么键？",
     "q_neg": "维度表不用业务主键，而是用什么键作为主键？"},

    # vecdb 向量数据库（英文）
    {"doc": "vecdb", "lang": "en", "topic": "index type", "key": "HNSW graph-based index",
     "statement": "For high recall at scale, the platform relies on the HNSW graph-based index, which trades a small amount of memory for logarithmic search complexity.",
     "q_direct": "Which index does the platform rely on for high recall at scale?",
     "q_para": "What graph structure gives the vector database fast approximate search?",
     "q_cross": "平台为了高召回率采用了哪种图索引？",
     "q_distract": "The vector store has both graph and inverted-file indexes; which one is chosen for high recall?",
     "q_neg": "The platform does not use brute force search, relying instead on which graph-based index?"},
    {"doc": "vecdb", "lang": "en", "topic": "compression", "key": "Product quantization compresses vectors",
     "statement": "Product quantization compresses vectors into short codes, cutting memory usage by up to 8x while preserving approximate distance ranking.",
     "q_direct": "What technique compresses vectors into short codes to cut memory?",
     "q_para": "How does the vector database shrink vector memory footprint?",
     "q_cross": "用什么技术把向量压缩成短码以节省内存？",
     "q_distract": "Vector stores offer HNSW and quantization; which one compresses vectors to reduce memory?",
     "q_neg": "Instead of storing full-precision vectors, which method compresses them into short codes?"},
    {"doc": "vecdb", "lang": "en", "topic": "index type", "key": "IVF inverted file index",
     "statement": "For large-scale batch queries, the IVF inverted file index partitions vectors into clusters, enabling fast coarse-to-fine candidate filtering.",
     "q_direct": "Which index partitions vectors into clusters for batch queries?",
     "q_para": "What cluster-based index speeds up large-scale vector search?",
     "q_cross": "哪种索引把向量划分成簇以加速批量检索？",
     "q_distract": "The platform has graph and inverted-file indexes; which one partitions vectors into clusters?",
     "q_neg": "This index does not build a graph; instead it partitions vectors into clusters. Which index is it?"},

    # recsys 推荐系统（英文）
    {"doc": "recsys", "lang": "en", "topic": "retrieval model", "key": "two-tower retrieval model",
     "statement": "The candidate generation stage uses a two-tower retrieval model that encodes users and items into a shared embedding space for fast dot-product scoring.",
     "q_direct": "What model does the candidate generation stage use?",
     "q_para": "Which architecture maps users and items into one embedding space?",
     "q_cross": "候选生成阶段采用哪种双塔模型？",
     "q_distract": "The recommender has retrieval and ranking stages; which model powers the retrieval stage?",
     "q_neg": "Candidate generation does not scan all items linearly; it uses which retrieval model?"},
    {"doc": "recsys", "lang": "en", "topic": "bias correction", "key": "positional bias correction",
     "statement": "Ranking applies positional bias correction to offset the tendency of users to click higher-ranked items regardless of relevance.",
     "q_direct": "What correction does ranking apply to offset click position bias?",
     "q_para": "How does the ranking stage fix the tendency to click top items?",
     "q_cross": "排序阶段用什么校正来抵消位置偏差？",
     "q_distract": "The recommender handles cold start and ranking; which correction fixes the position bias in ranking?",
     "q_neg": "Ranking must not assume top positions are truly relevant, so it applies which correction?"},

    # fin 财务报销
    {"doc": "fin", "lang": "zh", "topic": "发票规范", "key": "发票抬头必须为全称",
     "statement": "增值税专用发票抬头必须为全称且与税号一致，否则财务将作退票处理，不予报销。",
     "q_direct": "增值税专用发票的抬头有什么要求？",
     "q_para": "报销时专用发票的开票抬头要怎么写才合格？",
     "q_cross": "What is required for the title on a special VAT invoice?",
     "q_distract": "报销制度有发票规范和报销时效两条，发票抬头的要求是什么？",
     "q_neg": "发票抬头不能用简称，必须满足什么要求？"},
    {"doc": "fin", "lang": "zh", "topic": "报销时效", "key": "3 个工作日内到账",
     "statement": "预算内报销自完整材料提交之日起 3 个工作日内到账，预算外或超标准的报销需额外走部门负责人审批。",
     "q_direct": "预算内报销提交完整材料后多久到账？",
     "q_para": "材料齐全的预算内报销，钱几天能打过来？",
     "q_cross": "How quickly is an in-budget reimbursement paid after submission?",
     "q_distract": "报销制度有时效和发票规范两条，预算内报销的到账时限是多久？",
     "q_neg": "预算内报销不是无限期等待，而是在多少个工作日内到账？"},

    # ops IT 运维
    {"doc": "ops", "lang": "zh", "topic": "链路监控", "key": "黄金链路监控",
     "statement": "核心交易系统启用黄金链路监控，对入口网关、业务服务、缓存与数据库四层逐跳埋点，故障定位时间从小时级缩短到分钟级。",
     "q_direct": "核心交易系统启用什么监控来逐跳埋点？",
     "q_para": "交易系统靠哪套监控把故障定位压到分钟级？",
     "q_cross": "What monitoring does the core trading system enable for hop-by-hop tracing?",
     "q_distract": "运维手册有监控和发布两类，用于核心交易链路逐跳埋点的是哪个？",
     "q_neg": "故障定位不再靠人工逐层排查，而是靠哪套监控？"},
    {"doc": "ops", "lang": "zh", "topic": "发布策略", "key": "蓝绿发布",
     "statement": "应用发布默认采用蓝绿发布策略，新旧版本并行运行，验证通过后一次性切换流量，异常时可在 30 秒内回滚。",
     "q_direct": "应用发布默认采用什么策略？",
     "q_para": "系统上线新版本时默认用哪种发布方式来快速回滚？",
     "q_cross": "What deployment strategy is used by default for application releases?",
     "q_distract": "运维手册有监控和发布两套流程，默认的发布策略是什么？",
     "q_neg": "发布不直接覆盖旧版本，而是采用哪种策略？"},

    # legal 数据合规（英文）
    {"doc": "legal", "lang": "en", "topic": "data retention", "key": "data retention is capped at 24 months",
     "statement": "Under the retention policy, personal data retention is capped at 24 months, after which records are anonymized or securely deleted.",
     "q_direct": "For how long may personal data be retained under the policy?",
     "q_para": "What is the maximum retention period for personal records?",
     "q_cross": "个人信息按政策最多可保留多久？",
     "q_distract": "The handbook covers retention and erasure; what is the retention cap for personal data?",
     "q_neg": "Personal data cannot be kept indefinitely; retention is capped at how many months?"},
    {"doc": "legal", "lang": "en", "topic": "erasure", "key": "right-to-erasure requests within 30 days",
     "statement": "The organization must fulfill right-to-erasure requests within 30 days, barring legal obligations that require longer retention.",
     "q_direct": "Within how many days must erasure requests be fulfilled?",
     "q_para": "How quickly must the company act on a request to delete personal data?",
     "q_cross": "公司必须在多少天内响应数据删除请求？",
     "q_distract": "The handbook covers retention and erasure; what is the deadline for fulfilling erasure requests?",
     "q_neg": "Erasure requests are not optional; they must be fulfilled within how many days?"},
]

FACTS_BY_DOC: dict[str, list[dict]] = {}
for _f in FACTS:
    FACTS_BY_DOC.setdefault(_f["doc"], []).append(_f)

# ── 填充文案模板（生成逼真的企业文档正文，非事实锚点）─────────────────
_ZH_TEMPLATES = [
    "{term} 模块在系统启动阶段完成配置加载与依赖校验，避免运行时出现未初始化错误。",
    "运维团队建议为 {term} 配置独立的监控告警阈值，当响应时延超过 300 毫秒时触发降级。",
    "在 {term} 的灰度发布过程中采用金丝雀策略逐步放量，并实时观察错误率与资源占用。",
    "针对 {term} 的容量规划，需要结合历史峰值流量与未来三个月的业务增长预测综合评估。",
    "安全侧要求 {term} 的所有外部调用必须经过统一网关鉴权，并记录完整的审计日志。",
    "{term} 的异常场景已纳入应急预案，值班人员需在 15 分钟内完成首次响应与初步定位。",
    "新员工入职培训中会专门讲解 {term} 的操作规范与常见问题处置流程。",
    "{term} 与相邻模块之间通过异步消息队列解耦，避免上游抖动直接拖垮下游服务。",
    "季度复盘会上，{term} 的运行指标会被拆解为可用率、时延与错误率三个维度讨论。",
    "{term} 的参数调整需要先在测试环境验证，再通过变更工单审批后发布到生产环境。",
]

_EN_TEMPLATES = [
    "The {term} component is deployed behind a load balancer and supports automatic failover within the primary region.",
    "Operators should monitor the {term} service for elevated latency and trigger circuit breaking when the error budget is exhausted.",
    "During rollout, {term} is released through a canary strategy with staged traffic and continuous error-rate observation.",
    "Capacity planning for {term} combines historical peak traffic with a three-month business growth forecast.",
    "All external calls into {term} must pass through the unified gateway for authentication and audit logging.",
    "The runbook for {term} defines a fifteen-minute first-response target for on-call engineers.",
    "Quarterly reviews break down {term} metrics into availability, latency, and error rate.",
    "Parameter changes to {term} are validated in staging and approved through a change ticket before production.",
    "The {term} module is decoupled from its neighbors through an asynchronous message queue.",
    "A dedicated retention and archival policy applies to the logs produced by {term}.",
]

_ZH_HEADINGS = ["{term} 概览", "{term} 配置说明", "{term} 运维手册", "{term} 安全合规",
                "常见问题：{term}", "{term} 参数对照表", "{term} 故障排查", "附录：{term} 说明"]
_EN_HEADINGS = ["{term} Overview", "{term} Configuration", "{term} Operations",
                "{term} Security", "{term} FAQ", "{term} Reference", "{term} Troubleshooting",
                "Appendix: {term}"]

# 每个领域额外生成多少节「纯填充」内容（用于把 chunk 总量抬到 300-500）
EXTRA_SECTIONS_PER_DOMAIN = 16


def _templates(dom: dict) -> list[str]:
    return _ZH_TEMPLATES if dom["lang"] == "zh" else _EN_TEMPLATES


def _headings(dom: dict) -> list[str]:
    return _ZH_HEADINGS if dom["lang"] == "zh" else _EN_HEADINGS


def _filler_paragraph(dom: dict, rng: random.Random) -> str:
    """生成一段 2-3 句的领域相关填充文字（不含事实锚点）。"""
    terms = dom["terms"]
    tpl = _templates(dom)
    n = rng.randint(2, 3)
    chosen = rng.sample(tpl, n)
    parts = []
    for t in chosen:
        parts.append(t.format(term=rng.choice(terms)))
    sep = "。" if dom["lang"] == "zh" else ". "
    text = sep.join(parts)
    if dom["lang"] == "en" and not text.endswith("."):
        text += "."
    return text


def _fact_paragraph(dom: dict, fact: dict, rng: random.Random) -> str:
    """事实段落：事实句子 + 1 句填充，让锚点自然嵌入正文。"""
    extra = _templates(dom)[0].format(term=rng.choice(dom["terms"]))
    if dom["lang"] == "zh":
        return fact["statement"] + extra + "。"
    return fact["statement"] + " " + extra + "."


def build_kb_documents() -> list[tuple[str, str]]:
    """生成全部合成文档，返回 [(filename, markdown_content)]。

    使用固定随机种子保证可复现。"""
    rng = random.Random(20260903)
    docs: list[tuple[str, str]] = []
    for dom in DOMAINS:
        blocks: list[str] = []
        blocks.append(f"# {dom['title']}")

        # 术语表
        blocks.append("## 术语表")
        blocks.append("；".join(f"{t}：见正文相应章节" for t in dom["terms"]))

        # 每个事实一个章节
        for fact in FACTS_BY_DOC[dom["id"]]:
            blocks.append(f"## {fact['topic']}")
            blocks.append(_fact_paragraph(dom, fact, rng))
            blocks.append(_filler_paragraph(dom, rng))

        # 纯填充章节
        headings = _headings(dom)
        for i in range(EXTRA_SECTIONS_PER_DOMAIN):
            heading = headings[i % len(headings)].format(term=dom["terms"][i % len(dom["terms"])])
            blocks.append(f"## {heading}（{i + 1}）")
            blocks.append(_filler_paragraph(dom, rng))
            blocks.append(_filler_paragraph(dom, rng))

        docs.append((f"day7_{dom['id']}.md", "\n\n".join(blocks)))
    return docs


# ── 真实公开文档片段（与合成语料混合入库，贴近真实分布）──────────────────
# 内容为 PostgreSQL / LangChain / FastAPI / Redis / 向量检索 等官方文档的忠实摘要，
# 用于让检索评测在「真实风格 + 合成锚点」混合语料上进行。
REAL_DOCS: list[tuple[str, str]] = [
    ("real_pgvector.md", """# PostgreSQL pgvector 扩展

pgvector 是 PostgreSQL 的开源向量相似度检索扩展，提供 vector 数据类型，用于存储嵌入向量。

## 向量类型与索引

pgvector 支持 exact 与 approximate 最近邻检索。精确检索用顺序扫描逐一计算距离；近似检索用 IVFFlat 或 HNSW 索引加速。IVFFlat 先把向量划分到若干簇（lists），查询时只扫描最近的几个簇；HNSW 构建多层图结构，以少量内存换取对数级的搜索复杂度。

## 距离函数

pgvector 提供三种常用距离算子：L2 距离（欧氏距离）、内积（inner product）与余弦距离（cosine distance）。其中余弦距离需要向量先做 L2 归一化。选择距离函数时应与 embedding 模型的训练目标保持一致。

## 查询示例

建表时用 vector(1024) 声明维度，插入向量后可用 ORDER BY embedding <=> query 做近似检索，并配合 WHERE 过滤元数据。HNSW 索引通过 CREATE INDEX ... USING hnsw (embedding vector_cosine_ops) 建立。
"""),
    ("real_langchain.md", """# LangChain 框架概述

LangChain 是用于构建大语言模型（LLM）应用的开源框架，核心抽象包括 Chain、Agent 与 Tool。

## Chain 与 LCEL

Chain 把多个步骤串成流水线；LCEL（LangChain Expression Language）用管道运算符声明式组合 prompt、模型与解析器，便于异步、流式与批处理。

## Agent 与 Tool

Agent 根据 LLM 的推理决定调用哪个 Tool，常见模式是 ReAct（Reason + Act）。Tool 封装外部能力（搜索、计算、数据库查询），Agent 循环直到得到最终答案。

## Retriever 与 RAG

Retriever 是面向检索的统一接口，把用户查询转换为文档列表。RAG 模式先用 Retriever 召回相关文档，再把文档作为上下文交给 LLM 生成有依据的回答。LangChain 提供向量存储、BM25 等多种检索器实现。
"""),
    ("real_fastapi.md", """# FastAPI 框架概述

FastAPI 是基于 ASGI 的现代 Python Web 框架，用于构建 API 服务。

## 类型校验与文档

FastAPI 用 Pydantic 声明请求/响应模型，运行时自动做类型校验与序列化，并自动生成 OpenAPI 文档与交互式 Swagger UI。

## 异步支持

FastAPI 原生支持 async def 路由，也兼容普通 def 路由；异步路由能更高效地并发处理 I/O 密集请求，避免阻塞事件循环。

## 依赖注入

FastAPI 的 Depends 提供依赖注入机制，可复用数据库会话、鉴权校验等横切逻辑；依赖可嵌套、可缓存，便于测试时替换。
"""),
    ("real_redis.md", """# Redis 内存数据结构存储

Redis 是开源的内存数据结构存储，常用作缓存、消息代理与排行榜。

## 数据类型

Redis 支持字符串（String）、哈希（Hash）、列表（List）、集合（Set）、有序集合（Sorted Set）等类型。有序集合按 score 排序，适合实现排行榜与延迟队列。

## 过期与持久化

Redis 可为键设置 TTL（过期时间），到期自动删除。持久化有 RDB 快照与 AOF 追加日志两种方式，可单独或混合使用以平衡恢复速度与数据安全。

## 发布订阅

Redis 的 Pub/Sub 支持按频道发布与订阅消息，用于解耦服务间的实时通知；生产者与消费者彼此不直接感知。
"""),
    ("real_vector_search.md", """# 稠密检索与向量检索

稠密检索用神经网络把文本编码为高维向量，通过向量相似度衡量语义相关性，与基于关键词的稀疏检索互补。

## Embedding

Embedding 模型把 query 与文档映射到同一向量空间，语义相近的文本向量距离更近。常用模型包括 BGE、Sentence-BERT 等，输出向量通常做 L2 归一化后用于余弦相似度。

## 近似最近邻（ANN）

高维向量全量精确比对代价高，ANN 索引（HNSW、IVF、PQ 等）以少量召回损失换取大幅加速。HNSW 是图索引，查询复杂度近对数；PQ 用乘积量化压缩向量以降低内存。

## 混合检索

混合检索同时跑稀疏检索（如 BM25）与稠密检索，再通过 RRF（倒数排名融合）合并两路排序，兼顾专有名词精确匹配与语义泛化。
"""),
]


def build_real_documents() -> list[tuple[str, str]]:
    """返回真实公开文档片段（与合成语料混合入库）。"""
    return list(REAL_DOCS)


# ── 评测集 ──────────────────────────────────────────────────────────────
_CATEGORIES = [
    ("基线直配", "q_direct"),
    ("同义改写", "q_para"),
    ("跨语言", "q_cross"),
    ("多主题干扰", "q_distract"),
    ("反向否定", "q_neg"),
]


def build_eval_items() -> list[dict]:
    """由事实派生评测集：每事实 5 类各 1 条。"""
    items: list[dict] = []
    for fact in FACTS:
        for category, field in _CATEGORIES:
            items.append({
                "category": category,
                "query": fact[field],
                "keyword": fact["key"],
                "doc": fact["doc"],
            })
    return items


EVAL_ITEMS = build_eval_items()
