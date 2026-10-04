"""Optional, read-only PDF inspection; mechanical checks never grant visual approval."""
from collections import Counter
import hashlib
import importlib
import math
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit

from .common import StudioError


def _dependencies():
    modules = {}
    for name in ("pypdf", "pdfplumber"):
        try:
            modules[name] = importlib.import_module(name)
        except ImportError as exc:
            raise StudioError("PDF 检查依赖缺失：{}；安装 PDF 可选依赖后重试".format(name)) from exc
    return modules["pypdf"], modules["pdfplumber"]


def _object(value):
    return value.get_object() if hasattr(value, "get_object") else value


def _reference(value):
    if hasattr(value, "idnum"):
        return (value.idnum, value.generation)
    ref = getattr(value, "indirect_reference", None)
    return _reference(ref) if ref is not None else None


def _raw_name(value):
    if isinstance(value, bytes):
        return bytes(value)
    try:
        return value.original_bytes
    except (AttributeError, UnicodeEncodeError):
        return None


def _issue(code, message, page=None, **details):
    result = {"code": code, "message": message}
    if page is not None:
        result["page"] = page
    if details:
        result["details"] = details
    return result


def _box(value):
    result = [float(x) for x in value]
    if len(result) != 4 or not all(math.isfinite(x) for x in result):
        raise ValueError("页框必须包含四个有限坐标")
    if result[2] <= result[0] or result[3] <= result[1]:
        raise ValueError("页框宽高必须为正")
    return result


def _font_inventory(resources, page_number, fonts, visited):
    resources = _object(resources) or {}
    if not isinstance(resources, dict) or id(resources) in visited:
        return
    visited.add(id(resources))
    for value in (_object(resources.get("/Font")) or {}).values():
        font = _object(value)
        children = [_object(child) for child in (_object(font.get("/DescendantFonts")) or [])]
        leaves = children or [font]
        subtype = str(font.get("/Subtype", "unknown"))
        embedded = subtype == "/Type3" and bool(font.get("/CharProcs"))
        if not embedded:
            embedded = all(any(key in (_object(leaf.get("/FontDescriptor")) or {})
                               for key in ("/FontFile", "/FontFile2", "/FontFile3")) for leaf in leaves)
        name = str(font.get("/BaseFont", font.get("/Name", "unknown"))).lstrip("/")
        aliases = {name} | {str(child.get("/BaseFont", name)).lstrip("/") for child in children}
        key = (name, subtype, bool(embedded))
        item = fonts.setdefault(key, {"name": name, "subtype": subtype, "embedded": bool(embedded),
                                      "pages": set(), "used_pages": set(), "aliases": set()})
        item["pages"].add(page_number)
        item["aliases"].update(aliases)
    for value in (_object(resources.get("/XObject")) or {}).values():
        xobject = _object(value)
        if isinstance(xobject, dict) and xobject.get("/Subtype") == "/Form":
            _font_inventory(xobject.get("/Resources"), page_number, fonts, visited)


def _links(reader, errors):
    named = reader.named_destinations
    raw_names = {_raw_name(key): value for key, value in named.items() if _raw_name(key) is not None}
    page_refs = {_reference(page): number for number, page in enumerate(reader.pages, 1)}
    counts = Counter(total=0, internal=0, resolved=0, external=0, invalid=0, relative_file_links=0)
    details = []

    def resolve(destination, seen=None):
        seen = set() if seen is None else seen
        destination = _object(destination)
        if isinstance(destination, (str, bytes)):
            identity = (type(destination).__name__, repr(destination))
            if identity in seen:
                return None
            seen.add(identity)
            value = named.get(destination)
            if value is None:
                value = raw_names.get(_raw_name(destination))
            if value is None:
                return None
            return resolve(value, seen)
        if isinstance(destination, dict):
            if "/Page" in destination:
                return page_refs.get(_reference(destination["/Page"]))
            return resolve(destination.get("/D"), seen)
        if isinstance(destination, (list, tuple)) and destination:
            first = destination[0]
            if _reference(first) is not None:
                return page_refs.get(_reference(first))
            if isinstance(first, int) and 0 <= first < len(reader.pages):
                return int(first) + 1
        return None

    for number, page in enumerate(reader.pages, 1):
        for value in (_object(page.get("/Annots")) or []):
            annotation = _object(value)
            if annotation.get("/Subtype") != "/Link":
                continue
            counts["total"] += 1
            action = _object(annotation.get("/A")) or {}
            action_type = action.get("/S")
            destination = action.get("/D") if action_type == "/GoTo" else annotation.get("/Dest")
            item = {"page": number, "action": str(action_type or "/Dest")}
            if destination is not None or action_type == "/GoTo":
                counts["internal"] += 1
                target = resolve(destination)
                item.update(target_page=target, destination=str(destination)[:200])
                if target is None:
                    counts["invalid"] += 1
                    errors.append(_issue("invalid_internal_link", "内部链接目的地不能解析", number,
                                         destination=item["destination"]))
                else:
                    counts["resolved"] += 1
            elif action_type in ("/URI", "/GoToR", "/Launch"):
                uri = action.get("/URI") if action_type == "/URI" else _object(action.get("/F"))
                if isinstance(uri, dict):
                    uri = uri.get("/UF", uri.get("/F", ""))
                uri = str(uri or "")
                item["uri"] = uri
                counts["external"] += 1
                try:
                    scheme = urlsplit(uri).scheme.lower()
                except ValueError:
                    scheme = ""
                if not scheme or scheme == "file" or (len(scheme) == 1 and uri[1:2] == ":"):
                    counts["relative_file_links"] += 1
                    errors.append(_issue("relative_file_link", "PDF 残留本地或相对文件链接", number, uri=uri))
            else:
                item["unchecked"] = True
            details.append(item)
    return {**dict(counts), "named_destinations": len(named), "details": details}


def _render(path, output_dir, report):
    if output_dir is None:
        raise StudioError("PDF 校样需要显式 output_dir；纯扫描请保持 render=False")
    executable = shutil.which("pdftoppm")
    if not executable:
        raise StudioError("PDF 校样依赖缺失：pdftoppm（Poppler）")
    candidates = [1, 2, 3, report["pages"]]
    candidates += [item["page"] for item in report["errors"] if item.get("page")]
    candidates += [item["page"] for item in report["warnings"] if item.get("page")]
    selected = list(dict.fromkeys(page for page in candidates if 1 <= page <= report["pages"]))[:12]
    directory = Path(output_dir).resolve()
    targets = [(page, directory / ("page-{:04d}.png".format(page))) for page in selected]
    if any(target.exists() for _, target in targets):
        raise StudioError("PDF 校样目标已存在，保留原文件；请使用新的 output_dir")
    directory.mkdir(parents=True, exist_ok=True)
    outputs = []
    for page, target in targets:
        try:
            result = subprocess.run([executable, "-f", str(page), "-l", str(page), "-singlefile",
                                     "-scale-to", "1400", "-png", str(path), str(target.with_suffix(""))],
                                    capture_output=True, text=True, timeout=90)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StudioError("PDF 校样渲染失败：{}".format(exc)) from exc
        if result.returncode or not target.is_file():
            raise StudioError("PDF 校样渲染失败：" + (result.stderr or result.stdout)[-2000:])
        outputs.append({"page": page, "path": str(target)})
    return outputs


def inspect_pdf(path, output_dir=None, render=False):
    """Inspect a PDF without writes unless render=True; never return visual pass.

    pages is a count; errors/warnings are structured issue lists. page_details,
    links.details and fonts preserve evidence for review. Sparse/blank pages are
    candidates, not layout failures. A one-point edge tolerance avoids noise.
    """
    pypdf, pdfplumber = _dependencies()
    path = Path(path).resolve()
    if not path.is_file():
        raise StudioError("PDF 文件不存在：" + str(path))
    if render and output_dir is None:
        raise StudioError("PDF 校样需要显式 output_dir；纯扫描请保持 render=False")
    errors, warnings, page_details, fonts = [], [], [], {}
    try:
        with path.open("rb") as source:
            reader = pypdf.PdfReader(source)
            if reader.is_encrypted:
                raise StudioError("PDF 检查不接受加密文件，请提供可读取副本")
            pages = len(reader.pages)
            if not pages:
                errors.append(_issue("empty_pdf", "PDF 没有页面"))
            for number, page in enumerate(reader.pages, 1):
                try:
                    media, crop = _box(page.mediabox), _box(page.cropbox)
                    if crop[0] < media[0] - 1 or crop[1] < media[1] - 1 or crop[2] > media[2] + 1 or crop[3] > media[3] + 1:
                        errors.append(_issue("invalid_cropbox", "裁切框超出纸张页框", number, media=media, crop=crop))
                    page_details.append({"page": number, "media_box": media, "crop_box": crop,
                                         "width_pt": round(media[2] - media[0], 3),
                                         "height_pt": round(media[3] - media[1], 3), "rotation": int(page.rotation)})
                except (ValueError, TypeError) as exc:
                    errors.append(_issue("invalid_page_box", str(exc), number))
                    page_details.append({"page": number})
                _font_inventory(page.get("/Resources"), number, fonts, set())
            links = _links(reader, errors)
        with pdfplumber.open(path) as document:
            for number, page in enumerate(document.pages, 1):
                chars = [char for char in page.chars if str(char.get("text", "")).strip()]
                bounds = tuple(float(value) for value in page.bbox)
                used_fonts = {str(char.get("fontname", "")).lstrip("/") for char in chars}
                for font in fonts.values():
                    if number in font["pages"] and used_fonts.intersection(font["aliases"]):
                        font["used_pages"].add(number)
                overflow = []
                for char in chars:
                    excess = {"left": bounds[0] - char["x0"], "right": char["x1"] - bounds[2],
                              "top": bounds[1] - char["top"], "bottom": char["bottom"] - bounds[3]}
                    excess = {edge: round(value, 3) for edge, value in excess.items() if value > 1}
                    if excess:
                        overflow.append({"text": char["text"], "excess_pt": excess})
                if overflow:
                    errors.append(_issue("text_outside_page", "文字越过纸张边界，需要人工回看", number,
                                         requires_review=True, count=len(overflow), sample=overflow[:30]))
                height = bounds[3] - bounds[1]
                body = [char for char in chars if char["top"] >= bounds[1] + height * .09
                        and char["bottom"] <= bounds[1] + height * .91]
                image_count = len(page.images)
                drawing_count = len(page.rects) + len(page.curves) + len(page.lines)
                blank = not chars and not image_count and not drawing_count
                sparse = len(body) < 40 or len(chars) < 60
                page_details[number - 1].update(chars=len(chars), body_chars=len(body), images=image_count,
                                                drawings=drawing_count, blank_candidate=blank, sparse_candidate=sparse)
                if blank or sparse:
                    warnings.append(_issue("blank_page_candidate" if blank else "sparse_page_candidate",
                                           "疑似空白页，需人工判断" if blank else "低密度页面候选，封面或插图页可能正常",
                                           number, chars=len(chars), body_chars=len(body), images=image_count))
                page.close()
    except StudioError:
        raise
    except Exception as exc:
        raise StudioError("PDF 结构检查失败：{}".format(exc)) from exc
    font_records = []
    for font in fonts.values():
        record = {key: sorted(value) if isinstance(value, set) else value
                  for key, value in font.items() if key != "aliases"}
        font_records.append(record)
        if not font["embedded"]:
            issue = _issue("font_not_embedded", "字体未嵌入 PDF", name=font["name"], pages=record["used_pages"] or record["pages"])
            (errors if font["used_pages"] else warnings).append(issue)
    report = {"ok": not errors, "file": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "errors": errors, "warnings": warnings, "pages": pages, "page_details": page_details,
              "links": links, "fonts": sorted(font_records, key=lambda item: (item["name"], item["subtype"])),
              "visual_review": "pending", "rendered_files": [],
              "tools": {"pypdf": pypdf.__version__, "pdfplumber": pdfplumber.__version__}}
    if render:
        report["rendered_files"] = _render(path, output_dir, report)
    return report
