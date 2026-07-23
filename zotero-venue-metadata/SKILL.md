---
name: zotero-venue-metadata
description: Verify a paper's journal, conference, proceedings, acceptance status, DOI, pages, and related publication venue metadata online, then update the matching Zotero Desktop item through Zotero's local API. Use when the user asks to fix or fill Zotero fields for arXiv papers, accepted papers, conference papers, journal articles, proceedings entries, screenshots of Zotero items, or requests like "make this Zotero item show it is CVPR/ICLR/Nature/etc.".
---

# Zotero Venue Metadata

Use this skill to turn incomplete Zotero paper records, especially arXiv-imported `webpage` items, into clear publication records whose Zotero fields show the confirmed journal or conference venue.

## Workflow

1. Identify the Zotero item.
   - If the user names a paper, search the local Zotero library.
   - If the user says "this item" or shows a Zotero screenshot, use the selected Zotero item when possible; otherwise search by title.
   - Do not edit PDF attachment child items. Edit the parent bibliographic item.

2. Confirm venue metadata online before writing.
   - Browse the web. Prefer official sources: publisher pages, conference proceedings pages, OpenReview, CVF/OpenAccess, ACM/IEEE/Springer pages, journal pages, DOI landing pages, or the paper's official project page when it links to the venue.
   - Use arXiv only for title/authors/abstract/version unless it explicitly states the venue.
   - If sources conflict, prefer the official proceedings or publisher page over project pages, lab pages, indexes, or social posts.
   - If the venue cannot be confirmed, do not invent it. Write only confirmed fields and explain the unresolved field.

3. Choose the Zotero item type.
   - Use `conferencePaper` for accepted or published conference papers.
   - Use `journalArticle` for journal papers.
   - Keep `preprint` or `webpage` only when no venue is confirmed.

4. Build a field patch using Zotero field names.
   - For conference papers:
     - `itemType`: `conferencePaper`
     - `conferenceName`: short venue name and year when helpful, e.g. `CVPR 2026`
     - `proceedingsTitle`: official proceedings title, e.g. `Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition`
     - `date`: publication year or full official date
     - `publisher`: official publisher/sponsor if known, e.g. `IEEE/CVF`
     - `place`: conference location only if confirmed
     - `pages`: proceedings pages only if confirmed
     - `DOI`: only if confirmed
     - `url`: prefer the official proceedings/publisher URL after publication; keep arXiv URL only if no better official URL exists
     - `extra`: include compact status/provenance notes, such as `Status: Accepted to CVPR 2026`
   - For journal articles:
     - `itemType`: `journalArticle`
     - `publicationTitle`: full journal title
     - `journalAbbreviation`: official abbreviation if known
     - `volume`, `issue`, `pages`, `date`, `DOI`, `url`: fill only confirmed values
     - `extra`: include compact status/provenance notes when useful

5. Apply the update through Zotero's local API.
   - First confirm the local API is available. If the Zotero skill helper is available, use its `status --json` route.
   - Use `scripts/update_zotero_item.py` from this skill to write a JSON patch to one item key.
   - After updating, re-read the item and report the final item type plus changed fields.

## Update Script

Write a patch JSON file, then run:

```bash
python3 <skill-dir>/scripts/update_zotero_item.py --item-key ITEMKEY --patch patch.json
```

Patch example:

```json
{
  "itemType": "conferencePaper",
  "conferenceName": "CVPR 2026",
  "proceedingsTitle": "Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition",
  "date": "2026",
  "publisher": "IEEE/CVF",
  "url": "https://arxiv.org/abs/2601.22153",
  "extra": "Status: Accepted to CVPR 2026"
}
```

Use `--dry-run` before a risky update or when the item match is uncertain.

## Reporting

Keep the user-facing report short and concrete:

- Say which sources confirmed the venue.
- Say which Zotero item was edited: title and Zotero item key.
- List changed fields and any fields intentionally left blank because they were not confirmed.

Never present a guessed conference/journal as confirmed. If the user explicitly wants unverified notes, put them in `extra` as `Unverified note:` rather than bibliographic fields.
