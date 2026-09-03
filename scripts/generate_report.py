# -*- coding: utf-8 -*-
"""生成《专业综合工程实践设计报告》Word 文档。"""
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

IMGDIR = r"D:\agentic-rag-system\report\images"
OUT = r"D:\agentic-rag-system\report\专业综合工程实践设计报告.docx"

# ── 样式常量 ────────────────────────────────
SONG = "宋体"
HEI = "黑体"
KAI = "楷体"
BODY_SIZE = Pt(12)          # 小四
H1_SIZE = Pt(16)            # 三号
H2_SIZE = Pt(14)            # 四号
H3_SIZE = Pt(12)            # 小四加粗
DARK = RGBColor(0, 0, 0)

doc = Document()


def set_run(run, cn_font=SONG, size=BODY_SIZE, bold=False, color=DARK, italic=False):
    run.font.name = "Times New Roman"
    run.font.size = size
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run._element.rPr.rFonts.set(qn("w:eastAsia"), cn_font)


def add_para(text="", cn_font=SONG, size=BODY_SIZE, bold=False, align=None,
             indent=True, space_before=0, space_after=6, line_spacing=1.5):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    pf.line_spacing = line_spacing
    if indent:
        pf.first_line_indent = Pt(24)  # 首行缩进 2 字符
    if text:
        r = p.add_run(text)
        set_run(r, cn_font=cn_font, size=size, bold=bold)
    return p


def add_heading(text, level=1):
    """标题：黑体，居中/左对齐，带编号。"""
    p = doc.add_paragraph()
    if level == 1:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        size, bold, space_b, space_a = H1_SIZE, True, 18, 12
    elif level == 2:
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        size, bold, space_b, space_a = H2_SIZE, True, 12, 8
    else:
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        size, bold, space_b, space_a = H3_SIZE, True, 8, 6
    pf = p.paragraph_format
    pf.space_before = Pt(space_b)
    pf.space_after = Pt(space_a)
    pf.line_spacing = 1.3
    r = p.add_run(text)
    set_run(r, cn_font=HEI, size=size, bold=bold)
    # 标记为大纲级别（供目录识别）
    pPr = p._element.get_or_add_pPr()
    outlineLvl = OxmlElement("w:outlineLvl")
    outlineLvl.set(qn("w:val"), str(level - 1))
    pPr.append(outlineLvl)
    return p


def add_bullet(text, cn_font=SONG, size=BODY_SIZE):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.4
    r = p.add_run(text)
    set_run(r, cn_font=cn_font, size=size)
    return p


def add_figure(img_name, caption, width_cm=15.0):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run()
    run.add_picture(f"{IMGDIR}\\{img_name}", width=Cm(width_cm))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(10)
    r = cap.add_run(caption)
    set_run(r, cn_font=HEI, size=Pt(10.5), bold=False)
    return p


def add_table(headers, rows, col_widths=None, font_size=Pt(10.5)):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(h)
        set_run(r, cn_font=HEI, size=font_size, bold=True)
    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT if i == 0 or len(str(val)) > 20 else WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(str(val))
            set_run(r, cn_font=SONG, size=font_size)
    if col_widths:
        for i, w in enumerate(col_widths):
            for row in t.rows:
                row.cells[i].width = Cm(w)
    # 表后留白
    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(4)
    return t


def add_code_block(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.line_spacing = 1.0
    p.paragraph_format.left_indent = Pt(12)
    r = p.add_run(text)
    set_run(r, cn_font="Consolas", size=Pt(9))
    r.font.name = "Consolas"
    return p


# ══════════════════════════════════════════════
# 封面
# ══════════════════════════════════════════════
for _ in range(3):
    add_para("", indent=False)

p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("专业综合工程实践设计报告"); set_run(r, HEI, Pt(26), True)
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("——基于 Agentic RAG 的企业智能搜索与自动调研系统"); set_run(r, HEI, Pt(16), False)

for _ in range(2):
    add_para("", indent=False)

def cover_line(label, value="____________________"):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.line_spacing = 2.0
    r = p.add_run(label); set_run(r, SONG, Pt(14))
    r2 = p.add_run(value); set_run(r2, SONG, Pt(14))

cover_line("学    院：____________________")
cover_line("专    业：____________________")
cover_line("班    级：____________________")
cover_line("学    号：____________________")
cover_line("姓    名：____________________")
cover_line("指导教师：____________________")

add_para("", indent=False)
add_para("", indent=False)
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("二〇二六年九月"); set_run(r, SONG, Pt(14))

doc.add_page_break()

# ══════════════════════════════════════════════
# 摘要
# ══════════════════════════════════════════════
add_heading("摘  要", 1)
add_para(
    "随着企业文档规模持续增长，传统的关键词检索难以满足员工对语义理解和深度调研的需求。"
    "大语言模型（LLM）虽具备强大的生成能力，但存在知识时效性差、容易产生幻觉等问题。"
    "检索增强生成（Retrieval-Augmented Generation，RAG）通过将外部知识库检索结果注入生成过程，"
    "有效缓解了上述问题。然而，单一轮次的 RAG 在面对复杂、多跳问题时检索能力不足。"
)
add_para(
    "针对上述问题，本文设计并实现了一个基于 Agentic RAG 的企业智能搜索与自动调研系统。"
    "系统采用「四模块 + 四智能体」的架构：在业务层面划分为文档管理、搜索问答、调研报告与运营看板四大模块；"
    "在检索编排层面，通过 LangGraph 构建 Planner（问题分解）、Retrieval（混合检索）、Critic（充分性审查）、"
    "Synthesizer（综合生成）四智能体的多步检索状态机。检索环节采用 BM25 稀疏检索与 pgvector 向量检索相结合、"
    "经倒数排名融合（RRF）与 BGE-Reranker 精排的混合检索策略，保证结果兼顾关键词精确匹配与语义相关性。"
    "系统支持多轮对话与指代消解、SSE 流式回答、引用溯源、用户反馈闭环，并可基于给定主题自动生成带引用的结构化调研报告并导出 PDF。"
)
add_para(
    "系统基于 FastAPI、PostgreSQL（pgvector）、Redis 与 DeepSeek 大模型实现。"
    "在自建的 110 条评测集上进行了四组消融实验，结果表明完整混合检索管线（BM25 + 向量 + RRF + Reranker）"
    "在 top-1 命中率（76.36%）、MRR（0.8026）与 nDCG@5（0.8150）三项指标上均达最优，验证了混合检索与精排策略的有效性；"
    "RAGAS 生成质量评测表明回答具备良好的忠实度与相关性。"
    "多轮对话测试表明系统能够正确完成指代消解，端到端功能测试全部通过。"
)
p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(12)
r = p.add_run("关键词："); set_run(r, HEI, BODY_SIZE, True)
r = p.add_run("检索增强生成；Agentic RAG；混合检索；多智能体；LangGraph；pgvector"); set_run(r, SONG, BODY_SIZE)

doc.add_page_break()

# ══════════════════════════════════════════════
# 目录
# ══════════════════════════════════════════════
add_heading("目  录", 1)
p = doc.add_paragraph()
r = p.add_run("（目录为自动生成，请在 Word 中全选后按 F9 更新域，或右键“更新域”）")
set_run(r, KAI, Pt(10.5))
# TOC 域
toc_p = doc.add_paragraph()
run = toc_p.add_run()
fldChar = OxmlElement("w:fldChar"); fldChar.set(qn("w:fldCharType"), "begin")
instrText = OxmlElement("w:instrText"); instrText.set(qn("xml:space"), "preserve")
instrText.text = 'TOC \\o "1-3" \\h \\z \\u'
fldChar2 = OxmlElement("w:fldChar"); fldChar2.set(qn("w:fldCharType"), "separate")
t = OxmlElement("w:t"); t.text = "（目录待更新）"
fldChar2.append(t)
fldChar3 = OxmlElement("w:fldChar"); fldChar3.set(qn("w:fldCharType"), "end")
run._r.append(fldChar); run._r.append(instrText); run._r.append(fldChar2); run._r.append(fldChar3)

doc.add_page_break()

# ══════════════════════════════════════════════
# 第 1 章 绪论
# ══════════════════════════════════════════════
add_heading("第 1 章  绪论", 1)

add_heading("1.1 研究背景与意义", 2)
add_para(
    "在信息化与数字化不断深入的背景下，企业积累的文档数量呈爆炸式增长，涵盖产品手册、技术规范、"
    "会议纪要、研究报告等非结构化文本。据相关统计，企业数据中约 80% 为非结构化数据，而这些数据中"
    "蕴藏着大量对决策和运营有价值的知识。然而，传统的企业知识管理主要依赖关键词检索与人工翻阅，"
    "存在语义理解能力弱、检索结果碎片化、难以支持深度调研等问题，导致知识利用效率低下。"
)
add_para(
    "以大语言模型（Large Language Model，LLM）为代表的生成式人工智能在近年来取得了突破性进展，"
    "展现出强大的语言理解与生成能力。但 LLM 存在两个固有问题：一是其知识来源于训练数据，存在时效性差、"
    "覆盖不全的缺陷；二是生成过程中可能产生“幻觉”（Hallucination），即输出与事实不符的内容。"
    "检索增强生成（RAG）技术将外部知识库的检索结果作为上下文注入生成过程，使模型能够基于可靠的"
    "企业私有知识回答问题，从而在保留 LLM 生成能力的同时大幅降低幻觉风险。"
)
add_para(
    "然而，基础的 RAG 通常只执行一次检索，在面对需要多步推理、多角度信息综合的复杂问题时，"
    "往往因检索不充分而导致回答质量下降。Agentic RAG 将 RAG 与智能体（Agent）思想相结合，"
    "通过规划（Planning）、检索（Retrieval）、反思（Critique）等环节的多步迭代，模拟人类研究者的"
    "工作流程，显著提升了复杂问题的回答质量。"
)
add_para(
    "本课题以“企业智能搜索与自动调研”为应用场景，设计并实现一套基于 Agentic RAG 的系统，"
    "旨在解决企业知识检索的语义理解不足、复杂问题回答不充分、调研工作耗时费力等实际问题，"
    "对推动 RAG 技术在企业知识管理领域的落地应用具有一定的工程实践价值与参考意义。"
)

add_heading("1.2 国内外研究现状", 2)
add_para(
    "在检索增强生成方面，Lewis 等人于 2020 年提出 RAG 范式，将检索模块与序列到序列生成模型相结合，"
    "开创了知识增强生成的研究方向。此后，RAG 的研究沿着“检索器增强—索引优化—生成器优化”的路线快速发展。"
    "在检索器层面，从最初的基于稠密向量的 DPR，发展到 BM25 与向量检索相结合的混合检索（Hybrid Search），"
    "再到引入交叉编码器（Cross-Encoder）的精排（Rerank）机制，检索质量不断提升。"
)
add_para(
    "在向量检索基础设施方面，以 FAISS、Milvus、Weaviate 为代表的专用向量数据库，以及为 PostgreSQL "
    "扩展向量能力的 pgvector 插件，为大规模向量相似度检索提供了成熟方案。其中 pgvector 以其与关系型数据库"
    "的天然集成、支持 HNSW 近似最近邻索引等特性，成为中小规模企业知识库的热门选择。"
)
add_para(
    "在智能体编排方面，随着 LangChain、LangGraph 等框架的成熟，“多智能体协作”逐渐成为 RAG 系统演进的重要方向。"
    "代表性的工作如 Self-RAG、Corrective RAG（CRAG）以及各类 Planner-Executor 架构，均强调通过规划、"
    "反思与迭代来提升回答质量。Agentic RAG 正是在这一趋势下，将传统“检索一次即生成”的流程升级为“"
    "规划—检索—审查—综合”的多步闭环。"
)
add_para(
    "总体来看，Agentic RAG 在学术界与工业界均处于快速上升期，但面向中文企业知识库的完整工程实现、"
    "以及配套的可视化与评测体系，仍缺乏系统性的落地实践。本课题正是基于这一背景展开。"
)

add_heading("1.3 主要研究内容与工作", 2)
add_para("本文围绕企业智能搜索与自动调研系统的设计与实现，主要完成以下工作：")
add_bullet("设计并实现文档入库全链路：支持 PDF、DOCX、Markdown、TXT 等格式的解析、多策略智能分片、BGE 向量化与 pgvector 入库；")
add_bullet("实现混合检索：融合 BM25 稀疏检索与向量稠密检索，经 RRF 融合与 BGE-Reranker 精排，兼顾精确匹配与语义相关性；")
add_bullet("实现 Agentic 多步问答：基于 LangGraph 构建 Planner—Retrieval—Critic—Synthesizer 四智能体编排，支持 Critic 自循环补查与防死循环保护；")
add_bullet("实现多轮对话与指代消解：请求携带历史对话，前端 localStorage 持久化会话，支持“它/这个”等指代消解；")
add_bullet("实现自动调研报告：后台多轮检索生成结构化 Markdown 报告，支持 Chrome headless 导出 PDF；")
add_bullet("实现反馈闭环与运营看板：问答落库 query_log，支持反馈收集、热点问题与低置信度队列展示；")
add_bullet("建立检索评测体系：构建 110 条评测集与 385 分片知识库，开展 BM25-only / 向量-only / BM25+向量 / 完整+Reranker 四组消融实验，并接入 RAGAS 评测生成质量。")

add_heading("1.4 论文组织结构", 2)
add_para(
    "本文共分为八章。第 1 章绪论介绍研究背景、现状与主要工作；第 2 章介绍相关技术；"
    "第 3 章进行需求分析；第 4 章阐述系统设计；第 5 章给出数据库设计；第 6 章描述系统实现；"
    "第 7 章介绍系统测试与评测；第 8 章进行总结与展望。文末附参考文献、致谢与项目部署附录。"
)

doc.add_page_break()

# ══════════════════════════════════════════════
# 第 2 章 相关技术介绍
# ══════════════════════════════════════════════
add_heading("第 2 章  相关技术介绍", 1)

add_heading("2.1 检索增强生成（RAG）技术", 2)
add_para(
    "检索增强生成（RAG）是一种将信息检索与文本生成相结合的技术范式。其核心思想是：在生成回答之前，"
    "先从外部知识库中检索与用户问题相关的文档片段，将这些片段作为上下文注入到 LLM 的提示中，"
    "从而引导模型基于可靠的外部知识生成回答。RAG 的典型流程包括索引（Indexing）、检索（Retrieval）"
    "与生成（Generation）三个阶段。"
)
add_para(
    "与传统的 LLM 微调（Fine-tuning）相比，RAG 具有显著优势：其一，RAG 无需重新训练模型，"
    "即可即时接入最新知识，解决知识时效性问题；其二，RAG 的回答可追溯到具体的来源文档，"
    "具备可审计性；其三，RAG 的成本更低、部署更灵活。这些特性使其特别适合企业私有知识库的场景。"
)

add_heading("2.2 向量数据库与 pgvector", 2)
add_para(
    "向量检索的核心是将文本编码为高维稠密向量，并通过向量之间的相似度（如余弦相似度、内积）来衡量语义相关性。"
    "向量数据库负责存储这些向量并提供高效的相似度检索能力。pgvector 是 PostgreSQL 的开源扩展，"
    "它新增了 vector 数据类型，并支持 IVF（倒排文件）与 HNSW（分层可导航小世界图）两种近似最近邻（ANN）索引。"
)
add_para(
    "HNSW 索引通过构建多层图结构，在召回率与检索速度之间取得了良好的平衡，"
    "本系统采用 HNSW 配合余弦距离算子（vector_cosine_ops）实现向量检索。"
    "选择 pgvector 而非独立向量数据库的原因是：其与关系型数据库天然集成，"
    "便于将文档元数据与向量统一管理，并支持事务与 SQL 查询。"
)

add_heading("2.3 混合检索与重排序", 2)
add_para(
    "单一检索方式各有局限：BM25 等稀疏检索擅长精确关键词匹配，对专有名词、缩写等效果较好，"
    "但缺乏语义理解；向量稠密检索擅长语义相似性匹配，但对生僻术语和精确匹配不够敏感。"
    "混合检索（Hybrid Search）将两者结合，取长补短。"
)
add_para(
    "倒数排名融合（Reciprocal Rank Fusion，RRF）是一种无需分数归一化的排序融合算法，"
    "其计算公式为：RRF(d) = Σ 1/(k + rank_i(d))，其中 k 为常数（通常取 60），rank_i 为文档在第 i 路"
    "检索结果中的排名。RRF 的优点是只依赖排名而非原始分数，避免了不同检索器分数分布不一致带来的融合困难。"
)
add_para(
    "重排序（Rerank）是在粗排候选集上使用更精细的模型（如交叉编码器 Cross-Encoder）对查询-文档对"
    "进行逐对打分，从而进一步优化排序质量。本系统采用 BGE-Reranker 模型进行精排。"
)

add_heading("2.4 智能体与 Agentic RAG", 2)
add_para(
    "智能体（Agent）是能够感知环境、自主决策并执行动作的软件实体。在大模型时代，"
    "LLM 作为智能体的“大脑”，负责理解任务、制定计划并调用工具。Agentic RAG 将智能体思想引入 RAG，"
    "通过规划、检索、反思、综合等多个环节的协同与迭代，处理传统 RAG 难以胜任的复杂、多跳问题。"
)
add_para(
    "LangGraph 是一个基于图结构编排智能体工作流的框架，它将每个处理环节建模为图节点（Node），"
    "将节点间的转移建模为边（Edge），并支持条件边（Conditional Edge）实现循环与分支。"
    "本系统使用 LangGraph 的 StateGraph 构建四智能体的多步检索状态机，通过条件边实现 Critic 审查的"
    "自循环补查，并通过迭代计数器实现防死循环保护。"
)

add_heading("2.5 大语言模型与 BGE 模型", 2)
add_para(
    "系统的主生成模型采用 DeepSeek Chat，通过 OpenAI 兼容 API 接入，具备良好的中文理解与生成能力，"
    "并可根据需要替换为任意 OpenAI 兼容模型。系统的向量化与精排则采用本地部署的 BGE 模型："
    "BGE-large-zh-v1.5 用于文本向量化（1024 维，中英双语），BGE-Reranker-Base 用于精排，"
    "两者均本地推理，不产生额外 API 调用费用。"
)

add_heading("2.6 文档解析与分片", 2)
add_para(
    "文档解析负责将不同格式的原始文档转换为结构化文本。系统支持 PDF（pdfplumber）、DOCX（python-docx）、"
    "Markdown、TXT、HTML 等格式的解析。分片（Chunking）是将长文本切分为适合检索的片段的过程，"
    "分片质量直接影响检索效果。本系统采用多策略分片：优先按标题/章节边界分割以保留语义完整性，"
    "其次按自然段落分割，最后以固定长度截断加重叠兜底；同时对表格与代码块保持完整不拆分。"
)

doc.add_page_break()

# ══════════════════════════════════════════════
# 第 3 章 需求分析
# ══════════════════════════════════════════════
add_heading("第 3 章  需求分析", 1)

add_heading("3.1 系统概述与目标", 2)
add_para(
    "本系统面向企业知识管理与智能检索场景，目标是构建一套“上传即可问、问答可溯源、调研自动化”的"
    "企业智能搜索与自动调研平台。系统需在保证回答质量与可审计性的前提下，覆盖从文档入库、智能问答到"
    "自动调研报告的完整闭环，并通过运营看板为知识运营提供数据支撑。"
)

add_heading("3.2 用户角色分析", 2)
add_para("系统涉及两类用户角色，其职责与关注点如下：")
add_table(
    ["角色", "主要职责", "核心关注点"],
    [
        ["普通员工", "上传文档、智能问答、生成调研报告", "回答准确、有引用、响应快"],
        ["知识管理员", "管理知识库、监控运营指标、优化低质量回答", "知识覆盖率、低置信度队列、检索指标"],
    ],
    col_widths=[3.0, 7.0, 6.0],
)

add_heading("3.3 功能需求", 2)
add_para("系统功能需求按四大模块划分如下：")
add_para("（1）文档管理模块：支持单文件上传与批量上传，支持 PDF、DOCX、MD、TXT、HTML 等格式；"
         "文档上传后自动解析、分片、向量化并入库；支持文档列表分页查询、详情查看与删除（级联删除分片）。", indent=True)
add_para("（2）搜索问答模块：支持单轮检索与 Agentic 多步检索两种模式；支持 SSE 流式回答；"
         "支持多轮对话与指代消解；回答需附带引用来源、置信度与耗时；支持用户反馈（有帮助/没帮助）。", indent=True)
add_para("（3）调研报告模块：给定主题与深度后后台多轮检索并生成结构化 Markdown 报告（背景/现状/技术方案/案例/趋势）；"
         "支持报告列表查询、查看与 Markdown/PDF 下载。", indent=True)
add_para("（4）运营看板模块：展示文档数、分片数、查询总量、平均置信度等统计；"
         "展示热点问题（近 7 天）与低置信度回答队列。", indent=True)

add_heading("3.4 算法与技术需求", 2)
add_para("除功能需求外，系统对算法层面提出了明确的技术要求：")
add_bullet("混合检索：需同时支持 BM25 稀疏检索与向量稠密检索，并通过 RRF 融合与 Reranker 精排提升排序质量；")
add_bullet("多步 Agentic 检索：需将复杂问题分解为子查询，经 Critic 审查判断信息充分性，不充分时自动补查，并设置迭代上限防死循环；")
add_bullet("多轮对话与指代消解：需携带历史对话上下文，正确解析“它、这个、第二个方案”等指代；")
add_bullet("引用溯源：回答中的每个关键论点需标注引用编号，并回填来源文档与片段；")
add_bullet("评测体系：需构建评测集，并支持多组消融对比评测（BM25-only / 向量-only / 混合 / 完整+Reranker），输出 top-k 命中率、MRR、nDCG@5 等指标。")

add_heading("3.5 非功能需求", 2)
add_table(
    ["类别", "需求说明"],
    [
        ["性能", "常规问答端到端延迟控制在秒级；向量检索借助 HNSW 索引保证亚秒级；SSE 首 token 延迟尽量低"],
        ["可用性", "前端界面简洁直观，支持流式反馈与错误提示；模型离线可运行，避免网络波动影响"],
        ["可扩展性", "LLM 通过 OpenAI 兼容接口抽象，可替换；配置项集中管理，支持多环境部署"],
        ["可维护性", "模块化分层架构，ORM 建模，代码结构清晰，关键逻辑有日志"],
        ["安全与隐私", "企业文档本地存储与向量化，模型本地推理，敏感数据不出内网"],
    ],
    col_widths=[3.2, 12.8],
)

add_heading("3.6 业务流程图", 2)
add_para(
    "系统的核心业务流程包括文档入库、智能问答与自动调研三条主线。"
    "文档入库链路将原始文档经过解析、分片、向量化后写入 pgvector；"
    "智能问答链路通过四智能体多步检索生成带引用回答，Critic 审查不充分时自动补查；"
    "自动调研链路在后台多轮检索后生成结构化报告。业务流程如图 3-1 所示。"
)
add_figure("flow.png", "图 3-1  系统核心业务流程", 15.0)

add_heading("3.7 用例图", 2)
add_para(
    "系统用例图如图 3-2 所示。普通员工与知识管理员均可上传文档、进行智能问答、生成调研报告并查看运营看板，"
    "其中智能问答包含反馈提交与调研报告生成等环节。"
)
add_figure("usecase.png", "图 3-2  系统用例图", 14.5)

doc.add_page_break()

# ══════════════════════════════════════════════
# 第 4 章 系统设计
# ══════════════════════════════════════════════
add_heading("第 4 章  系统设计", 1)

add_heading("4.1 系统总体架构设计", 2)
add_para(
    "系统采用分层架构，自顶向下分为前端展示层、API 网关层、Agentic RAG 核心层与数据存储层，"
    "并辅以独立的 LLM 服务层。各层职责单一、通过明确接口交互，便于独立开发与演进。总体架构如图 4-1 所示。"
)
add_figure("arch.png", "图 4-1  系统总体架构图", 15.5)

add_para(
    "前端展示层为原生 HTML/CSS/JS 实现的单页应用（SPA），包含智能搜索、知识库、调研报告、运营看板四个视图；"
    "API 网关层基于 FastAPI，提供 /api/documents、/api/search、/api/reports、/api/dashboard 四组 RESTful 接口；"
    "核心层为 LangGraph 编排的 Agentic RAG 状态机与 HybridRetriever 混合检索器，BGE 模型本地推理；"
    "存储层为 PostgreSQL（pgvector）与 Redis。LLM 通过 OpenAI 兼容接口接入 DeepSeek。"
)

add_heading("4.2 功能模块划分", 2)
add_para("系统在业务层面划分为四大功能模块，各模块职责与关键接口如下表所示。")
add_table(
    ["模块", "路由前缀", "核心职责"],
    [
        ["文档管理", "/api/documents", "上传/批量导入/列表/详情/删除，解析分片向量化入库"],
        ["搜索问答", "/api/search", "单轮检索、Agentic 问答、SSE 流式、反馈"],
        ["调研报告", "/api/reports", "后台生成报告、列表、Markdown/PDF 下载"],
        ["运营看板", "/api/dashboard", "统计、热点问题、低置信度队列、检索指标"],
    ],
    col_widths=[3.2, 4.6, 8.2],
)

add_heading("4.3 Agentic RAG 工作流设计", 2)
add_para(
    "Agentic RAG 工作流是系统的核心，由四个智能体组成状态机，通过 LangGraph 编排，"
    "其工作流程为：用户问题进入 Planner，由 Planner 结合历史对话将复杂问题分解为若干可独立检索的子查询；"
    "Retrieval 依次对每个子查询执行混合检索并汇总结果；Critic 审查已检索信息是否足以回答问题，"
    "若信息不足且未达迭代上限，则给出建议补充查询并回到 Retrieval 继续检索；"
    "信息充分后由 Synthesizer 综合生成带引用的最终答案。"
)
add_para(
    "为防止 Critic 无限自循环，系统设置最大迭代次数 MAX_ITERATIONS=3：每次经过 Critic 迭代计数加一，"
    "达到上限时强制判定为充分并进入 Synthesizer。四个智能体的职责如下表所示。"
)
add_table(
    ["智能体", "职责", "关键能力"],
    [
        ["Planner", "将复杂问题拆分为 2–5 个子查询", "结合多轮历史做指代消解"],
        ["Retrieval", "对子查询执行混合检索", "BM25 + 向量 + RRF + Reranker"],
        ["Critic", "审查信息充分性", "缺失方面分析、建议补充查询、迭代上限保护"],
        ["Synthesizer", "综合生成带引用答案/报告", "问答/报告/流式三种模式"],
    ],
    col_widths=[2.8, 6.2, 7.0],
)

add_heading("4.4 接口设计", 2)
add_para("系统采用 RESTful 风格接口，主要接口如下表所示。")
add_table(
    ["方法", "路径", "说明"],
    [
        ["GET", "/api/health", "健康检查"],
        ["POST", "/api/documents/upload", "上传单个文档并入库"],
        ["POST", "/api/documents/upload-batch", "批量上传"],
        ["GET", "/api/documents", "分页文档列表"],
        ["GET", "/api/documents/{id}", "文档详情"],
        ["DELETE", "/api/documents/{id}", "删除文档及分片"],
        ["GET", "/api/search", "同步搜索（q/top_k/use_agentic）"],
        ["POST", "/api/search/chat", "问答（含 history 多轮历史）"],
        ["POST", "/api/search/chat/stream", "SSE 流式问答"],
        ["POST", "/api/search/feedback", "提交反馈"],
        ["POST", "/api/reports/generate", "创建后台报告"],
        ["GET", "/api/reports", "分页报告列表"],
        ["GET", "/api/reports/{id}/download", "下载报告（fmt=markdown/pdf）"],
        ["GET", "/api/dashboard/stats", "知识库统计"],
        ["GET", "/api/dashboard/hot-queries", "热点问题"],
        ["GET", "/api/dashboard/low-confidence", "低置信度队列"],
        ["GET", "/api/dashboard/metrics", "检索性能指标"],
    ],
    col_widths=[2.2, 7.2, 6.6],
)

add_heading("4.5 界面设计", 2)
add_para(
    "前端采用左侧深色导航栏 + 右侧内容区的布局。智能搜索视图以对话流形式呈现多轮问答，"
    "右侧 Agent 流程面板实时高亮 Planner—Retrieval—Critic—Synthesizer 的执行状态，并展示子查询数、"
    "迭代轮数、耗时与置信度等元信息；知识库视图以表格展示文档列表并支持上传；"
    "调研报告视图提供主题输入与报告列表；运营看板以统计卡片与列表展示运营指标。"
)

add_heading("4.6 关键设计决策与权衡", 2)
add_para(
    "系统设计过程中的关键决策包括：（1）选用 pgvector 而非独立向量数据库，以降低部署复杂度并复用关系型数据能力；"
    "（2）采用 LangGraph 而非手写循环，借助图结构清晰表达多步编排与条件回环；"
    "（3）SSE 流式问答复用同一套智能体单例而非依赖 LangGraph 已弃用的 astream_events，"
    "以保证跨版本稳定性；（4）BM25 索引采用内存结构并在数据变更后失效重建，"
    "开发阶段足够、后续可平滑迁移至 PostgreSQL tsvector 或 Redis 持久化。"
)

doc.add_page_break()

# ══════════════════════════════════════════════
# 第 5 章 数据库设计
# ══════════════════════════════════════════════
add_heading("第 5 章  数据库设计", 1)

add_heading("5.1 数据库选型与总体设计", 2)
add_para(
    "系统选用 PostgreSQL 16 作为主数据库，并安装 pgvector 扩展以支持向量存储与检索，"
    "Redis 用于 BM25 索引缓存与会话状态。数据库共设计四张核心表：documents（文档）、chunks（分片，含向量）、"
    "query_logs（查询日志）与 reports（调研报告）。其中 documents 与 chunks 为一对多关系，"
    "query_logs 与 reports 为独立业务表。"
)

add_heading("5.2 概念结构设计（E-R 图）", 2)
add_para(
    "系统实体-联系（E-R）图如图 5-1 所示。文档表 documents 与分片表 chunks 之间为一对多关系"
    "（一个文档对应多个分片），通过 document_id 外键关联并设置级联删除；"
    "查询日志表 query_logs 记录每次问答的问题、答案、引用、置信度与性能指标；"
    "调研报告表 reports 记录报告主题、状态、深度与内容。"
)
add_figure("er.png", "图 5-1  系统数据库 E-R 图", 15.5)

add_heading("5.3 逻辑结构设计（四表）", 2)
add_para("（1）documents 文档表，存储上传的原始文档元信息，字段如下：")
add_table(
    ["字段", "类型", "约束/说明"],
    [
        ["id", "int", "主键，自增"],
        ["filename", "varchar(255)", "原始文件名"],
        ["file_path", "varchar(500)", "存储路径"],
        ["file_type", "varchar(20)", "pdf/docx/md/txt/html"],
        ["file_size", "int", "文件大小（字节）"],
        ["title", "varchar(500)", "文档标题"],
        ["summary", "text", "文档摘要"],
        ["total_chunks", "int", "分片总数"],
        ["status", "varchar(20)", "uploaded/parsed/embedded/ready/error"],
        ["created_at / updated_at", "timestamp", "创建/更新时间"],
    ],
    col_widths=[4.2, 3.4, 8.4],
)
add_para("（2）chunks 文档分片表，存储知识库的最小检索单元，含向量字段，如下表所示。")
add_table(
    ["字段", "类型", "约束/说明"],
    [
        ["id", "int", "主键，自增"],
        ["document_id", "int", "外键 → documents.id，级联删除"],
        ["chunk_index", "int", "分片在文档中的序号"],
        ["content", "text", "分片文本内容"],
        ["embedding", "vector(1024)", "BGE 向量嵌入"],
        ["metadata", "json", "元数据（page_num/section/table_flag）"],
        ["token_count", "int", "估算 token 数"],
        ["created_at", "timestamp", "创建时间"],
    ],
    col_widths=[4.2, 3.4, 8.4],
)
add_para("（3）query_logs 查询日志表，记录每次问答与检索过程，用于评测与运营分析：")
add_table(
    ["字段", "类型", "约束/说明"],
    [
        ["id", "int", "主键，自增"],
        ["question / answer", "text", "用户问题 / 系统答案"],
        ["citations", "json", "引用来源列表"],
        ["confidence_score", "float", "答案置信度（0–1）"],
        ["retrieval_details", "json", "子查询、每查询片段数、迭代、agent_trace"],
        ["latency_ms", "int", "端到端延迟"],
        ["llm_tokens_used", "int", "LLM 总 token 消耗"],
        ["use_agentic", "bool", "是否走 Agentic 多步检索"],
        ["status / error", "varchar/text", "success/error 与失败原因"],
        ["user_feedback", "varchar(20)", "helpful/not_helpful"],
        ["created_at", "timestamp", "创建时间"],
    ],
    col_widths=[4.2, 3.4, 8.4],
)
add_para("（4）reports 调研报告表，存储后台生成的调研报告：")
add_table(
    ["字段", "类型", "约束/说明"],
    [
        ["id", "int", "主键，自增"],
        ["topic", "text", "调研主题"],
        ["status", "varchar(20)", "generating/ready/failed"],
        ["depth", "int", "检索深度（迭代轮数）"],
        ["content", "text", "Markdown 报告全文"],
        ["citations", "json", "引用来源列表"],
        ["stats", "json", "统计（子查询数/片段数/迭代/置信度）"],
        ["error", "text", "失败原因"],
        ["created_at / completed_at", "timestamp", "创建/完成时间"],
    ],
    col_widths=[4.2, 3.4, 8.4],
)

add_heading("5.4 向量索引设计", 2)
add_para(
    "chunks 表的 embedding 字段为 vector(1024) 类型，对应 BGE-large-zh-v1.5 的 1024 维输出。"
    "系统在其上创建 HNSW 索引并采用余弦距离算子（vector_cosine_ops），"
    "建索引语句为：CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops)。"
    "HNSW 索引在召回率与查询速度之间取得平衡，满足企业知识库中等规模（万级至十万级分片）的检索需求。"
    "此外，document_id 字段建有普通 B-tree 索引以加速按文档查询，"
    "created_at 字段用于运营看板的时间范围过滤。"
)

add_heading("5.5 物理存储与索引优化", 2)
add_para(
    "系统通过 docker-compose 编排 PostgreSQL（pgvector/pgvector:pg16）与 Redis（redis:7-alpine），"
    "启动时执行初始化脚本创建 pgvector 扩展。ORM 层使用 SQLAlchemy 异步引擎，"
    "向量检索通过 ORDER BY embedding <=> query 命中 HNSW 索引。"
    "BM25 索引为内存结构，文档新增/删除后标记失效并于下次检索时从数据库全量重建，"
    "开发阶段数据量小、重建开销可控。"
)

doc.add_page_break()

# ══════════════════════════════════════════════
# 第 6 章 系统实现
# ══════════════════════════════════════════════
add_heading("第 6 章  系统实现", 1)

add_heading("6.1 开发环境与工具", 2)
add_table(
    ["类别", "工具/技术"],
    [
        ["操作系统", "Windows 11"],
        ["开发语言", "Python 3.13（后端）、原生 JavaScript（前端）"],
        ["Web 框架", "FastAPI + Uvicorn + sse-starlette"],
        ["Agent 编排", "LangGraph + LangChain + langchain-openai"],
        ["数据库", "PostgreSQL 16 + pgvector（Docker）、Redis 7"],
        ["模型", "DeepSeek Chat（LLM）、BGE-large-zh-v1.5（Embedding）、BGE-Reranker-Base（精排）"],
        ["文档解析", "pdfplumber、python-docx、BeautifulSoup、html2text"],
        ["报告导出", "python-markdown + Chrome headless"],
        ["测试/评测", "pytest、playwright、自建评测脚本"],
    ],
    col_widths=[3.6, 12.4],
)

add_heading("6.2 文档入库实现", 2)
add_para(
    "文档入库链路（ingestion）依次完成解析、分片、向量化与入库。解析器根据文件扩展名路由到对应的解析函数，"
    "输出带元数据的文本块；分片器采用多策略分片（标题边界 → 段落边界 → 固定长度+重叠），"
    "其中表格与代码块保持完整不拆分，中文按句读断句以避免词语中间切断；"
    "向量化由 EmbeddingService 调用本地 BGE 模型将每个分片编码为 1024 维向量；"
    "最后将文档记录与分片（含向量）写入数据库，并标记 BM25 索引失效。"
)
add_para("分片器核心参数为：目标分片大小 500 字符、相邻重叠 50 字符、最小分片 50 字符。"
         "Token 估算按中文约 1.5 字符/token、英文约 4 字符/token 的规则近似计算。")

add_heading("6.3 混合检索实现", 2)
add_para(
    "混合检索器 HybridRetriever 实现了完整的检索管线。BM25 稀疏检索基于 rank_bm25 的 BM25Okapi，"
    "中文采用“单字 + 双字滑动窗口”的简化分词；向量检索通过 SQLAlchemy 的 cosine_distance 构造"
    "ORDER BY <=> 查询命中 HNSW 索引；两路结果经 RRF 融合（融合常数 k=60）得到初步排序；"
    "启用 Reranker 时，先粗排取更多候选（默认 20 条），再由 BGE-Reranker 对查询-文档对逐对打分，"
    "将精排分数按权重（默认 0.3）与 RRF 融合分加权求和，最终截断到 top_k。"
)
add_para("RRF 融合的核心代码逻辑为：对每路检索结果按排名倒数 1/(k+rank+1) 累加，"
         "并将融合分归一化到 0–1（两路第一名同时命中时为 1.0），如下所示：")
add_code_block(
    "for rank, (chunk_id, _) in enumerate(bm25_results):\n"
    "    rrf[chunk_id] = rrf.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)\n"
    "for rank, (chunk_id, _) in enumerate(vector_results):\n"
    "    rrf[chunk_id] = rrf.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)"
)

add_heading("6.4 Agentic 编排实现", 2)
add_para(
    "Agentic 编排基于 LangGraph StateGraph 实现，注册 planner、retrieval、critic、synthesizer 四个节点，"
    "以 planner 为入口。retrieval 节点通过条件边实现“所有子查询执行完毕后再进入 critic”的自循环；"
    "critic 节点通过 should_continue_retrieval 条件边路由：信息充分则进入 synthesizer，"
    "信息不足且有补充查询则回到 retrieval，达到迭代上限则强制进入 synthesizer。"
    "数据库会话通过 configurable 注入（避免把活动连接塞进 state 导致 checkpointer 持久化问题）。"
)
add_para(
    "除同步图执行外，系统还实现了流式变体 run_agentic_query_stream，其编排逻辑与图完全一致，"
    "区别仅在于 Synthesizer 采用逐 token 流式产出，配合 SSE 推送给前端；"
    "流式实现复用同一套智能体单例，不依赖 LangGraph 已弃用的 astream_events 接口。"
)

add_heading("6.5 多轮对话与指代消解实现", 2)
add_para(
    "问答请求体中的 history 字段承载多轮历史（list[ChatMessage]，含 role 与 content）。"
    "后端 utils/history 将历史格式化为提示片段，在 Planner 与 Synthesizer 的提示中显式告知模型"
    "结合历史理解“它/这个/第二个方案”等指代。前端维护 turns 数组并通过 localStorage 持久化会话，"
    "每次提问取最近 4 轮历史带给后端做指代消解，实现刷新后对话不丢失。"
)

add_heading("6.6 调研报告生成与 PDF 导出实现", 2)
add_para(
    "报告生成复用同一套 Agentic 编排，仅将 Synthesizer 切换为报告模式：要求 LLM 输出固定章节结构"
    "（背景/现状/技术方案/案例/趋势）的完整 Markdown，事实性陈述用 [n] 标注引用，文末附参考文献列表；"
    "若 LLM 遗漏参考文献章节，则程序化补齐以保证引用可溯源。报告状态经 generating → ready/failed 流转，"
    "前端轮询直至就绪。PDF 导出采用 Chrome headless 的 --print-to-pdf 能力将 Markdown 渲染为 PDF，"
    "避免引入 weasyprint 等重型依赖。"
)

add_heading("6.7 前端实现", 2)
add_para(
    "前端为原生 HTML/CSS/JS 单页应用，无框架依赖。智能搜索视图以对话流渲染多轮问答，"
    "通过手写的 fetch 流式读取器实现 POST 场景下的 SSE 客户端（EventSource 仅支持 GET），"
    "逐 token 追加文本并在流式结束后渲染 Markdown 与引用卡片。"
    "Agent 流程面板根据后端推送的 stage 事件实时高亮对应节点，并更新子查询数、迭代轮数、耗时与置信度。"
    "知识库、调研报告与运营看板视图通过统一的 fetch 封装调用后端接口并渲染表格与统计卡片。"
)

doc.add_page_break()

# ══════════════════════════════════════════════
# 第 7 章 系统测试与评测
# ══════════════════════════════════════════════
add_heading("第 7 章  系统测试与评测", 1)

add_heading("7.1 测试环境", 2)
add_para(
    "测试环境为 Windows 11，CPU 推理 BGE 模型（离线模式），PostgreSQL（pgvector）与 Redis 通过 "
    "Docker 运行，LLM 为 DeepSeek Chat。功能测试采用 pytest 编写单元测试，"
    "前端交互采用 playwright + Chrome headless 自动化验证。"
)

add_heading("7.2 功能测试", 2)
add_para("针对四大模块的核心功能进行了端到端测试，测试结果如下表所示。")
add_table(
    ["模块", "测试项", "预期结果", "结果"],
    [
        ["文档管理", "上传 PDF/TXT 并入库", "解析→分片→向量化→状态 ready", "通过"],
        ["文档管理", "批量上传", "部分失败不影响其他文件", "通过"],
        ["文档管理", "删除文档", "级联删除分片", "通过"],
        ["搜索问答", "单轮检索", "返回带引用与置信度的答案", "通过"],
        ["搜索问答", "Agentic 多步检索", "子查询分解、Critic 迭代、引用溯源", "通过"],
        ["搜索问答", "SSE 流式回答", "逐 token 输出，前端实时渲染", "通过"],
        ["搜索问答", "多轮对话与指代消解", "正确解析“它”等指代", "通过"],
        ["调研报告", "生成报告", "后台生成结构化 Markdown", "通过"],
        ["调研报告", "下载 Markdown/PDF", "返回对应格式文件", "通过"],
        ["运营看板", "统计与队列", "展示统计、热点问题、低置信度队列", "通过"],
        ["反馈闭环", "提交反馈", "落库 query_log 并更新反馈", "通过"],
    ],
    col_widths=[2.6, 4.2, 6.2, 3.0],
)

add_heading("7.3 检索性能评测（四组消融）", 2)
add_para(
    "为量化评估检索质量，系统构建了 110 条评测集，覆盖基线直配、同义改写、跨语言、多主题干扰、"
    "反向否定五类难度（各 22 条），每条记录期望关键词（库内 chunk 的真实子串）。"
    "知识库扩充至 385 个分片、17 份文档，覆盖智能客服、工业物联网、信息安全、人力资源、数据仓库、"
    "向量数据库、推荐系统、财务、IT 运维、数据合规等 10 个互不相关领域，制造检索干扰。"
    "评测指标包括 top-k 命中率、MRR（平均倒数排名）与 nDCG@5（归一化折损累计增益，二值相关性）。"
    "为验证各组件贡献，开展 BM25-only、向量-only、BM25+向量、完整+Reranker 四组消融实验，"
    "汇总指标如下表所示。"
)
add_table(
    ["指标", "BM25-only", "向量-only", "BM25+向量", "完整+Reranker"],
    [
        ["top-1 命中率", "72.73%", "74.55%", "69.09%", "76.36%"],
        ["top-3 命中率", "76.36%", "82.73%", "83.64%", "83.64%"],
        ["top-5 命中率", "77.27%", "83.64%", "89.09%", "85.45%"],
        ["MRR", "0.7462", "0.7871", "0.7708", "0.8026"],
        ["nDCG@5", "0.7529", "0.7991", "0.7989", "0.8150"],
    ],
    col_widths=[3.4, 3.0, 3.0, 3.0, 3.4],
)
add_para("四组消融的评测结果对比如图 7-1 所示。")
add_figure("eval.png", "图 7-1  检索评测消融对比（四组）", 14.5)
add_para(
    "消融结果表明：BM25 稀疏检索对字面精确匹配有效但语义泛化弱，整体最弱；"
    "向量稠密检索语义泛化强，跨语言与同义改写命中率明显高于 BM25；"
    "BM25+向量 经 RRF 融合兼顾字面与语义，top-3 与 top-5 召回达到最高，"
    "但其 top-1 略低于单路，是 RRF 对两路分歧取平均的典型效应；"
    "完整管线（+Reranker）对融合候选精排后，top-1、MRR 与 nDCG@5 均达到最优，"
    "说明 Reranker 主要提升首位精度，其 top-5 召回相较无 Reranker 略降，"
    "是精排以少量召回换取更高精度的典型 trade-off，符合预期。"
)

add_heading("7.4 中文分词对比", 2)
add_para(
    "为提升中文检索质量，将 BM25 中文分词由简化的字符滑动窗口升级为 jieba 分词，并引入停用词过滤。"
    "在 67 条中文查询上对比两套分词方案：jieba 的 top-5 命中率为 86.57%，字符滑动窗口为 89.55%，"
    "二者差距在个位数以内；但 jieba 将 BM25 索引词汇表由 1347 个缩减至 890 个（缩小约 34%）。"
    "结果表明：字符 n-gram 对字面匹配更鲁棒，jieba 则以约 3 个百分点的字面命中率为代价，"
    "换取词级语义切分与更精简的索引，更适合大规模知识库场景。"
)

add_heading("7.5 生成质量评测（RAGAS）", 2)
add_para(
    "为评估端到端生成质量，接入 RAGAS 框架，采用 LLM-as-judge 对真实问答样本评测四项指标："
    "忠实度（faithfulness，回答是否忠于检索上下文）、回答相关性（answer_relevancy）、"
    "上下文精确率（context_precision）与上下文召回率（context_recall）。评测结果如下表所示。"
)
add_table(
    ["指标", "分数", "说明"],
    [
        ["faithfulness", "0.7455", "回答是否忠于检索上下文（无编造）"],
        ["answer_relevancy", "0.6341", "回答与问题的相关程度"],
        ["context_precision", "0.8371", "相关上下文在检索结果中的排序精度"],
        ["context_recall", "0.8636", "检索结果覆盖参考答案信息的比例"],
    ],
    col_widths=[4.2, 2.8, 8.6],
)
add_para(
    "faithfulness 为 0.75，表明生成的回答整体忠于检索上下文、无编造；answer_relevancy 为 0.63，"
    "随查询难度上升（同义改写、跨语言、多主题干扰等难例）而有所下降，符合预期；"
    "context_precision（0.84）与 context_recall（0.86）表明检索上下文具备良好的覆盖与排序质量，"
    "且在不同难度样本上呈现合理区分度。"
)

add_heading("7.6 多轮对话与指代消解测试", 2)
add_para(
    "对多轮对话与指代消解能力进行了专项验证：第一轮提问“什么是 RRF 混合检索？”，"
    "系统返回了带引用的完整回答；第二轮追问“它和 BM25 是什么关系？”，"
    "系统正确识别“它”指代上一轮的 RRF，并回答“RRF 与 BM25 是协同配合的关系，"
    "RRF 是融合算法，BM25 是稀疏检索算法”，验证了历史上下文传递与指代消解的有效性。"
)

add_heading("7.7 系统演示", 2)
add_para(
    "图 7-2 为智能搜索模块的多轮对话界面，展示了用户问题气泡、流式回答、引用卡片、"
    "置信度与耗时等元信息，以及右侧 Agent 流程面板的实时状态。"
)
add_figure("demo_chat_multiturn.png", "图 7-2  智能搜索模块（多轮对话与指代消解）", 15.0)
add_para("图 7-3 为知识库模块，展示文档列表（文件名、类型、状态、分片数与上传时间）。")
add_figure("demo_kb.png", "图 7-3  知识库模块", 15.0)
add_para("图 7-4 为调研报告模块，展示主题输入、检索深度选择与报告列表。")
add_figure("demo_report.png", "图 7-4  调研报告模块", 15.0)
add_para("图 7-5 为运营看板模块，展示文档数、分片数、查询总量、平均置信度及热点问题、低置信度队列。")
add_figure("demo_dashboard.png", "图 7-5  运营看板模块", 15.0)

add_heading("7.8 测试结论", 2)
add_para(
    "综合功能测试与评测结果，系统各功能模块运行正常，端到端流程通畅；"
    "四组消融实验验证了混合检索与 Reranker 精排的贡献，完整管线在 top-1 命中率（76.36%）、"
    "MRR（0.8026）与 nDCG@5（0.8150）上均达最优；"
    "jieba 分词在保持命中率基本持平的同时将 BM25 索引缩减约 34%；"
    "RAGAS 评测表明生成回答的忠实度与相关性良好；"
    "Agentic 多步检索能够正确完成子查询分解、Critic 迭代与指代消解。系统达到预期设计目标。"
)

doc.add_page_break()

# ══════════════════════════════════════════════
# 第 8 章 总结与展望
# ══════════════════════════════════════════════
add_heading("第 8 章  总结与展望", 1)

add_heading("8.1 工作总结", 2)
add_para(
    "本文围绕企业知识管理与智能检索的实际需求，设计并实现了一套基于 Agentic RAG 的企业智能搜索与自动调研系统，"
    "完成了以下工作：构建了文档入库全链路，支持多格式解析、多策略分片与向量化入库；"
    "实现了 BM25 + 向量 + RRF + Reranker 的混合检索；基于 LangGraph 实现了 Planner—Retrieval—Critic—Synthesizer "
    "四智能体的多步检索编排与防死循环保护；实现了多轮对话与指代消解、SSE 流式回答、引用溯源与反馈闭环；"
    "实现了自动调研报告生成与 PDF 导出；搭建了运营看板；并建立了检索评测体系，"
    "验证了 Reranker 精排对检索质量的显著提升。"
)

add_heading("8.2 系统不足与局限", 2)
add_para(
    "系统仍存在以下不足：（1）BM25 索引仍为内存结构，大规模数据下内存占用与重建开销较大，"
    "未实现真正的增量更新；（2）Embedding 与 Reranker 在 CPU 上推理，"
    "大批量入库与高并发下吞吐受限；（3）评测语料为程序化生成的合成企业文档，"
    "虽覆盖多主题、多难度，但与真实企业文档分布仍有差异；（4）RAGAS 评测样本规模有限（22 条），"
    "且为合成语料，端到端生成质量的评估仍有待更大规模真实数据的验证。"
)

add_heading("8.3 未来展望", 2)
add_para(
    "后续工作可从以下方向展开：引入 PostgreSQL tsvector 或 Elasticsearch 等持久化索引实现 BM25 增量更新，"
    "进一步降低大规模数据下的内存与重建开销；支持 GPU 推理与模型服务化部署以提升吞吐；"
    "扩充真实企业文档评测语料与 RAGAS 难例样本，使生成质量评测更具区分度；"
    "探索多路召回、查询改写、HyDE 等进阶检索策略，进一步提升复杂问题的回答质量。"
)

doc.add_page_break()

# ══════════════════════════════════════════════
# 参考文献
# ══════════════════════════════════════════════
add_heading("参考文献", 1)
refs = [
    "Lewis P, Perez E, Piktus A, et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks[C]. NeurIPS, 2020.",
    "Karpukhin V, Oğuz B, Min S, et al. Dense Passage Retrieval for Open-Domain Question Answering[C]. EMNLP, 2020.",
    "Robertson S, Zaragoza H. The Probabilistic Relevance Framework: BM25 and Beyond[J]. Foundations and Trends in Information Retrieval, 2009.",
    "Cormack G V, Clarke C L A, Buettcher S. Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods[C]. SIGIR, 2009.",
    "Malkov Y A, Yashunin D A. Efficient and Robust Approximate Nearest Neighbor Search Using Hierarchical Navigable Small World Graphs[J]. IEEE TPAMI, 2020.",
    "Asai A, Wu Z, Wang Y, et al. Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection[C]. ICLR, 2024.",
    "Yan S Q, Gu J C, Zhu Y, et al. Corrective Retrieval Augmented Generation[J]. arXiv preprint arXiv:2401.15884, 2024.",
    "Xiao S, Liu Z, Zhang P, et al. C-Pack: Packaged Resources To Advance General Chinese Embedding[J]. arXiv preprint arXiv:2309.07597, 2023.",
    "DeepSeek-AI. DeepSeek-V3 Technical Report[J]. arXiv preprint arXiv:2412.19437, 2024.",
    "Chase H. LangChain: Building applications with LLMs through composability[EB/OL]. https://github.com/langchain-ai/langchain.",
    "LangChain-AI. LangGraph: Building stateful, multi-actor applications with LLMs[EB/OL]. https://github.com/langchain-ai/langgraph.",
    "pgvector. Open-source vector similarity search for Postgres[EB/OL]. https://github.com/pgvector/pgvector.",
]
for i, ref in enumerate(refs, 1):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.3
    p.paragraph_format.left_indent = Pt(24)
    p.paragraph_format.first_line_indent = Pt(-24)
    r = p.add_run(f"[{i}] {ref}")
    set_run(r, SONG, Pt(10.5))

doc.add_page_break()

# ══════════════════════════════════════════════
# 致谢
# ══════════════════════════════════════════════
add_heading("致  谢", 1)
add_para(
    "本设计报告的完成离不开指导教师的悉心指导与帮助。在选题、方案设计与报告撰写过程中，"
    "老师给予了大量宝贵的意见和建议，使本人在专业知识与工程实践能力上都有了显著提升，在此表示衷心感谢。"
)
add_para(
    "同时感谢在项目开发过程中提供帮助的同学与朋友，感谢开源社区贡献的 LangChain、LangGraph、"
    "pgvector、FastAPI 等优秀工具，它们为本项目的实现提供了坚实的技术基础。"
)
add_para(
    "最后，感谢学校与学院提供的良好学习与实践环境，让我能够将课堂所学应用于实际工程项目中，"
    "完成本次综合工程实践。"
)

doc.add_page_break()

# ══════════════════════════════════════════════
# 附录：项目部署
# ══════════════════════════════════════════════
add_heading("附录  项目部署", 1)

add_heading("A.1 环境要求", 2)
add_table(
    ["项目", "要求"],
    [
        ["操作系统", "Windows 10/11、macOS 或 Linux"],
        ["Python", "3.11+（本项目使用 3.13）"],
        ["Docker", "Docker Desktop（用于 PostgreSQL + pgvector + Redis）"],
        ["浏览器", "Chrome（用于报告 PDF 导出与前端访问）"],
        ["网络", "首次需下载 BGE 模型（约 2.3 GB），可用 HF 镜像"],
    ],
    col_widths=[3.6, 12.4],
)

add_heading("A.2 启动依赖服务", 2)
add_para("通过 Docker Compose 一键启动 PostgreSQL（含 pgvector）与 Redis：")
add_code_block("docker compose up -d")
add_para(
    "编排内容包括 postgres（pgvector/pgvector:pg16，端口 5432，用户 rag_user / 密码 rag_pass / 库 rag_db）"
    "与 redis（redis:7-alpine，端口 6379）。首次启动会执行 scripts/init-db.sql 创建 pgvector 扩展。"
)

add_heading("A.3 安装依赖与配置", 2)
add_para("创建虚拟环境并安装依赖：")
add_code_block(
    "python -m venv .venv\n"
    ".venv\\Scripts\\activate        # Windows\n"
    "pip install -r requirements.txt"
)
add_para("配置环境变量：复制 .env.example 为 .env，至少填写 OPENAI_API_KEY（DeepSeek），其余保持默认即可。"
         "若本机无法直连 huggingface.co，下载模型前先设置镜像：")
add_code_block("set HF_ENDPOINT=https://hf-mirror.com")

add_heading("A.4 模型缓存与离线运行", 2)
add_para(
    "系统本地运行两个 BGE 模型：BGE-large-zh-v1.5（Embedding，1024 维，约 1.2 GB）与 "
    "BGE-Reranker-Base（精排，约 1.1 GB），首次运行自动下载并缓存到 ~/.cache/huggingface/hub。"
    "模型缓存后即可完全离线运行，避免内网代理访问超时："
)
add_code_block("set HF_HUB_OFFLINE=1\nset TRANSFORMERS_OFFLINE=1")

add_heading("A.5 启动服务与验收", 2)
add_para("启动后端服务：")
add_code_block("cd backend\npython -m uvicorn app.main:app --host 0.0.0.0 --port 8000")
add_para("浏览器访问 http://localhost:8000 进入前端 SPA，健康检查 http://localhost:8000/api/health。")
add_para("运行测试与评测：")
add_code_block(
    "cd backend\n"
    "HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest tests/ -q\n"
    "HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python scripts/eval_retrieval.py --reranker both"
)
add_para(
    "项目提供了 scripts/dev_server.bat 一键启动脚本，已内置清空代理与离线模式的环境变量，"
    "可直接双击运行，规避代理导致的外部 API 访问异常。"
)

# ── 保存 ──────────────────────────────────────
doc.save(OUT)
print("报告已生成：", OUT)
