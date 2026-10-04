"""Fixed-source PDF export with a shared, independently versioned layout."""
from pathlib import Path
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile

from .common import StudioError, atomic_write, git_commit, safe_path

LAYOUT_VERSION = "series-pdf-v1.2"
PROFILES = ("standard", "mobile")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def code_blocks(ast, include_inline=False):
    result = []
    def collect(node):
        if isinstance(node, dict):
            if node.get("t") == "Figure":
                _, caption, contents = node["c"]
                # Pandoc duplicates an implicit figure's caption as Image.alt.
                # Count the identical semantic text once, without deduplicating
                # unrelated or genuinely repeated code elsewhere in the book.
                if len(contents) == 1 and contents[0].get("t") == "Plain":
                    inlines = contents[0]["c"]
                    if len(inlines) == 1 and inlines[0].get("t") == "Image" and caption == [None, [{"t": "Plain", "c": inlines[0]["c"][1]}]]:
                        collect(caption)
                        return
            if node.get("t") == "CodeBlock" or (include_inline and node.get("t") == "Code"):
                attributes, code = node["c"]
                if node["t"] != "CodeBlock" or "mermaid" not in attributes[1]:
                    result.append({"index": len(result) + 1, "kind": node["t"], "classes": attributes[1], "text": code})
            else:
                for value in node.values(): collect(value)
        elif isinstance(node, list):
            for value in node: collect(value)
    collect(ast.get("blocks", []))
    return result


def map_pdf_prose(body, transform):
    """Conservatively keep literal Markdown out of presentation-only rewrites.

    Protect fences (also inside quotes/lists), indented lines and exact-length
    backtick spans, including spans crossing a newline. Ambiguous indentation is
    left alone; the final Pandoc AST comparison remains the integrity backstop.
    """
    result, literals, fence = [], {}, None
    prefix = "\x00PDF_LITERAL_"
    while prefix in body:
        prefix += "_"

    def hide(text):
        key = prefix + str(len(literals)) + "\x00"
        literals[key] = text
        return key

    for line in body.splitlines(keepends=True):
        content = re.sub(r"^(?: {0,3}>[ \t]?)+", "", line)
        content = re.sub(r"^ {0,3}(?:[-+*]|\d+[.)])[ \t]+", "", content)
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", content)
        if fence:
            result.append(hide(line.rstrip("\r\n")) + line[len(line.rstrip("\r\n")):])
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= fence[1] and not content[marker.end():].strip():
                fence = None
        elif marker:
            fence = (marker[1][0], len(marker[1]))
            result.append(hide(line.rstrip("\r\n")) + line[len(line.rstrip("\r\n")):])
        elif content.startswith(("    ", "\t")):
            result.append(hide(line.rstrip("\r\n")) + line[len(line.rstrip("\r\n")):])
        else:
            result.append(line)
    masked = re.sub(r"(?<![\\`])(`+)(?!`)([\s\S]*?)(?<!`)\1(?!`)", lambda match: hide(match[0]), "".join(result))
    rendered = transform(masked)
    for key, literal in reversed(list(literals.items())):
        rendered = rendered.replace(key, literal)
    return rendered


def figure_captions(body, entries):
    """Keep an explicitly paired manuscript caption inside its PDF figure.

    Only consume the conventional caption immediately before the matching closing
    diagram marker. Ordinary following prose remains outside the figure.
    """
    for fid, filename, _, _ in entries:
        image = r'^!\[((?:\\.|[^]\\\n])*)\]\(' + re.escape(filename) + r'\)\{width=100%\}[ \t]*(?=\n|$)'
        caption = r'(?:[ \t]*\n)+[ \t]*\*图[：:]\s*([^\n]+)\*[ \t]*\n[ \t]*<!-- /diagram: ' + re.escape(fid) + r' -->'
        pattern = image + '(' + caption + ')?'
        def replace(match):
            title, paired, explanation = match.groups()
            label = fid + " · " + title
            if paired:
                label += "。" + explanation.strip()
            result = "![" + label + "](" + filename + "){width=100%}"
            return result + ("\n\n<!-- /diagram: " + fid + " -->" if paired else "")
        body = map_pdf_prose(body, lambda text: re.sub(pattern, replace, text, flags=re.M))
    return body


def monochrome_callouts(body, language):
    """Render known decorative quote prefixes as readable monochrome labels."""
    labels = {"💡": "Tip" if language == "en" else "提示",
              "⚠": "Warning" if language == "en" else "注意"}
    def line(value):
        match = re.match(r"^(>\s*)(💡|⚠)(?:\ufe0f)?[ \t]+", value)
        if match:
            return match[1] + "**" + labels[match[2]] + "** · " + value[match.end():]
        # The following visible label already carries these decorative meanings.
        return re.sub(r"^(>\s*)(?:🎯|🌿)[ \t]+(?=\*\*【(?:主线|支线)】)", r"\1", value)
    return map_pdf_prose(body, lambda text: "".join(line(value) for value in text.splitlines(keepends=True)))


def layout_config(book, commit, version, export_id, profile=None, export_date=None):
    options = (book.get("outputs") or {}).get("pdf") or {}
    if not isinstance(options, dict) or not options.get("enabled"):
        raise StudioError("该来源版本未启用 PDF")
    profile = profile or options.get("profile", "standard")
    if profile not in PROFILES:
        raise StudioError("PDF 阅读配置必须是 standard 或 mobile")
    day = export_date or datetime.date.today().isoformat()
    try:
        if datetime.date.fromisoformat(day).isoformat() != day:
            raise ValueError(day)
    except (ValueError, TypeError):
        raise StudioError("导出日期必须是 YYYY-MM-DD")
    lang = book.get("language", "zh-CN")
    if lang not in ("zh-CN", "zh-TW", "en"):
        raise StudioError("PDF 模板尚不支持主语言：" + str(lang))
    paper = options.get("paper", "a5")
    if paper not in ("a5", "b5", "a4"):
        raise StudioError("标准 PDF 纸张须为 a5、b5 或 a4")
    font = options.get("body_font", options.get("font", "PingFang SC"))
    config = {
        "layout_version": LAYOUT_VERSION, "profile": profile,
        "title": book["title"], "author": options.get("author", book.get("author", "马力")),
        "subtitle": options.get("subtitle", ""),
        "series_title": options.get("series_title", "普通人的 AI 工具入门系列"),
        "source_commit": commit, "version": version, "export_id": export_id,
        "export_date": day, "language": lang, "work_type": book.get("type", "book"),
        "paper": paper, "body_font": font,
        "heading_font": options.get("heading_font", font),
        "code_font": options.get("code_font", "Sarasa Mono SC"),
        "toc": options.get("toc", book.get("type") == "book"),
        "toc_depth": options.get("toc_depth", 1),
        "bookmark_depth": options.get("bookmark_depth", 4),
        "figure_appendix": options.get("figure_appendix", False),
    }
    for key in ("toc", "figure_appendix"):
        if type(config[key]) is not bool:
            raise StudioError("PDF " + key + " 须为布尔值")
    for key in ("toc_depth", "bookmark_depth"):
        if type(config[key]) is not int or not 1 <= config[key] <= 6:
            raise StudioError("PDF " + key + " 须为 1—6")
    for key in ("title", "author", "subtitle", "series_title", "body_font", "heading_font", "code_font"):
        if not isinstance(config[key], str) or (key.endswith("_font") and not config[key].strip()):
            raise StudioError("PDF " + key + " 须为有效文本")
    repo = (book.get("repository") or {}).get("name")
    config["source_url"] = "https://github.com/{}/tree/{}".format(repo, commit) if repo else ""
    return config


class LoggedRunner:
    def __init__(self, directory):
        self.directory = directory
        self.commands = []

    def run(self, args, cwd=None):
        record = {"args": [str(a) for a in args], "cwd": str(cwd) if cwd else None}
        self.commands.append(record)
        try:
            result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=300)
            record.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        except (OSError, subprocess.TimeoutExpired) as exc:
            record.update(error=str(exc))
            self.save()
            raise StudioError("{}: {}".format(args[0], exc))
        self.save()
        if result.returncode:
            raise StudioError("{} 失败：{}".format(args[0], (result.stderr or result.stdout)[-3000:]))
        return result.stdout.strip()

    def save(self):
        atomic_write(self.directory / "commands.json", json.dumps(self.commands, ensure_ascii=False, indent=2) + "\n")


def _font_inputs(source, options, config, runner):
    """Explicit font files are pinned; system discovery is identified honestly."""
    declared = sorted({config[k] for k in ("body_font", "heading_font", "code_font")})
    paths = options.get("font_paths", [])
    if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths):
        raise StudioError("PDF font_paths 须为书内字体目录列表")
    font_args, files = [], []
    for rel in paths:
        directory = safe_path(source, rel)
        if not directory.is_dir():
            raise StudioError("PDF 字体目录不存在：" + rel)
        font_args += ["--font-path", str(directory)]
        files += [{"path": str(p.relative_to(source)), "sha256": digest(p)}
                  for p in sorted(directory.rglob("*")) if p.is_file() and p.suffix.lower() in (".ttf", ".otf", ".ttc", ".otc")]
    if paths:
        font_args += ["--ignore-system-fonts", "--ignore-embedded-fonts"]
    inventory = runner.run(["typst", "fonts"] + font_args, source)
    available = {line.strip().casefold() for line in inventory.splitlines()}
    missing = [font for font in declared if font.casefold() not in available]
    if missing:
        raise StudioError("缺少声明的 PDF 字体：" + ", ".join(missing))
    return font_args, {"mode": "pinned-directory" if paths else "system-discovery",
                       "declared": declared, "files": files,
                       "inventory_sha256": hashlib.sha256(inventory.encode()).hexdigest(),
                       "limitation": None if paths else "系统字体名称已核对；字体源文件未固定，实际嵌入字体另见 qa.json"}


def _markdown(source, root, book, bodies, commit, config, runner):
    from .builder import rewritten_body, TICK
    from .illustrations import pdf_assets
    parts, figures = [], []
    for unit in book["units"]:
        body = rewritten_body(source, unit, bodies[unit["id"]], source, book["units"], pdf_mode=True, source_commit=commit)
        pattern = r"<!--\s*diagram:\s*([A-Za-z0-9_-]+)\s*-->\s*" + TICK + r"{3}mermaid\s*\n([\s\S]*?)" + TICK + r"{3}"
        def diagram(match):
            did, code = match.groups()
            if not any(d.get("id") == did and d.get("unit") == unit["id"] for d in book.get("diagrams", [])):
                raise StudioError("未登记的图：" + did)
            mmdc = os.environ.get("STUDIO_MMDC") or shutil.which("mmdc")
            if not mmdc:
                local = root / "tools/node_modules/.bin/mmdc"
                mmdc = str(local) if local.is_file() else None
            if not mmdc:
                raise StudioError("历史图渲染依赖缺失：mmdc；新图须采用已审手绘图")
            inp, out = source / ("diagram-" + did + ".mmd"), source / ("diagram-" + did + ".png")
            inp.write_text(code, encoding="utf-8")
            args = [mmdc, "-i", str(inp), "-o", str(out), "-b", "white", "-s", "2"]
            legacy_css = source / "tools/pdf-mermaid.css"
            if legacy_css.is_file():
                args += ["-C", str(legacy_css)]
            if os.environ.get("STUDIO_CHROME"):
                p = source / "puppeteer.json"
                p.write_text(json.dumps({"executablePath": os.environ["STUDIO_CHROME"]}))
                args += ["-p", str(p)]
            runner.run(args, source)
            if not out.is_file() or out.stat().st_size < 20:
                raise StudioError("图渲染未产生有效文件：" + did)
            figures.append((did, out.name, unit["id"], unit["title"]))
            return "![{}]({}){{width=100%}}".format(did, out.name)
        body = re.sub(pattern, diagram, body)
        body, entries = pdf_assets(source, unit, body, book)
        figures.extend(entries)
        body = figure_captions(body, entries)
        body = monochrome_callouts(body, config["language"])
        if re.search(TICK + r"{3}mermaid", body):
            raise StudioError(unit["path"] + ": 存在无登记标记的 Mermaid 图")
        if re.search(r"!\[[^\]]*\]\(https?://", body):
            raise StudioError("PDF 只使用已保存的本地图片，不能构建时下载")
        if config["figure_appendix"]:
            for did, filename, uid, _ in figures:
                if uid == unit["id"]:
                    label = "Open full-size figure" if config["language"] == "en" else "查看独立大图页"
                    body = body.replace("](" + filename + "){width=100%}", "](" + filename + "){width=100%}\n\n[" + label + "](#pdf-diagram-" + did + ")")
        if book.get("type") == "book":
            parts.append(TICK * 3 + "{=typst}\n#pagebreak(weak: true)\n" + TICK * 3)
        parts.append(body)
    if config["figure_appendix"] and figures:
        parts.append(TICK * 3 + '{=typst}\n#pagebreak(weak: true)\n#set page(paper: "a4", flipped: true, margin: 18mm, header: none)\n' + TICK * 3)
        for did, filename, uid, title in figures:
            label = "Return to chapter" if config["language"] == "en" else "返回本章"
            gallery = '#pagebreak(weak: true)\n#text(size: 14pt, weight: "bold", ' + json.dumps(did + " · " + title, ensure_ascii=False) + ') <pdf-diagram-' + did + '>\n'
            gallery += '#v(4mm)\n#block(width: 100%, height: 135mm)[#align(center + horizon)[#image(' + json.dumps(filename) + ', width: 100%, height: 100%, fit: "contain")]]\n'
            gallery += '#v(3mm)\n#link(<' + uid + '>)[ ' + label + ' ]\n'
            parts.append(TICK * 3 + '{=typst}\n' + gallery + TICK * 3)
    return "\n\n".join(parts) + "\n", figures


def export_pdf(root, source_ref, version, export_id, profile=None, export_date=None, language=None):
    from .builder import book_inputs
    from .checker import check_book
    from .pdf_qa import inspect_pdf
    if not source_ref or not version or not export_id:
        raise StudioError("PDF 需要 --source、--version 和 --export-id；不得隐式使用工作区")
    if not re.fullmatch(r"v\d{4}\.\d{2}\.\d+(?:-rc\.\d+)?", version) or not re.fullmatch(r"\d{2,}", export_id):
        raise StudioError("无效正文版本或导出编号")
    commit = git_commit(root, source_ref)
    tag = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "refs/tags/" + version + "^{commit}"], capture_output=True, text=True)
    if tag.returncode == 0 and tag.stdout.strip() != commit:
        raise StudioError("正文版本标签与 PDF 来源提交不一致：" + version)
    output = safe_path(root, "build/pdf/{}/{}".format(version, export_id))
    diagnostics = safe_path(root, "build/pdf-work/{}/{}".format(version, export_id))
    if output.exists() or diagnostics.exists():
        raise StudioError("导出编号已存在，保留文件和诊断；使用新编号")
    for tool in ("pandoc", "typst"):
        if not shutil.which(tool):
            raise StudioError("PDF 依赖缺失：" + tool)
    template = Path(__file__).resolve().parents[1] / "pdf/template.typ"
    if not template.is_file():
        raise StudioError("随书 PDF 模板缺失：" + str(template))
    archive = subprocess.run(["git", "-C", str(root), "archive", commit], capture_output=True)
    if archive.returncode:
        raise StudioError("Git snapshot 获取失败")
    with tempfile.TemporaryDirectory(prefix="studio-pdf-") as tmp:
        source = Path(tmp) / "source"; source.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            for member in tar.getmembers():
                safe_path(source, member.name)
                if not (member.isfile() or member.isdir()):
                    raise StudioError("PDF snapshot 不接受链接或特殊文件：" + member.name)
            if hasattr(tarfile, "data_filter"):
                tar.extractall(source, filter="data")
            else:
                tar.extractall(source)
        book, bodies = book_inputs(source)
        if language and language != book.get("language", "zh-CN"):
            raise StudioError("本轮 PDF 只支持来源提交的主语言；目标语言 PDF 尚未接通")
        errors = [i for i in check_book(source, freshness=False)["issues"] if i["level"] == "error"]
        if errors:
            raise StudioError("PDF 来源结构检查失败：" + json.dumps(errors, ensure_ascii=False))
        config = layout_config(book, commit, version, export_id, profile, export_date)
        from .branding import author_brand
        branding = author_brand(source, book, config["language"])
        if branding:
            config["author_avatar"] = branding["avatar"]
            if "author" not in ((book.get("outputs") or {}).get("pdf") or {}):
                config["author"] = branding["name"]
        diagnostics.mkdir(parents=True)
        runner = LoggedRunner(diagnostics)
        # Preserve fixed input and caller layout identity separately from the body commit.
        receipt = {"schema": 2, "source_commit": commit, "version": version, "export_id": export_id,
                   "profile": config["profile"], "language": config["language"], "export_date": config["export_date"],
                   "layout_version": LAYOUT_VERSION, "layout_sha256": digest(template),
                   "builder_sha256": digest(Path(__file__)), "toolkit_version": book.get("toolkit"),
                   "visual_review": "pending", "config": config}
        if branding:
            receipt["author_branding"] = branding
        tools_root = Path(__file__).resolve().parents[1]
        caller_files = sorted((tools_root / "studio_lib").glob("*.py")) + [template]
        caller_files += [tools_root / name for name in ("studio.py", "requirements.txt", "requirements-pdf.txt")
                         if (tools_root / name).is_file()]
        receipt["tool_sources"] = {str(p.relative_to(tools_root)): digest(p) for p in caller_files}
        try:
            for path in caller_files:
                saved = diagnostics / "caller-tools" / path.relative_to(tools_root)
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, saved)
            receipt["tools"] = {t: runner.run([t, "--version"]).splitlines()[0] for t in ("pandoc", "typst")}
            font_args, receipt["font_inputs"] = _font_inputs(source, (book.get("outputs") or {}).get("pdf") or {}, config, runner)
            text, figures = _markdown(source, root, book, bodies, commit, config, runner)
            receipt["diagrams"] = len(figures)
            (source / "export.md").write_text(text, encoding="utf-8")
            (source / "pdf-config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
            shutil.copy2(template, source / "pdf-template.typ")
            (source / "source-manuscript.md").write_text("\n\n".join(bodies[unit["id"]] for unit in book["units"]), encoding="utf-8")
            original_ast = json.loads(runner.run(["pandoc", "source-manuscript.md", "--from=markdown+raw_html+raw_attribute-citations", "--to=json"], source))
            code_sources = code_blocks(original_ast, include_inline=True)
            (source / "code-sources.json").write_text(json.dumps(code_sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            ast = json.loads(runner.run(["pandoc", "export.md", "--from=markdown+raw_html+raw_attribute-citations", "--to=json"], source))
            if code_sources != code_blocks(ast, include_inline=True):
                raise StudioError("PDF 适配改变了来源代码块或行内代码；保留诊断并停止导出")
            filename = "{}-{}-{}-{}.pdf".format(book["id"], version, export_id, config["profile"])
            result_pdf = source / filename
            runner.run(["pandoc", "export.md", "--from=markdown+raw_html+raw_attribute-citations", "--to=typst", "--standalone", "--syntax-highlighting=none", "--template=pdf-template.typ", "--metadata=lang:" + config["language"], "-o", "book.typ"], source)
            runner.run(["typst", "compile", "--root", str(source)] + font_args + ["book.typ", filename], source)
            if not result_pdf.is_file() or result_pdf.read_bytes()[:5] != b"%PDF-":
                raise StudioError("未产生有效 PDF")
            receipt.update(file=filename, sha256=digest(result_pdf), font=config["body_font"])
            qa = inspect_pdf(result_pdf)
            qa["file"] = filename
            warnings = [r["stderr"] for r in runner.commands if r.get("stderr")]
            missing_glyph = any(re.search(r"unknown font family|does not contain|missing glyph|not found in any font", s, re.I) for s in warnings)
            if missing_glyph:
                qa["errors"].append({"code": "font_warning", "message": "构建报告缺字或字体替代；检查 commands.json"})
                qa["ok"] = False
            receipt.update(pages=qa["pages"], machine_review="pass" if qa["ok"] else "fail", build_warnings=warnings)
            (diagnostics / "qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2) + "\n")
            if not qa["ok"]:
                raise StudioError("PDF 机械检查未通过；详见 " + str(diagnostics / "qa.json"))
            output.mkdir(parents=True)
            shutil.copy2(result_pdf, output / filename)
            shutil.copy2(diagnostics / "qa.json", output / "qa.json")
            atomic_write(output / "export.json", json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
        except (StudioError, OSError, ValueError) as exc:
            receipt.update(status="failed", error=str(exc))
            atomic_write(diagnostics / "export.json", json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
            raise
        finally:
            # Complete fixed-source inputs enable diagnostics without rebuilding live sources.
            shutil.copytree(source, diagnostics / "source", dirs_exist_ok=True)
            atomic_write(diagnostics / "input-files.json", json.dumps({str(p.relative_to(source)): digest(p) for p in sorted(source.rglob("*")) if p.is_file()}, ensure_ascii=False, indent=2) + "\n")
        return {"ok": True, "target": book["id"], "mode": "pdf", "source_commit": commit,
                "profile": config["profile"], "diagnostics": str(diagnostics),
                "outputs": [str(output / filename), str(output / "export.json"), str(output / "qa.json")],
                "pending": ["PDF 视觉审阅", "实际阅读器中的复制与跳转检查"]}
