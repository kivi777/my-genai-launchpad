---
name: research-reading
description: 检索科研资料、追溯原文页码、整理阅读笔记并按用户要求保存到 Notion。
---

1. 确定资料库名称和研究问题。需要直接查看证据时，调用 research-library 的 search_research_library，展示片段、论文原始链接、章节和页码。
2. 需要汇总时，调用 research-library 的 prepare_research_note。直接展示简明回答，原文位置单独列在来源中。
3. 用户要求保存时，确认目标 Notion 父页面。用官方 Notion MCP 的创建页面工具，在该页面下新建一页，把返回的 title 和 markdown 分别用作标题和内容。
4. 创建成功后返回 Notion 页面链接。连接尚未授权时，提示用户完成 Notion OAuth。写入结果未知时先检查目标父页面，避免重复创建。

用户要求生成科研周报时，收集用户提供或授权读取的带时间戳对话记录，
为每条记录保留唯一 ID，调用 `prepare_weekly_report` 并传入周一日期。
如果用户要求归档，用官方 Notion MCP 在指定父页面下新建一页，写入返回的
Markdown，并回传新页面链接。制作组会材料时，可以通过 Notion MCP 读取
已保存的周报，把页面 Markdown 作为科研工作台组会接口的 `weekly_report`。

用户要求把 Notion 笔记纳入知识库时，用 Notion MCP 读取目标页面，保留
页面 ID、标题、原始 URL 和 Markdown，再调用科研 MCP 的 `index_notion_note`。
