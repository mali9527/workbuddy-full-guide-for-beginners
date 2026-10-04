"""Book-local author identity, independent of teaching illustration policies."""
from pathlib import Path
from html import escape
from urllib.parse import quote
import hashlib
import os
import re

from .common import StudioError, safe_path


def author_brand(root, book, language=None):
    brand = book.get("branding")
    if brand is None:
        return None
    if not isinstance(brand, dict) or set(brand) - {"name", "name_en", "avatar", "sha256"}:
        raise StudioError("branding 只能包含 name、name_en、avatar、sha256")
    for field in ("name", "avatar", "sha256"):
        if not isinstance(brand.get(field), str) or not brand[field].strip():
            raise StudioError("branding 缺少有效的 " + field)
    if "name_en" in brand and (not isinstance(brand["name_en"], str) or not brand["name_en"].strip()):
        raise StudioError("branding.name_en 须为非空文本")
    if not re.fullmatch(r"[a-f0-9]{64}", brand["sha256"]):
        raise StudioError("branding.sha256 须为完整 SHA-256")
    avatar = safe_path(root, brand["avatar"])
    if avatar.suffix.lower() not in (".png", ".svg") or not avatar.is_file():
        raise StudioError("作者头像须为书内已保存的 PNG 或 SVG")
    if hashlib.sha256(avatar.read_bytes()).hexdigest() != brand["sha256"]:
        raise StudioError("作者头像与登记摘要不符；核对素材版本后再更新")
    language = language or book.get("language", "zh-CN")
    name = brand.get("name_en", brand["name"]) if language == "en" else brand["name"]
    return {"name": name, "avatar": brand["avatar"], "sha256": brand["sha256"]}


def author_html(root, book, parent=None, language=None):
    brand = author_brand(root, book, language)
    if not brand:
        return ""
    relative = os.path.relpath(safe_path(root, brand["avatar"]), Path(parent or root).resolve())
    src = escape(quote(Path(relative).as_posix(), safe="/"), quote=True)
    name = escape(brand["name"], quote=True)
    return '<p><img src="{}" width="48" height="48" alt="{}" align="absmiddle"> <strong>{}</strong></p>'.format(src, name, name)
