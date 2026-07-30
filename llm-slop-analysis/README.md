# llm-slop-analysis

Everything in this directory was written by an LLM. It is kept apart from
`docs/` on purpose.

We all drive coding agents continuously. If model-written notes sit next to
official documentation, the next model cannot tell them apart, and one model's
guess becomes the next model's "documentation" — a telephone effect that gets
worse every pass. So:

- **`docs/` holds original sources only.** Verbatim capture of the official
  site. Never add a summary of it there.
- **Everything an LLM wrote lives here**, under the folder of whoever ran it.
- **Nothing here is authoritative.** These are claims. The running engine
  outranks all of it, then the spec shipped in the engine wheel
  (`.venv/…/fcode/data/docs/spec.md`), then the scraped official docs.

## Folders

| Folder | Branch | Contents |
|---|---|---|
| [`jon/`](jon/) | `x/jon` | Competitor research, engine mechanics audit, opening-economy analysis, file-format reverse engineering |
| [`lucas/`](lucas/) | `x/luc` | — |
| [`vaek/`](vaek/) | `viktor` | — |
| [`elias/`](elias/) | `x/llm-RL` | — |

## Writing notes here

State how each claim was established — measured against the engine, read from
the official docs, or inferred — and keep the three visibly distinct. Prefer a
reproducible probe over prose.

Do not cite a document in this directory as evidence for a new document in this
directory. Go back to the engine.

When a note turns out to be wrong, correct it in place and say what changed;
do not leave a superseded claim sitting there unmarked. See
[`jon/strategy/opening-economy-revision.md`](jon/strategy/opening-economy-revision.md)
for the pattern.
