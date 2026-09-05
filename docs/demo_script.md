# 系统演示脚本（约 6 分 30 秒）

项目：基于 Agentic RAG 的企业智能搜索与自动调研系统  
执行环境：Windows，浏览器打开 `http://localhost:3000`；后端 API 为 `http://localhost:8000`。  
启动命令：在项目根目录执行 `docker compose up -d`，再执行 `scripts\dev_server.bat`。

| 时段 | 动作 | 讲解词（≤50字） | 截图路径 |
|---|---|---|---|
| 0:00-0:30 | 启动系统，打开首页 | 系统基于 FastAPI 和 pgvector，统一提供搜索、问答、调研和看板。 | （可省略） |
| 0:30-1:30 | 打开知识库，上传 1 篇 PDF，等待索引完成 | 知识库已索引 402 个文档片段，上传后会自动解析、切分并建立向量索引。 | `D:\agentic-rag-system\report\images\demo_kb.png` |
| 1:30-2:30 | 在搜索框输入“什么是 RAG”，提交并展开引用 | 这是简单问答示例，答案下方保留来源片段，方便核对原文。 | `D:\agentic-rag-system\report\images\demo_search.png` |
| 2:30-3:30 | 切换聊天页，输入复杂问题，观察流式输出 | 复杂问题会经过规划、多路检索和证据审查，再流式生成回答。 | `D:\agentic-rag-system\report\images\demo_chat.png` |
| 3:30-4:30 | 在同一会话追问“它有什么优势” | 系统结合上一轮上下文，把“它”正确解析为 RAG，完成指代消解。 | `D:\agentic-rag-system\report\images\demo_chat_multiturn.png` |
| 4:30-5:30 | 打开调研页，输入主题，生成报告并导出 PDF | Agent 自动组织 5 个章节，引用跟随内容保留，报告可以直接导出。 | `D:\agentic-rag-system\report\images\demo_report.png` |
| 5:30-6:30 | 打开运营看板，查看命中率、反馈和 Top 文档 | 看板汇总检索命中率、用户反馈和高频文档，帮助定位系统改进方向。 | `D:\agentic-rag-system\report\images\demo_dashboard.png` |

## 现场检查清单

1. 启动前关闭代理：`env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`。
2. 确认页面能访问后再开始计时；上传 PDF 时预留索引完成提示。
3. 若现场网络或模型不可用，按上表截图顺序播放，讲解词保持不变。
