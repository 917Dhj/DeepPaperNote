# Paper corpus

The corpus checks extraction and figure selection against real papers. It covers layouts that synthetic PDFs miss, and it runs locally because the PDFs are not redistributable.

- `evals/papers/` holds the PDFs and is ignored by Git.
- `evals/expectations/` holds one JSON file for each paper and is committed.
- `evals/http-cassettes/` holds the provider responses that identity resolution received for each paper, and is committed.

Each file records the PDF's SHA-256 and manually verified facts. It stores only the first and last words of a caption, not its full text.

## Run it

```sh
python3 -m pytest -q -m corpus
```

The default test run excludes the corpus, so CI needs no PDFs. A check is skipped when its PDF is missing locally and fails when the PDF's hash differs. The run takes a few minutes and uses no network.

The `title` check runs identity resolution on the local PDF (`resolve_paper.py`, `collect_metadata.py`, `build_identity_contract.py`) with Zotero off. Every HTTP request is answered from the paper's cassette, so the check fails when a code change sends a request the cassette lacks. The other checks start after PDF acquisition, with a constructed fetch result.

## Record cassettes

Re-record when identity resolution starts sending different requests, or when you add a paper:

```sh
DEEPPAPERNOTE_CORPUS_RECORD=1 python3 -m pytest -q -m corpus -k title
```

Recording reaches the providers and replaces each cassette. It retries rate-limited responses a few times, then stores the error, so a cassette can record a provider as unavailable. Review the cassette diff before committing it: a provider that answered differently this time changes what the check replays.

The test header prints the PyMuPDF version. Text block boundaries can change between versions, so check the version before treating a new failure as a regression.

## Add a paper

1. Copy the PDF to `evals/papers/`.
2. Create `evals/expectations/<paper>.json` with these fields, then record its cassette:

| Field | Content |
| --- | --- |
| `schema_version` | `1` |
| `pdf` | The filename in `evals/papers/` |
| `sha256` | The PDF's SHA-256 |
| `source` | The DOI, arXiv ID, or citation |
| `traits` | The layout features this paper covers |
| `readable` | Whether the text layer can be read; an unreadable paper must stop at source extraction |
| `title` | The paper's title, from its published version when a preprint's title differs; the check ignores case, spacing, ligatures, and full-width forms |
| `labels` | Every real figure and table label, in normalized form |
| `captions` | For selected labels, the `starts` and `ends` of the true caption |
| `review` | Labels that must reach Visual Review, such as main results |
| `crops` | For selected labels, text the crop must contain (`contains`) and must leave out (`excludes`) |
| `same_visual` | Label pairs that describe one visual |
| `known_gaps` | Check patterns mapped to the reason each one fails today |

Read expected values from the paper, not from the current output. Otherwise a snapshot would record existing bugs as correct behavior.

## Known gaps

A check matching `known_gaps` is a strict expected failure. When a fix makes it pass, the run fails until you remove the gap, so fixes are always recorded. Patterns use shell-style wildcards against the check IDs shown in the test names.
