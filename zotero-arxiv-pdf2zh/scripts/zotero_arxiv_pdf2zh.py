#!/usr/bin/env python3
"""Sync-safe arXiv-to-Zotero and pdf2zh helper."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

HOME = Path.home()
DEFAULT_PDF2ZH_SERVER_DIR = HOME / "Documents" / "zotero-pdf2zh" / "server"

ZOTERO = os.environ.get("ZOTERO_LOCAL_BASE_URL", "http://127.0.0.1:23119").rstrip("/")
PDF2ZH = os.environ.get("PDF2ZH_BASE_URL", "http://127.0.0.1:8890").rstrip("/")
LOCAL_USER = "/api/users/0"
PDF2ZH_SERVER_DIR = Path(os.environ.get("PDF2ZH_SERVER_DIR", str(DEFAULT_PDF2ZH_SERVER_DIR))).expanduser()
TRANSLATED_DIR = Path(os.environ.get("PDF2ZH_TRANSLATED_DIR", str(PDF2ZH_SERVER_DIR / "translated"))).expanduser()
ZOTERO_DIR = Path(os.environ.get("ZOTERO_DATA_DIR", str(HOME / "Zotero"))).expanduser()
ZOTERO_DB = ZOTERO_DIR / "zotero.sqlite"
ZOTERO_STORAGE = ZOTERO_DIR / "storage"
ZOTERO_APP_NAME = os.environ.get("ZOTERO_APP_NAME", "Zotero")
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"


def fail(message: str) -> None:
    raise SystemExit(message)


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: Any = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10,
) -> Any:
    body = None
    req_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, method=method, headers=req_headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
        if "json" in response.headers.get("Content-Type", "").lower():
            return json.loads(text or "null")
        return text


def zotero_api(path: str) -> Any:
    return request_json(
        ZOTERO + path,
        headers={"Zotero-API-Version": "3"},
        timeout=8,
    )


def connector(path: str, payload: Any) -> Any:
    return request_json(
        ZOTERO + path,
        method="POST",
        payload=payload,
        headers={"X-Zotero-Connector-API-Version": "3"},
        timeout=30,
    )


def health(url: str) -> dict[str, Any]:
    try:
        data = request_json(url, timeout=3)
        return {"ok": True, "response": data}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def clean_ws(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def norm_title(text: str | None) -> str:
    text = norm(text)
    text = re.sub(r"\s*([:;,.!?()\[\]{}\-–—/])\s*", r"\1", text)
    return re.sub(r"[^\w]+", "", text)


def title_match(candidate: str | None, query: str) -> bool:
    c = norm(candidate)
    q = norm(query)
    loose_c = norm_title(candidate)
    loose_q = norm_title(query)
    return bool(c and q and (q in c or c in q or loose_q in loose_c or loose_c in loose_q))


def random_id(length: int = 8) -> str:
    alphabet = "23456789ABCDEFGHIJKLMNPQRSTUVWXYZ"
    return "".join(random.choice(alphabet) for _ in range(length))


def file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def storage_mtime_ms(path: Path) -> int:
    return int(path.stat().st_mtime * 1000)


def safe_pdf_filename(title: str) -> str:
    base = re.sub(r"[^\w .()\\[\\]-]+", " ", title, flags=re.UNICODE)
    base = re.sub(r"\s+", " ", base).strip(" .")
    if not base:
        base = "pdf2zh"
    return (base[:120].rstrip(" .") + ".pdf")


def translated_title_for_path(path: Path, fallback: str | None = None) -> str:
    name = path.name.casefold()
    if ".dual." in name or name.endswith(".dual.pdf"):
        return "pdf2zh zh-CN dual PDF"
    if ".mono." in name or name.endswith(".mono.pdf"):
        return "pdf2zh zh-CN mono PDF"
    return fallback or "pdf2zh zh-CN translated PDF"


def collections() -> list[dict[str, Any]]:
    return zotero_api(f"{LOCAL_USER}/collections")


def collection_map() -> dict[str, dict[str, Any]]:
    rows = collections()
    by_key = {row["key"]: row for row in rows}
    paths: dict[str, dict[str, Any]] = {}

    def path_for(row: dict[str, Any]) -> str:
        data = row.get("data", row)
        name = data.get("name") or row.get("key")
        parent = data.get("parentCollection")
        if parent and parent in by_key:
            return path_for(by_key[parent]) + "/" + name
        return name

    for row in rows:
        path = path_for(row)
        row["_path"] = path
        paths[norm(path)] = row
    return paths


def resolve_collection(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    matches = [row for key, row in collection_map().items() if key == norm(path)]
    if len(matches) > 1:
        fail(f"Ambiguous collection path: {path}")
    return matches[0] if matches else None


def selected_target() -> dict[str, Any] | None:
    try:
        return connector("/connector/getSelectedCollection", {})
    except Exception:
        return None


def selected_target_path(target: dict[str, Any] | None) -> str | None:
    if not target:
        return None
    selected_id = "C" + str(target.get("id")) if target.get("id") is not None else None
    stack: list[str] = []
    for row in target.get("targets") or []:
        level = row.get("level", 0)
        name = row.get("name")
        if not name:
            continue
        stack = stack[:level]
        stack.append(name)
        if selected_id and row.get("id") == selected_id:
            return "/".join(stack[1:] if stack and stack[0] == target.get("libraryName") else stack)
    return target.get("name")


def search_items(title: str, collection_key: str | None = None) -> list[dict[str, Any]]:
    queries = [title]
    compact = re.sub(r"\s*:\s*", ":", title)
    prefix = title.split(":", 1)[0].strip()
    for query in (compact, prefix):
        if query and query not in queries:
            queries.append(query)
    found = []
    seen = set()
    for query in queries:
        params = {"q": query, "include": "data"}
        url = f"{LOCAL_USER}/items/top?{urllib.parse.urlencode(params)}"
        rows = zotero_api(url)
        for row in rows:
            if row["key"] in seen:
                continue
            data = row.get("data", row)
            if not title_match(data.get("title"), title):
                continue
            if collection_key and collection_key not in (data.get("collections") or []):
                continue
            seen.add(row["key"])
            found.append(row)
    return found


def arxiv_id_from_text(text: str) -> str:
    match = re.search(
        r"(?:(?:arxiv:|/abs/|/pdf/)?)(\d{4}\.\d{4,5}(?:v\d+)?|[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)",
        text,
        re.I,
    )
    if not match:
        fail(f"Could not parse arXiv id from: {text}")
    return match.group(1).removesuffix(".pdf")


def fetch_arxiv_metadata(arxiv_id: str) -> dict[str, Any]:
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"id_list": arxiv_id, "max_results": 1})
    with urllib.request.urlopen(url, timeout=20) as response:
        root = ET.fromstring(response.read())
    entry = root.find(f"{ATOM}entry")
    if entry is None:
        fail(f"No arXiv metadata found for: {arxiv_id}")
    canonical_id = (entry.findtext(f"{ATOM}id") or "").rsplit("/", 1)[-1] or arxiv_id
    title = clean_ws(entry.findtext(f"{ATOM}title") or "")
    summary = clean_ws(entry.findtext(f"{ATOM}summary") or "")
    published = (entry.findtext(f"{ATOM}published") or "")[:10]
    authors = [
        {"creatorType": "author", "firstName": "", "lastName": clean_ws(author.findtext(f"{ATOM}name") or "")}
        for author in entry.findall(f"{ATOM}author")
    ]
    categories = [node.attrib.get("term", "") for node in entry.findall(f"{ATOM}category") if node.attrib.get("term")]
    primary = entry.find(f"{ARXIV}primary_category")
    primary_category = primary.attrib.get("term") if primary is not None else (categories[0] if categories else "")
    pdf_url = ""
    for link in entry.findall(f"{ATOM}link"):
        if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
            pdf_url = link.attrib.get("href", "")
            break
    if not pdf_url:
        pdf_url = f"https://arxiv.org/pdf/{canonical_id}"
    return {
        "id": canonical_id,
        "title": title,
        "summary": summary,
        "published": published,
        "authors": authors,
        "categories": categories,
        "primary_category": primary_category,
        "abs_url": f"https://arxiv.org/abs/{canonical_id}",
        "pdf_url": pdf_url,
    }


def zotero_item_from_arxiv(meta: dict[str, Any], collection_key: str | None = None) -> dict[str, Any]:
    arxiv_id = meta["id"]
    category = f" [{meta['primary_category']}]" if meta.get("primary_category") else ""
    item = {
        "itemType": "preprint",
        "id": random_id(),
        "title": meta["title"],
        "creators": meta["authors"],
        "abstractNote": meta["summary"],
        "date": meta["published"],
        "url": meta["abs_url"],
        "DOI": "10.48550/arXiv." + arxiv_id,
        "archiveID": "arXiv:" + arxiv_id,
        "extra": "arXiv:" + arxiv_id + category,
        "libraryCatalog": "arXiv.org",
        "repository": "arXiv",
        "number": "arXiv:" + arxiv_id,
        "tags": [{"tag": tag, "type": 1} for tag in meta["categories"]],
        "attachments": [
            {
                "id": random_id(),
                "title": "Preprint PDF",
                "url": meta["pdf_url"],
                "mimeType": "application/pdf",
                "isPrimary": True,
            },
            {
                "id": random_id(),
                "title": "Snapshot",
                "url": meta["abs_url"],
                "mimeType": "text/html",
            },
        ],
    }
    if collection_key:
        item["collections"] = [collection_key]
    return item


def save_items_via_connector(items: list[dict[str, Any]], uri: str) -> Any:
    return connector(
        "/connector/saveItems",
        {
            "sessionID": random_id(12),
            "uri": uri,
            "items": items,
        },
    )


def best_item(title: str, collection: str | None) -> dict[str, Any]:
    coll = resolve_collection(collection) if collection else None
    key = coll["key"] if coll else None
    rows = search_items(title, key)
    if not rows:
        where = f" in {collection}" if collection else ""
        fail(f"No matching Zotero item found{where}: {title}")
    return rows[0]


def best_item_from_db(title: str) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{ZOTERO_DB}?immutable=1", uri=True)
    try:
        rows = conn.execute(
            """
            SELECT i.key, idv.value
            FROM items i
            JOIN itemData id ON id.itemID = i.itemID AND id.fieldID = 1
            JOIN itemDataValues idv ON idv.valueID = id.valueID
            LEFT JOIN itemAttachments ia ON ia.itemID = i.itemID
            WHERE ia.itemID IS NULL
            """
        ).fetchall()
    finally:
        conn.close()
    matches = [{"key": key, "data": {"title": value}} for key, value in rows if title_match(value, title)]
    if not matches:
        fail(f"No matching Zotero item found in local database: {title}")
    if len(matches) > 1:
        titles = ", ".join(row["data"]["title"] for row in matches[:5])
        fail(f"Ambiguous Zotero item title in local database: {title}. Matches: {titles}")
    return matches[0]


def child_attachments(item_key: str) -> list[dict[str, Any]]:
    rows = zotero_api(f"{LOCAL_USER}/items/{urllib.parse.quote(item_key)}/children")
    return [r for r in rows if r.get("data", {}).get("itemType") == "attachment"]


def child_attachments_from_db(item_key: str) -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{ZOTERO_DB}?immutable=1", uri=True)
    try:
        rows = conn.execute(
            """
            SELECT child.key, childTitle.value, ia.contentType, ia.path
            FROM items parent
            JOIN itemAttachments ia ON ia.parentItemID = parent.itemID
            JOIN items child ON child.itemID = ia.itemID
            LEFT JOIN itemData childData ON childData.itemID = child.itemID AND childData.fieldID = 1
            LEFT JOIN itemDataValues childTitle ON childTitle.valueID = childData.valueID
            WHERE parent.key = ?
            ORDER BY child.itemID
            """,
            (item_key,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "key": key,
            "data": {
                "itemType": "attachment",
                "title": title,
                "contentType": content_type,
                "_dbPath": path,
            },
        }
        for key, title, content_type, path in rows
    ]


def file_path_for_attachment(attachment_key: str) -> Path | None:
    try:
        url = zotero_api(f"{LOCAL_USER}/items/{urllib.parse.quote(attachment_key)}/file/view/url")
    except Exception:
        return None
    if isinstance(url, str) and url.startswith("file://"):
        return Path(urllib.parse.unquote(urllib.parse.urlparse(url).path))
    return None


def pdf_attachment(item_key: str) -> tuple[dict[str, Any], Path]:
    candidates = []
    for att in child_attachments(item_key):
        data = att.get("data", {})
        title = data.get("title", "")
        title_key = norm_title(title)
        if "pdf" not in (data.get("contentType") or "").lower() and not title.lower().endswith(".pdf"):
            continue
        if any(marker in title_key for marker in ("pdf2zh", "dual", "mono", "translated")):
            continue
        path = file_path_for_attachment(att["key"])
        if path and path.exists():
            candidates.append((att, path))
    if not candidates:
        fail("No local PDF attachment is available yet. Wait for Zotero attachment sync/download.")
    candidates.sort(key=lambda pair: 0 if title_match(pair[0].get("data", {}).get("title"), "Preprint PDF") else 1)
    return candidates[0]


def open_zotero_db() -> sqlite3.Connection:
    conn = sqlite3.connect(ZOTERO_DB, timeout=2)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 2000")
    return conn


def backup_zotero_db() -> Path:
    backup = ZOTERO_DB.with_name(f"zotero.sqlite.codex-backup-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(ZOTERO_DB, backup)
    return backup


def quit_zotero_and_wait(timeout: int = 20) -> bool:
    subprocess.run(["osascript", "-e", 'tell application "Zotero" to quit'], check=False)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            conn = sqlite3.connect(ZOTERO_DB, timeout=1)
            conn.execute("BEGIN IMMEDIATE")
            conn.rollback()
            conn.close()
            return True
        except sqlite3.OperationalError:
            time.sleep(0.5)
    return False


def open_zotero() -> None:
    subprocess.run(["open", "-a", ZOTERO_APP_NAME], check=False)


def translated_attachment_exists(conn: sqlite3.Connection, parent_key: str, title: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT child.key, ia.path, idv.value
        FROM items parent
        JOIN itemAttachments ia ON ia.parentItemID = parent.itemID
        JOIN items child ON child.itemID = ia.itemID
        LEFT JOIN itemData id ON id.itemID = child.itemID AND id.fieldID = 1
        LEFT JOIN itemDataValues idv ON idv.valueID = id.valueID
        WHERE parent.key = ? AND ia.contentType = 'application/pdf'
        """,
        (parent_key,),
    ).fetchall()
    for key, path, value in row:
        if title_match(value, title):
            return {"key": key, "path": path, "title": value}
    return None


def unique_zotero_key(conn: sqlite3.Connection) -> str:
    for _ in range(100):
        key = random_id()
        exists = conn.execute("SELECT 1 FROM items WHERE key = ?", (key,)).fetchone()
        if not exists and not (ZOTERO_STORAGE / key).exists():
            return key
    fail("Could not generate a unique Zotero attachment key.")


def attach_pdf_to_zotero_item(item_key: str, pdf: Path, title: str, *, auto_close_zotero: bool = False) -> dict[str, Any]:
    if not pdf.exists():
        fail(f"Translated PDF does not exist: {pdf}")
    try:
        conn = open_zotero_db()
    except sqlite3.OperationalError as exc:
        if auto_close_zotero and "locked" in str(exc).casefold():
            if not quit_zotero_and_wait():
                fail("Could not close Zotero or release the database lock.")
            try:
                result = attach_pdf_to_zotero_item(item_key, pdf, title, auto_close_zotero=False)
                result["zotero_restarted"] = True
                return result
            finally:
                open_zotero()
        fail(f"Could not open Zotero database for writing: {exc}. Close Zotero and retry.")
    try:
        parent = conn.execute(
            "SELECT itemID, libraryID FROM items WHERE key = ?",
            (item_key,),
        ).fetchone()
        if not parent:
            fail(f"No Zotero item found for key: {item_key}")
        parent_item_id, library_id = parent
        existing = translated_attachment_exists(conn, item_key, title)
        if existing:
            return {"status": "exists", **existing}

        backup = backup_zotero_db()
        attachment_key = unique_zotero_key(conn)
        filename = safe_pdf_filename(title)
        dest_dir = ZOTERO_STORAGE / attachment_key
        dest_dir.mkdir(parents=True, exist_ok=False)
        dest = dest_dir / filename
        shutil.copy2(pdf, dest)

        now = int(time.time())
        modtime = storage_mtime_ms(dest)
        digest = file_md5(dest)
        with conn:
            conn.execute(
                """
                INSERT INTO items
                    (itemTypeID, dateAdded, dateModified, clientDateModified, libraryID, key, version, synced)
                VALUES
                    ((SELECT itemTypeID FROM itemTypes WHERE typeName = 'attachment'),
                     datetime(?, 'unixepoch'), datetime(?, 'unixepoch'), datetime(?, 'unixepoch'),
                     ?, ?, 0, 0)
                """,
                (now, now, now, library_id, attachment_key),
            )
            attachment_item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                """
                INSERT INTO itemAttachments
                    (itemID, parentItemID, linkMode, contentType, path, syncState, storageModTime, storageHash)
                VALUES
                    (?, ?, 0, 'application/pdf', ?, 0, ?, ?)
                """,
                (attachment_item_id, parent_item_id, f"storage:{filename}", modtime, digest),
            )
            conn.execute("INSERT OR IGNORE INTO itemDataValues(value) VALUES (?)", (title,))
            value_id = conn.execute("SELECT valueID FROM itemDataValues WHERE value = ?", (title,)).fetchone()[0]
            conn.execute(
                "INSERT INTO itemData(itemID, fieldID, valueID) VALUES (?, 1, ?)",
                (attachment_item_id, value_id),
            )
        return {
            "status": "attached",
            "key": attachment_key,
            "title": title,
            "path": str(dest),
            "backup": str(backup),
        }
    except sqlite3.OperationalError as exc:
        if auto_close_zotero and "locked" in str(exc).casefold():
            if not quit_zotero_and_wait():
                fail("Could not close Zotero or release the database lock.")
            try:
                result = attach_pdf_to_zotero_item(item_key, pdf, title, auto_close_zotero=False)
                result["zotero_restarted"] = True
                return result
            finally:
                open_zotero()
        fail(f"Could not write Zotero database: {exc}. Close Zotero and retry.")
    finally:
        conn.close()


def cmd_status(args: argparse.Namespace) -> None:
    payload: dict[str, Any] = {
        "zotero_api": health(ZOTERO + "/api/"),
        "zotero_connector": health(ZOTERO + "/connector/ping"),
        "pdf2zh": health(PDF2ZH + "/health"),
        "configured_paths": {
            "zotero_base_url": ZOTERO,
            "pdf2zh_base_url": PDF2ZH,
            "pdf2zh_server_dir": str(PDF2ZH_SERVER_DIR),
            "pdf2zh_translated_dir": str(TRANSLATED_DIR),
            "zotero_data_dir": str(ZOTERO_DIR),
            "zotero_app_name": ZOTERO_APP_NAME,
        },
        "selected_target": selected_target(),
    }
    if args.collection:
        coll = resolve_collection(args.collection)
        payload["requested_collection"] = {
            "path": args.collection,
            "exists": bool(coll),
            "key": coll.get("key") if coll else None,
            "actual_path": coll.get("_path") if coll else None,
        }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def cmd_wait_item(args: argparse.Namespace) -> None:
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        try:
            item = best_item(args.title, args.collection)
            data = item.get("data", item)
            print(json.dumps({"found": True, "key": item["key"], "title": data.get("title")}, indent=2, ensure_ascii=False))
            return
        except SystemExit:
            time.sleep(args.interval)
    fail(f"Timed out waiting for Zotero item: {args.title}")


def cmd_attachments(args: argparse.Namespace) -> None:
    from_db = False
    try:
        item = best_item(args.title, args.collection)
        attachments = child_attachments(item["key"])
    except Exception:
        item = best_item_from_db(args.title)
        attachments = child_attachments_from_db(item["key"])
        from_db = True
    rows = []
    for att in attachments:
        data = att.get("data", {})
        if from_db:
            raw_path = data.get("_dbPath")
            if raw_path and raw_path.startswith("storage:"):
                path = ZOTERO_STORAGE / att["key"] / raw_path.removeprefix("storage:")
            else:
                path = Path(raw_path) if raw_path else None
        else:
            path = file_path_for_attachment(att["key"])
        rows.append(
            {
                "key": att["key"],
                "title": data.get("title"),
                "contentType": data.get("contentType"),
                "path": str(path) if path else None,
                "exists": bool(path and path.exists()),
            }
        )
    print(json.dumps(rows, indent=2, ensure_ascii=False))


def cmd_save_arxiv(args: argparse.Namespace) -> None:
    if not args.arxiv_id and not args.url_or_id:
        fail("Provide an arXiv URL/id or --arxiv-id.")
    arxiv_id = args.arxiv_id or arxiv_id_from_text(args.url_or_id)
    coll = resolve_collection(args.collection) if args.collection else None
    target_path = selected_target_path(selected_target())
    if args.collection and norm(target_path) != norm(args.collection):
        fail(f"Selected Zotero target is {target_path!r}, not {args.collection!r}. Select the requested collection in Zotero first.")
    meta = fetch_arxiv_metadata(arxiv_id)
    title = args.title or meta["title"]
    existing = search_items(title, coll["key"] if coll else None)
    if existing:
        item = existing[0]
        data = item.get("data", item)
        print(json.dumps({"status": "exists", "key": item["key"], "title": data.get("title")}, indent=2, ensure_ascii=False))
        return

    item = zotero_item_from_arxiv(meta, coll["key"] if coll else None)
    response = save_items_via_connector([item], meta["abs_url"])
    deadline = time.time() + args.timeout
    found = None
    has_pdf = False
    while time.time() < deadline:
        rows = search_items(title, coll["key"] if coll else None)
        if rows:
            found = rows[0]
            try:
                pdf_attachment(found["key"])
                has_pdf = True
                break
            except SystemExit:
                pass
        time.sleep(args.interval)
    if not found:
        fail(f"Timed out waiting for Zotero item after connector save: {title}")
    data = found.get("data", found)
    attachments = []
    for att in child_attachments(found["key"]):
        att_data = att.get("data", {})
        path = file_path_for_attachment(att["key"])
        attachments.append(
            {
                "key": att["key"],
                "title": att_data.get("title"),
                "contentType": att_data.get("contentType"),
                "path": str(path) if path else None,
                "exists": bool(path and path.exists()),
            }
        )
    print(
        json.dumps(
            {
                "status": "saved",
                "key": found["key"],
                "title": data.get("title"),
                "pdf_available": has_pdf,
                "connector_response": response,
                "attachments": attachments,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def cmd_attach_translated(args: argparse.Namespace) -> None:
    try:
        item = best_item(args.title, args.collection)
    except Exception:
        item = best_item_from_db(args.title)
    pdf = Path(args.pdf)
    attachment_title = args.attachment_title or translated_title_for_path(pdf)
    result = attach_pdf_to_zotero_item(
        item["key"],
        pdf,
        attachment_title,
        auto_close_zotero=args.auto_close_zotero,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


def cmd_translate(args: argparse.Namespace) -> None:
    item = best_item(args.title, args.collection)
    _att, pdf = pdf_attachment(item["key"])
    content = base64.b64encode(pdf.read_bytes()).decode("ascii")
    payload = {
        "fileName": pdf.name,
        "fileContent": "data:application/pdf;base64," + content,
        "engine": args.engine,
        "service": args.service,
        "sourceLang": "en",
        "targetLang": "zh-CN",
        "mono": True,
        "dual": True,
        "noWatermark": True,
        "noDual": False,
        "noMono": False,
    }
    result = request_json(PDF2ZH + "/translate", method="POST", payload=payload, timeout=args.timeout)
    files = []
    if isinstance(result, dict):
        for name in result.get("fileList") or []:
            path = TRANSLATED_DIR / name
            files.append({"name": name, "path": str(path), "exists": path.exists()})
    attached = []
    attach_errors = []
    if not args.no_attach:
        for file_info in files:
            if not file_info["exists"]:
                continue
            try:
                attachment_title = args.attachment_title or translated_title_for_path(Path(file_info["path"]))
                attached.append(
                    attach_pdf_to_zotero_item(
                        item["key"],
                        Path(file_info["path"]),
                        attachment_title,
                        auto_close_zotero=args.auto_close_zotero,
                    )
                )
            except SystemExit as exc:
                attach_errors.append(str(exc))
    print(
        json.dumps(
            {
                "source_pdf": str(pdf),
                "response": result,
                "files": files,
                "attached": attached,
                "attach_errors": attach_errors,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status")
    status.add_argument("--collection")
    status.set_defaults(func=cmd_status)

    wait = sub.add_parser("wait-item")
    wait.add_argument("--title", required=True)
    wait.add_argument("--collection")
    wait.add_argument("--timeout", type=int, default=180)
    wait.add_argument("--interval", type=float, default=3)
    wait.set_defaults(func=cmd_wait_item)

    attachments = sub.add_parser("attachments")
    attachments.add_argument("--title", required=True)
    attachments.add_argument("--collection")
    attachments.set_defaults(func=cmd_attachments)

    save_arxiv = sub.add_parser("save-arxiv")
    save_arxiv.add_argument("url_or_id", nargs="?")
    save_arxiv.add_argument("--arxiv-id")
    save_arxiv.add_argument("--title")
    save_arxiv.add_argument("--collection")
    save_arxiv.add_argument("--timeout", type=int, default=180)
    save_arxiv.add_argument("--interval", type=float, default=3)
    save_arxiv.set_defaults(func=cmd_save_arxiv)

    attach_translated = sub.add_parser("attach-translated")
    attach_translated.add_argument("--title", required=True)
    attach_translated.add_argument("--collection")
    attach_translated.add_argument("--pdf", required=True)
    attach_translated.add_argument("--attachment-title")
    attach_translated.add_argument("--auto-close-zotero", action="store_true")
    attach_translated.set_defaults(func=cmd_attach_translated)

    translate = sub.add_parser("translate")
    translate.add_argument("--title", required=True)
    translate.add_argument("--collection")
    translate.add_argument("--engine", default="pdf2zh_next")
    translate.add_argument("--service", default="bing")
    translate.add_argument("--timeout", type=int, default=1800)
    translate.add_argument("--attachment-title")
    translate.add_argument("--no-attach", action="store_true")
    translate.add_argument("--auto-close-zotero", action="store_true")
    translate.set_defaults(func=cmd_translate)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
