# metagen

A Textual TUI that profiles a local CSV / Excel / Parquet file and writes a
versioned **semantic catalog** (JSON + Markdown) — grounding context for Gen AI
apps that answer questions over your data.

- Every claim is **source-tagged** (`computed | llm | user`) with confidence
- Output is JSON (canonical, schema-validated) **and** Markdown (rendered, GitHub-friendly)
- LLM provider is auto-picked: Claude or OpenAI from your `.env`
- Optional **user context** flows directly into LLM prompts so descriptions are written *with* domain knowledge
- Detects each table's **grain** (what does one row represent?) — natural key from stats, plain English from the LLM

## Install & run

```bash
uv sync                          # installs everything (Claude + OpenAI included)
uv run metagen               # launch the TUI
```

Drop your API key into `.env` next to where you run the command:

```bash
ANTHROPIC_API_KEY=sk-ant-…
# or
OPENAI_API_KEY=sk-…
```

## What it does

The TUI walks you through six steps:

1. **Source** — point at a CSV, Excel, or Parquet file (or a directory of them)
2. **Context** *(optional)* — type anything the LLM should know: domain, period, conventions, gotchas
3. **Tables** — multi-select which tables / sheets to include (default: all)
4. **Output** — pick what to put in the catalog (table descriptions, column descriptions, statistics, dataset grain, relationships, quality grades), choose JSON / Markdown / Both, set the output directory (defaults to `<your-data-folder>/catalog`)
5. **Run** — pipeline runs in the background with live progress
6. **Done** — paths to the files you just wrote

There's a **"Try sample data"** button on the Welcome screen if you want to see the output before pointing at your own data.

## What you get

- `catalog/catalog.json` — canonical, schema-validated, every field source-tagged
- `catalog/CATALOG.md` — human-readable index with Mermaid ERD
- `catalog/tables/<name>.md` — per-table page (multi layout)
- `catalog/quality.md` — cross-table quality summary

## Provenance

Every value in the catalog is tagged with its source — so a downstream LLM
(or human) can tell which claims are verifiable from the data and which are
inferred:

- `[computed]` — derived from the data itself (stats, null counts, natural keys, FK candidates)
- `[llm · 0.85]` — written by the LLM, with confidence between 0 and 1
- `[user]` — from the context or glossary you provided

The convention is also rendered as a callout at the top of every `CATALOG.md`.

## Keyboard

- **Tab / Shift+Tab** — move focus
- **Enter** — primary action ("Continue" / "Run" / "Quit")
- **Esc** — back one screen
- **Ctrl+C** — quit (also Ctrl+Q, Ctrl+D)

Or just click the buttons — every screen has them.

## Testing

```bash
uv run pytest                    # full suite, LLM always mocked
uv run ruff check . && ruff format .
uv run mypy src/metagen/
```

See `claude_code_docs/product_plan.md` for architecture and the output
contract, and `claude_code_docs/TUI_DESIGN.md` for the TUI design.

## v1 limitations

- **Composite foreign keys are not detected.** Relationship inference matches on a single column only — multi-column FKs (e.g. bridge / junction tables, `(date, store_id)` keys) are skipped. Single-column natural keys + composite *natural* keys (within a table) are detected; only cross-table composite FKs are out of scope. Coming in a later release.
- Local files only (CSV, Excel, Parquet). Database / warehouse connectors deferred.

## License

MIT
