# Paper corpus

The corpus checks extraction and figure selection against real papers. It covers layouts that synthetic PDFs miss, and it runs locally because the PDFs are not redistributable.

- `evals/papers/` holds the PDFs and is ignored by Git.
- `evals/expectations/` holds one JSON file for each paper and is committed.

Each file records the PDF's SHA-256 and manually verified facts. It stores only the first and last words of a caption, not its full text.

## Run it

```sh
python3 -m pytest -q -m corpus
```

The default test run excludes the corpus, so CI needs no PDFs. A check is skipped when its PDF is missing locally and fails when the PDF's hash differs. The run takes about a minute and uses no network: it starts after PDF acquisition, with a constructed fetch result.

The test header prints the PyMuPDF version. Text block boundaries can change between versions, so check the version before treating a new failure as a regression.

## Add a paper

1. Copy the PDF to `evals/papers/`.
2. Create `evals/expectations/<paper>.json` with these fields:

| Field | Content |
| --- | --- |
| `schema_version` | `1` |
| `pdf` | The filename in `evals/papers/` |
| `sha256` | The PDF's SHA-256 |
| `split` | `dev` or `holdout` |
| `source` | The DOI, arXiv ID, or citation |
| `traits` | The layout features this paper covers |
| `labels` | Every real figure and table label, in normalized form |
| `captions` | For selected labels, the `starts` and `ends` of the true caption |
| `review` | Labels that must reach Visual Review, such as main results |
| `same_visual` | Label pairs that describe one visual |
| `known_gaps` | Check patterns mapped to the reason each one fails today |

Read expected values from the paper, not from the current output. Otherwise a snapshot would record existing bugs as correct behavior.

## Known gaps

A check matching `known_gaps` is a strict expected failure. When a fix makes it pass, the run fails until you remove the gap, so fixes are always recorded. Patterns use shell-style wildcards against the check IDs shown in the test names.

## Held-out papers

Heuristics can overfit papers they are tuned against. Keep some papers as `holdout`, and run them once before merging a change to extraction or selection:

```sh
python3 -m pytest -q -m corpus_holdout
```

If a held-out paper fails, move it to `dev`, fix the problem, and add a new paper to `holdout`. Every paper in the first batch was inspected while building the corpus, so all of them are `dev`. Only papers not yet used for tuning belong in `holdout`.
