# 科研工作台

把论文、代码与数据集入口、Notion 笔记放进同一资料库，再从证据检索一路生成研究计划、周报和组会 PPT。科研业务使用上游的 `WorkflowRegistry`、`events` 表、Redis 和 `process_incoming_event` Celery Worker。

## 启动

从 `docker/.env.example` 创建 `docker/.env`，按模板配置数据库密码，再加上 `DEEPSEEK_API_KEY` 和 `SILICONFLOW_API_KEY`。启动 Docker 或 OrbStack 后，在仓库根目录运行：

```sh
(cd docker && docker compose -f docker-compose.launchpad.yml -f docker-compose.research.yml up --build -d --wait)
```

API 启动时执行 Alembic 迁移。Worker 容器安装 Docling 和组会工具依赖。Docling 首次使用会下载版面模型。模型成功缓存后，可在 `docker/.env` 设置 `HF_HUB_OFFLINE=1`，让 Worker 直接使用缓存，避免重复向 Hugging Face 检查模型。DeepSeek 和硅基流动仍按正式模式联网。API 和 Worker 通过绑定挂载共享后端仓库的 `data/research-uploads/`。PPT 和数据库各有自己的数据卷。打开 [FastAPI 文档](http://127.0.0.1:8080/docs) 提交任务。

每次提交返回 HTTP 202、`run_id` 和 `status_url`。以 `GET /research/jobs/{run_id}` 查询状态。任务进度和失败详情写入 PostgreSQL 的 `events.research_progress`，成功结果写入 `events.task_context`。启用 Langfuse 后，进度中同时记录 `trace_id`。队列发布失败时返回 503 和事件 ID，可据此查状态。当前没有自动补投机制。PDF 和 Excel 原件写入宿主机上传目录。保留其中按任务 ID 命名的子目录，才能从已有索引打开原文。该 API 适合本地单用户使用。

用 `uv run --locked python playground/research_workspace.py` 验证运行中的队列。可用 `RESEARCH_DEMO_MODE=1` 跑同一个脚本的无密钥进程内演示。演示模式用内存检索和脚本模型，适合本地讲解。

## 任务进度与 Langfuse

问答、检索、导入、科研周报、组会 PPT 与阅读器翻译使用同一套进度记录。
页面在发起任务的位置显示「任务详情」，运行中轮询步骤，结束后显示各阶段的耗时、
计数和失败摘要。重新打开历史会话时也可查看每轮问答的进度记录。

空白会话只存在于页面。第一条问答或检索请求提交时，后端在一个事务里创建会话和任务事件。
会话记录支持重命名和删除。删除会话会一并清理其 PostgreSQL 任务事件和问答结果，
有任务正在等待或执行的会话须等任务结束后再删除。

使用 Compose 时，在 `docker/.env` 为 Worker 配置
`RESEARCH_LANGFUSE_ENABLED=1`、`LANGFUSE_BASE_URL`、`LANGFUSE_PUBLIC_KEY`
和 `LANGFUSE_SECRET_KEY`。本机启动 Worker 时，在进程环境或根目录 `.env`
配置同样的变量。填写 `LANGFUSE_PROJECT_ID` 后，任务执行时即可显示跳转链接。
留空时，系统在任务结束后通过 SDK 获取项目链接。

一个任务的 UUID 对应一个 Langfuse Trace，同一会话的多轮问答按会话 ID 归组。
Trace 只记录步骤、耗时、计数、模型标识和错误摘要。论文正文、对话内容、
实验数据和向量不作为 Trace 输入或输出发送。

## 上传文件持久化

本机运行后端时默认使用仓库的 `data/research-uploads/`，可以通过根目录
`.env` 中的 `RESEARCH_UPLOAD_DIR` 指定其他路径。Compose 把该宿主目录挂载到
API 和 Worker 的 `/workspace/data/research-uploads`，Worker 只读。
可在 `docker/.env` 通过 `RESEARCH_UPLOAD_HOST_DIR` 更改宿主目录。
独立演示栈默认使用 `data/research-demo-uploads/`，可用
`RESEARCH_DEMO_UPLOAD_HOST_DIR` 覆盖。

从旧的 Compose 部署升级时，先等上传任务完成，在替换旧 API 容器前把
`/research-artifacts/uploads/` 下的文件复制到新目录，保留任务 ID 子目录：

```sh
mkdir -p data/research-uploads
docker cp <旧API容器名>:/research-artifacts/uploads/. data/research-uploads/
```

如果旧后端直接运行在本机，将原 `RESEARCH_UPLOAD_DIR` 内的文件复制到新目录。
备份资料库时同时备份上传目录和 PostgreSQL。

## 面试演示

如果还没有模型密钥，可先启动独立的无密钥演示栈。以下命令使用轻量 PostgreSQL + pgvector 镜像和独立的数据卷，安装组会依赖。请先完成上面的 `docker/.env` 配置，演示时两项模型密钥可留空。

```sh
(cd docker && RESEARCH_OFFLINE_MODE=1 RESEARCH_WORKER_EXTRAS='--extra meeting' docker compose \
  -p research-interview -f docker-compose.launchpad.yml \
  -f docker-compose.research.yml -f docker-compose.research-demo.yml up --build -d --wait)
uv run --locked python playground/research_workspace.py
```

脚本会提交摘要入库、独立检索和问答任务，打印任务 ID、召回片段及引用。这个模式仍使用真实 FastAPI、Redis、Celery、PostgreSQL 和 pgvector，模型部分用固定规则和词项哈希向量演示。建议使用独立演示栈，避免示例数据覆盖正式资料。两套栈依次启动，默认共用本机 8080 端口。Compose 镜像拉取遇到镜像站 401 时，可以设置 `LAUNCHPAD_PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.13.13-slim-bookworm` 使用同版本 Python 镜像。

正式模式配置 DeepSeek 和硅基流动密钥后，可运行下面的 PDF 演示。无密钥模式也能执行这个示例，前提是启动时去掉 `RESEARCH_WORKER_EXTRAS` 覆盖以安装 Docling，首次解析需下载 Docling 权重。

```sh
curl -fL https://aclanthology.org/2020.emnlp-main.550.pdf -o /tmp/dpr.pdf
uv run --locked python playground/research_workspace.py \
  --library interview-pdf --pdf /tmp/dpr.pdf \
  --paper app/launchpad/workflows/examples/research_workspace/request_examples/dpr-paper.json \
  --query 'DPR 如何分别编码问题和段落？' --keywords 'DPR OR encoder'
```

上传后，检索和问答结果附带 `/research/pdf/{run_id}#page=页码`，点击可打开本地 PDF 对应页。旧版入库记录重新上传后即可获得跳页链接。再次演示同一资料库时，用 `--skip-import` 保留已有资料，省去现场解析时间。

```sh
(cd docker && docker compose -p research-interview -f docker-compose.launchpad.yml \
  -f docker-compose.research.yml -f docker-compose.research-demo.yml down)
```

## 四项任务

### 1. 建立科研知识库

- **论文与资产**。通过 `POST /research/pdf` 上传 `file`、`library` 和 JSON 字符串 `paper`。前端上传时由后端按资料库自动分配编号，原文链接可选。导入保留论文原题。开启「自动生成关键词」后，DeepSeek 先从 PDF 首页提取原文标题，再仅根据标题生成最多 3 个中文检索关键词。「查询发表渠道与 CCF 等级」是独立开关，默认关闭。开启后，DeepSeek 从首页提取原题和发表证据，首页未确认正式渠道时按原题查询 Crossref。后端按本地已核对的 CCF 人工智能目录条目匹配等级。未匹配的字段留空，预览结果随论文提交入库。正式 PDF 入库需要 DeepSeek 和硅基流动密钥。Worker 用 Docling HybridChunker 按结构分块，保留章节和页码，再用硅基流动 BGE-M3 生成 1024 维向量。同一资料库的相同 ID 会更新记录、替换旧片段。已有论文资产和旧版 JSON 请求继续兼容。也可用 `POST /research/events` 的 [import_papers 样例](request_examples/import.json) 导入多条摘要。
- **个人笔记**。授权 Notion MCP 客户端读取目标页面，通过科研 MCP 的 `index_notion_note` 提交 Markdown，或通过 [import_notion 请求](request_examples/notion.json) 提交相同数据。Worker 按 Markdown 标题和长度分段，保留 Notion 页面 ID、URL 和章节。相同页面重新导入会更新其片段。PDF 与笔记可在同一资料库检索，来源类型可见。

论文可选择自动生成检索关键词。Notion 笔记可用逗号或顿号分隔多个关键词。关键词与资料一同入库，查询时输入完整关键词可优先匹配对应资料。删除资料会清除记录和索引，后续导入继续使用新编号。已有 ID 和显式传入页面 ID 的 MCP 导入继续兼容。

在 Navicat 核对片段数、发表信息和向量维度，可在连接的 `postgres → public` 下执行：

```sql
SELECT p.library, p.paper_id, p.payload->>'title' AS title,
       p.payload->'keywords' AS keywords,
       p.payload#>>'{publication,venue}' AS venue,
       c.embedding_backend, vector_dims(c.bge_embedding) AS dimensions,
       count(c.number) AS chunk_count
FROM public.research_papers p
LEFT JOIN public.research_chunks c USING (library, paper_id)
GROUP BY 1, 2, 3, 4, 5, 6, 7
ORDER BY 1, 2;
```

### 2. 查询文献并构建科研思路

提交 [reading_note 请求](request_examples/reading.json)。DeepSeek 先输出结构化检索计划。PostgreSQL 全文检索和 pgvector 向量检索用 RRF 融合。生成节点依据召回证据输出摘要、证据缺口和带交付物的下一步研究计划，并可调用工具查已登记的代码和数据集。返回片段 ID、链接、章节及 PDF 页码。仅需要原始证据时把 `action` 改成 `search`。

可选只读扩展通过 `RESEARCH_EXTERNAL_MCP_URL` 和 `RESEARCH_EXTERNAL_MCP_TOOL` 配置。工具接收 `{"query": "..."}`，用于补充资料库之外的信息。

### 3. 生成周报

提交 [weekly_report 请求](request_examples/weekly.json)，包含周一日期和你提供的一周对话记录。Worker 按上海时区筛选周一至周日，用 DeepSeek 提炼完成事项、发现、阻塞和下周计划，每条带对话 ID。完成结果提供 Markdown。Notion MCP 客户端可在你指定的页面下归档周报。对话从客户端提供，任务由请求触发。

### 4. 制作组会 PPT

通过 `POST /research/meeting` 上传 XLSX，传入周报任务 ID（同一资料库）或已有周报 Markdown，再指定提示、工作表和列名。Worker 读取 Excel、检索文献、让 DeepSeek 组织大纲，再调用独立的 `render_meeting_pptx` MCP 工具。完成结果的 `RenderMeetingNode.url` 是下载地址。图表直接读取 Excel 数值，支持一个类别列、一个数值列和最多 100 条数据。公式值需预先计算并保存。文献出处附原文链接和可用页码。

```sh
curl -sS http://127.0.0.1:8080/research/meeting \
  -F 'file=@results.xlsx' \
  -F 'library=information-retrieval' \
  -F 'query=突出 DPR 基线、Recall@10 和下一步实验' \
  -F 'weekly_run_id=替换为周报任务ID' \
  -F 'worksheet=Results' \
  -F 'category_column=Method' \
  -F 'value_column=Recall@10'
```

也可用 `weekly_report=<weekly.md` 代替 `weekly_run_id`。默认 renderer 为本地 stdio MCP 进程。配置 `RESEARCH_PPT_MCP_URL` 可换成 Streamable HTTP 服务。工具接收 `outline`、`experiment` 和 `evidence`，返回 `filename` 和可访问的下载 `url`。

## MCP 与可观测性

把 [MCP 示例](request_examples/mcp.json) 中的科研连接器路径替换为本机虚拟环境路径，并加载 [科研 Skill](skills/research-reading/SKILL.md)。科研 MCP 通过 API 提交队列任务，默认 API 地址为 `http://127.0.0.1:8080`，可用 `RESEARCH_API_URL` 指定。Notion MCP 走客户端 OAuth，客户端负责读取或写入页面。

设置 `RESEARCH_LANGFUSE_ENABLED=1` 与 `LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`、
`LANGFUSE_BASE_URL` 后，仅 `search` 和 `reading_note` 任务会生成 Trace。它涵盖意图规划、
检索节点的输入与命中结果，以及问答模型和工具调用。文档入库、批量向量嵌入、周报和组会 PPT
不启用 Langfuse。查询向量化仍在检索节点内执行，当前没有单独的嵌入追踪。
嵌入文本仍发给硅基流动，汇总输入仍发给 DeepSeek。

自托管时，单独启动 Langfuse 的 Docker Compose 并创建本地项目和密钥。在本机 Docker
可通过宿主机别名访问该端口时，可将 `LANGFUSE_BASE_URL` 设为
`http://host.docker.internal:3000`，或配置为 Worker 能访问的其他地址。
Python SDK 已声明在项目依赖中，Worker 镜像构建时自动安装。
