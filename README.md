# Zotero Codex Skills

Two portable Codex skills for Zotero research workflows:

- `zotero-arxiv-pdf2zh`: save arXiv papers into a chosen Zotero collection and translate attached PDFs through a local `zotero-pdf2zh` server.
- `zotero-venue-metadata`: verify journal or conference metadata online and update the matching Zotero item through Zotero's local API.

## Install

Clone the repository and copy the skill directories into your Codex skills directory:

```bash
git clone https://github.com/Berumotto-mk/zotero-codex-skills.git
mkdir -p ~/.codex/skills
cp -R zotero-codex-skills/zotero-arxiv-pdf2zh ~/.codex/skills/
cp -R zotero-codex-skills/zotero-venue-metadata ~/.codex/skills/
```

Restart Codex after installation.

## Requirements

- Zotero Desktop with its local API and Connector available at `http://127.0.0.1:23119`.
- Python 3.
- `zotero-arxiv-pdf2zh` additionally expects a local `zotero-pdf2zh` server, normally at `http://127.0.0.1:8890`.

See each directory's `SKILL.md` for configuration, workflow, and helper commands.

## Repository layout

```text
zotero-codex-skills/
├── zotero-arxiv-pdf2zh/
│   ├── SKILL.md
│   ├── agents/
│   ├── references/
│   └── scripts/
└── zotero-venue-metadata/
    ├── SKILL.md
    ├── agents/
    ├── references/
    └── scripts/
```

The repository contains skill definitions and helper source code only. It does not include Zotero databases, PDFs, API keys, or translated documents.
