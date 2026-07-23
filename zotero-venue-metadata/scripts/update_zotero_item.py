#!/usr/bin/env python3
"""Patch one Zotero local API item with confirmed venue metadata."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


BASE_URL = "http://127.0.0.1:23119/api/users/0"

ITEM_TYPE_FIELDS = {
    "conferencePaper": {
        "itemType",
        "title",
        "creators",
        "abstractNote",
        "conferenceName",
        "proceedingsTitle",
        "date",
        "place",
        "publisher",
        "pages",
        "DOI",
        "ISBN",
        "url",
        "shortTitle",
        "language",
        "extra",
        "tags",
        "collections",
        "relations",
    },
    "journalArticle": {
        "itemType",
        "title",
        "creators",
        "abstractNote",
        "publicationTitle",
        "journalAbbreviation",
        "volume",
        "issue",
        "pages",
        "date",
        "DOI",
        "ISSN",
        "url",
        "shortTitle",
        "language",
        "extra",
        "tags",
        "collections",
        "relations",
    },
}

DROP_WHEN_RETYPE = {
    "websiteTitle",
    "websiteType",
    "accessDate",
    "archive",
    "archiveLocation",
}


def request_json(method: str, path: str, payload: dict | None = None, version: int | None = None) -> tuple[dict, dict]:
    data = None
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Zotero-API-Version": "3",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if version is not None:
        headers["If-Unmodified-Since-Version"] = str(version)
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            return (json.loads(body) if body else {}, dict(resp.headers))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Zotero API {method} {path} failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not reach Zotero local API at {BASE_URL}: {exc}") from exc


def changed_fields(before: dict, after: dict) -> dict:
    changes = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changes[key] = {"before": before.get(key), "after": after.get(key)}
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--item-key", required=True, help="Zotero item key, not a BibTeX key")
    parser.add_argument("--patch", required=True, help="JSON object of Zotero data fields to update")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    args = parser.parse_args()

    with open(args.patch, "r", encoding="utf-8") as handle:
        patch = json.load(handle)
    if not isinstance(patch, dict):
        raise SystemExit("Patch file must contain a JSON object.")

    item, _ = request_json("GET", f"/items/{args.item_key}")
    data = item.get("data", {})
    if not data:
        raise SystemExit(f"Item {args.item_key} was not found or had no data.")

    updated = dict(data)
    target_type = patch.get("itemType", updated.get("itemType"))
    if target_type in ITEM_TYPE_FIELDS and target_type != updated.get("itemType"):
        for field in DROP_WHEN_RETYPE:
            updated.pop(field, None)
        allowed = ITEM_TYPE_FIELDS[target_type]
        for field in list(updated):
            if field not in allowed and field not in {"key", "version"}:
                updated.pop(field, None)

    updated.update(patch)
    changes = changed_fields(data, updated)

    if args.dry_run:
        print(json.dumps({"dry_run": True, "item_key": args.item_key, "changes": changes}, ensure_ascii=False, indent=2))
        return 0

    version = item.get("version") or data.get("version")
    request_json("PUT", f"/items/{args.item_key}", updated, version=version)
    reread, _ = request_json("GET", f"/items/{args.item_key}")
    final_data = reread.get("data", {})
    print(json.dumps({
        "updated": True,
        "item_key": args.item_key,
        "title": final_data.get("title"),
        "itemType": final_data.get("itemType"),
        "changed_fields": sorted(changes),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
