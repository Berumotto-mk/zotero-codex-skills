# pdf2zh Request Notes

The local server in `$PDF2ZH_SERVER_DIR/server.py` accepts `POST /translate` JSON. `$PDF2ZH_SERVER_DIR` defaults to `~/Documents/zotero-pdf2zh/server`. The required PDF fields are:

- `fileName`: basename for the uploaded source PDF.
- `fileContent`: base64 PDF data, optionally prefixed with `data:application/pdf;base64,`.

Useful translation defaults:

- `engine`: `pdf2zh_next`
- `service`: `bing` unless the user's configured plugin/server indicates another default.
- `sourceLang`: `en`
- `targetLang`: `zh-CN`
- `dual`: `true`
- `mono`: `true`
- `noWatermark`: `true`
- `noDual`: `false`
- `noMono`: `false`

The response usually includes:

```json
{"status":"success","fileList":["paper.zh-CN.mono.pdf", "paper.zh-CN.dual.pdf"]}
```

Generated files are stored under `$PDF2ZH_TRANSLATED_DIR`, which defaults to `$PDF2ZH_SERVER_DIR/translated`.
