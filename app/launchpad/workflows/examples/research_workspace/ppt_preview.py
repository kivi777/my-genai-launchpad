import logging
import os
import subprocess
import sys
from pathlib import Path
from shutil import which
from tempfile import TemporaryDirectory
from threading import Lock
from xml.etree import ElementTree


logger = logging.getLogger(__name__)
_render_lock = Lock()


class PreviewUnavailable(RuntimeError):
    pass


def _render_environment(work: Path) -> dict[str, str]:
    env = os.environ.copy()
    if sys.platform == "darwin" and "FONTCONFIG_FILE" not in env:
        fonts = ElementTree.Element("fontconfig")
        for directory in (
            "/System/Library/Fonts",
            "/Library/Fonts",
            Path.home() / "Library/Fonts",
        ):
            ElementTree.SubElement(fonts, "dir").text = str(directory)
        ElementTree.SubElement(fonts, "cachedir").text = str(work / "fonts")
        for name in ("Microsoft YaHei", "微软雅黑"):
            alias = ElementTree.SubElement(fonts, "alias")
            ElementTree.SubElement(alias, "family").text = name
            preferred = ElementTree.SubElement(alias, "prefer")
            ElementTree.SubElement(preferred, "family").text = "Hiragino Sans GB"
        config = work / "fonts.conf"
        ElementTree.ElementTree(fonts).write(
            config, encoding="utf-8", xml_declaration=True
        )
        env["FONTCONFIG_FILE"] = str(config)
    return env


def preview_presentation(source: Path) -> Path:
    preview = source.with_suffix(".pdf")
    with _render_lock:
        if not source.is_file():
            raise FileNotFoundError(source.name)
        if (
            preview.is_file()
            and preview.stat().st_mtime_ns >= source.stat().st_mtime_ns
        ):
            return preview

        office = which("soffice") or which("libreoffice")
        mac_office = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        if not office and mac_office.is_file():
            office = str(mac_office)
        if not office:
            raise PreviewUnavailable("后端需要 LibreOffice 才能生成 PPT 预览。")

        with TemporaryDirectory(prefix=".ppt-preview-", dir=source.parent) as directory:
            work = Path(directory).resolve()
            profile = (work / "profile").as_uri()
            try:
                result = subprocess.run(
                    [
                        office,
                        f"-env:UserInstallation={profile}",
                        "--headless",
                        "--convert-to",
                        "pdf:impress_pdf_Export",
                        "--outdir",
                        str(work),
                        str(source.resolve()),
                    ],
                    env=_render_environment(work),
                    capture_output=True,
                    timeout=60,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                logger.warning(
                    "research_ppt_preview_process_failed",
                    extra={"artifact": source.name},
                )
                raise PreviewUnavailable("生成 PPT 预览失败，请稍后重试。") from exc
            rendered = work / preview.name
            if (
                result.returncode
                or not rendered.is_file()
                or rendered.stat().st_size == 0
            ):
                logger.warning(
                    "research_ppt_preview_conversion_failed",
                    extra={"artifact": source.name},
                )
                raise PreviewUnavailable("暂时无法渲染这份 PPT，请下载原文件查看。")
            rendered.replace(preview)
    return preview
