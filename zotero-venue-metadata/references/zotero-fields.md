# Zotero Venue Field Reference

Use these Zotero API field names when patching publication venue metadata.

## conferencePaper

- `title`
- `creators`
- `conferenceName`
- `proceedingsTitle`
- `date`
- `place`
- `publisher`
- `pages`
- `DOI`
- `ISBN`
- `url`
- `shortTitle`
- `language`
- `extra`

Good `extra` lines:

```text
Status: Accepted to CVPR 2026
arXiv: 2601.22153
Venue source: CVF OpenAccess
```

## journalArticle

- `title`
- `creators`
- `publicationTitle`
- `journalAbbreviation`
- `volume`
- `issue`
- `pages`
- `date`
- `DOI`
- `ISSN`
- `url`
- `shortTitle`
- `language`
- `extra`

## Common Cleanup

When converting a `webpage` or arXiv import, remove or ignore website-only fields if they are no longer appropriate:

- `websiteTitle`
- `websiteType`
- `accessDate`

Do not remove title, authors, date, URL, short title, language, abstract, tags, collections, relations, notes, or attachments.
