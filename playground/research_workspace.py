"""Submit a research demo and print its evidence, answer and PDF page links."""

import argparse
import asyncio
import json
from pathlib import Path

import httpx

from launchpad.main import app
from launchpad.workflows.examples.research_workspace import config

EXAMPLES = (
    Path(__file__).resolve().parents[1]
    / "app/launchpad/workflows/examples/research_workspace/request_examples"
)


async def submit(client: httpx.AsyncClient, path: str, **kwargs: object) -> dict:
    response = await client.post(path, **kwargs)
    response.raise_for_status()
    if config.DEMO_MODE:
        events = [
            json.loads(line[6:])
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        if "event: completed\n" not in response.text:
            raise SystemExit(events[-1]["message"])
        return events[-1]["outputs"]

    job = response.json()
    print(f"任务 {job['run_id']} 已提交", flush=True)
    try:
        async with asyncio.timeout(300):
            while True:
                status = await client.get(job["status_url"])
                status.raise_for_status()
                result = status.json()
                if result["status"] == "failed":
                    raise SystemExit(f"任务 {job['run_id']} 失败：{result['message']}")
                if result["status"] == "completed":
                    if result.get("trace_id"):
                        print(f"Langfuse trace_id: {result['trace_id']}")
                    return result["outputs"]
                await asyncio.sleep(1)
    except TimeoutError:
        raise SystemExit(
            f"任务仍在后台执行，可查询 {client.base_url.join(job['status_url'])}"
        )


async def main(args: argparse.Namespace) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app) if config.DEMO_MODE else None,
        base_url="http://research.local" if config.DEMO_MODE else config.API_URL,
        timeout=30,
        trust_env=httpx.URL(config.API_URL).host
        not in {"localhost", "127.0.0.1", "::1"},
    ) as client:
        if args.pdf:
            paper = json.loads(args.paper.read_text())
            with args.pdf.open("rb") as file:
                await submit(
                    client,
                    "/research/pdf",
                    files={"file": (args.pdf.name, file, "application/pdf")},
                    data={"library": args.library, "paper": json.dumps(paper)},
                )
        elif not args.skip_import:
            payload = json.loads((EXAMPLES / "import.json").read_text())
            await submit(
                client, "/research/events", json=payload | {"library": args.library}
            )

        request = json.loads((EXAMPLES / "reading.json").read_text())
        request["library"] = args.library
        if args.query:
            request.update(query=args.query, keywords=args.keywords)
        elif args.keywords is not None:
            request["keywords"] = args.keywords

        search = await submit(
            client, "/research/events", json=request | {"action": "search"}
        )
        for index, hit in enumerate(search["RetrievePapersNode"]["hits"], 1):
            paper = hit["paper"]
            chunk = hit.get("chunk") or {}
            print(
                f"\n命中 {index} · {paper['title']} · 页码 {chunk.get('pages') or '无'}"
            )
            print(chunk.get("text", "")[:250])

        result = await submit(client, "/research/events", json=request)
        note = result["WriteReadingNoteNode"]
        print(f"\n{note['note']['answer']}")
        sources = {paper["id"]: paper["source_url"] for paper in note["sources"]}
        for cid, passage in note["passages"].items():
            url = passage.get("locator") or sources[passage["paper_id"]]
            print(f"[{cid}] {client.base_url.join(url)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query")
    parser.add_argument("--keywords")
    parser.add_argument("--library", default="information-retrieval")
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--paper", type=Path, help="PDF metadata JSON")
    parser.add_argument(
        "--skip-import", action="store_true", help="Query an existing library"
    )
    args = parser.parse_args()
    if bool(args.pdf) != bool(args.paper):
        parser.error("--pdf and --paper must be provided together")
    if args.pdf and args.skip_import:
        parser.error("--pdf and --skip-import are mutually exclusive")
    if config.DEMO_MODE:
        print("演示模式：内存资料库、关键词检索、预设模型。")
    asyncio.run(main(args))
