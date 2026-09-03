# 部署说明

## 1. Docker Compose 部署

项目依赖 PostgreSQL（含 pgvector 扩展）与 Redis，均由 `docker-compose.yml` 编排：

```bash
docker compose up -d
```

编排内容：

| 服务 | 镜像 | 端口 | 说明 |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | `5432` | 用户 `rag_user` / 密码 `rag_pass` / 库 `rag_db`，启动时执行 `scripts/init-db.sql` |
| `redis` | `redis:7-alpine` | `6379` | BM25 索引缓存等 |

常用命令：

```bash
docker compose ps               # 查看状态
docker compose logs -f postgres # 看日志
docker compose down             # 停止（保留数据卷）
docker compose down -v          # 停止并删除数据（慎用）
```

应用进程本身建议以本地方式运行（见 README「快速启动」）；如需容器化应用，只需把 `backend/` 挂载进容器，并让 `DATABASE_URL` / `REDIS_URL` 指向 compose 网络内的服务名即可。

---

## 2. 模型缓存说明

系统本地运行两个 BGE 模型（不消耗 API 费用）：

| 模型 | 用途 | 大小（约） |
|---|---|---|
| `BAAI/bge-large-zh-v1.5` | Embedding（1024 维，中英双语） | ~1.2 GB |
| `BAAI/bge-reranker-base` | Reranker 精排 | ~1.1 GB |

- 首次运行会通过 HuggingFace 下载，缓存到 `~/.cache/huggingface/hub`。
- 本机无法直连 huggingface.co 时，先设置镜像再启动：

  ```bash
  export HF_ENDPOINT=https://hf-mirror.com
  ```

- 模型已缓存后，可完全离线运行（避免沙箱/内网代理访问 HF 超时）：

  ```bash
  export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
  python -m uvicorn app:app --port 8000
  ```

- 仓库内 `models/bge-reranker-base/` 仅存放 tokenizer / config 参考文件；实际权重以 HF 缓存为准。

---

## 3. 环境变量说明

配置加载顺序（`app/config.py`）：

1. 系统环境变量（优先级最高）
2. `backend/.env`
3. 项目根目录 `.env`

因此如果发现改了 `.env` 不生效，优先检查是否被系统环境变量覆盖（Windows 可查 `os.environ` / `HKCU\Environment`）。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `OPENAI_API_KEY` | 占位符 | 主 LLM 的 API Key（DeepSeek） |
| `OPENAI_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI 兼容 API 地址 |
| `LLM_MODEL` | `deepseek-chat` | 主模型名 |
| `DATABASE_URL` | `postgresql+asyncpg://rag_user:rag_pass@localhost:5432/rag_db` | 异步数据库连接串 |
| `SYNC_DATABASE_URL` | 同步版连接串 | 用于同步工具 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接串 |
| `EMBEDDING_MODEL` | `BAAI/bge-large-zh-v1.5` | Embedding 模型 |
| `EMBEDDING_DEVICE` | `cpu` | 推理设备（`cpu` / `cuda`） |
| `EMBEDDING_DIMENSION` | `1024` | 向量维度 |
| `RERANKER_MODEL` | `BAAI/bge-reranker-base` | Reranker 模型 |
| `RERANKER_ENABLED` | `true` | 是否启用 Reranker（评测可一键关） |
| `CHROME_PATH` | `C:\Users\27809\AppData\Local\Google\Chrome\Application\chrome.exe` | PDF 导出的 Chrome 路径 |
| `UPLOAD_DIR` | `./uploads` | 上传文件目录 |
| `MAX_UPLOAD_SIZE_MB` | `50` | 上传大小上限 |
| `ALLOWED_EXTENSIONS` | `.pdf,.docx,.doc,.md,.txt,.html` | 允许的扩展名 |
| `CHECKPOINT_POSTGRES_URI` | 空 | LangGraph 持久化 checkpointer（可选） |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | 服务监听地址 |

---

## 4. 验收 / 测试命令

```bash
cd backend
# 全量单测（模型离线；若系统环境变量 OPENAI_API_KEY 会覆盖 .env，请先 unset）
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest tests/ -q

# 检索评测（Reranker 开/关对比，输出 output/eval_result.md）
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python scripts/eval_retrieval.py --reranker both
```
