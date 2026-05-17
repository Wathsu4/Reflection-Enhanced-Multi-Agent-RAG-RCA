# helpful_scripts

Small, dependency-free utilities and notes that are useful around the
project but are not part of the main classifier / agent system.

## `defense_qa.md`

A running practice bank of likely defense / supervisor questions and
rehearsed answers (one "speak it out loud" version + one technical
fallback per question). Append new questions to the bottom of the file
as they come up.

## `visualize_data_and_labels.py`

A standalone Python script (Python 3.9+, stdlib only) that prints and
writes labelled samples from every dataset the log severity classifier
uses.

**What it shows, per dataset:**

- The class taxonomy (`FATAL_OR_CRITICAL`, `ERROR`, `WARNING`, `NORMAL`).
- The label distribution.
- A handful of example records *for each class*, so you can eyeball
  what each label actually looks like.

**Two views are produced for BGL:**

1. **Raw** — reads `BGL.log` directly, applies the same labelling rule
   used in the training notebook (`classify_bgl_line`), then groups
   lines into 30-line chunks and assigns each chunk its worst-severity
   label. This is the view that explains *where the labels come from*.
2. **Processed** — reads the `bgl_train.jsonl` / `bgl_val.jsonl` /
   `bgl_test.jsonl` files (the actual training inputs).

Synthetic data is shown from its processed `*.jsonl` files.

### Running it

From the repo root:

```bash
python helpful_scripts/visualize_data_and_labels.py
```

It auto-discovers data in common locations (`raw_data/`, `processed_data/`,
`synthetic_data/`, and the Colab Drive mount paths used by the
notebook). If nothing is found, it falls back to a tiny inline demo so
the output is never empty.

Explicit paths:

```bash
python helpful_scripts/visualize_data_and_labels.py \
    --bgl-raw            /path/to/BGL.log \
    --bgl-processed-dir  /path/to/processed_data \
    --synthetic-dir      /path/to/synthetic_jsonl_dir \
    --samples-per-class  3 \
    --out                helpful_scripts/samples
```

Useful flags:

| flag | default | meaning |
|---|---|---|
| `--samples-per-class` | `2` | how many labelled examples to print per class |
| `--max-raw-lines` | `200000` | cap on raw BGL.log lines to parse (the full file is ~4.7M lines) |
| `--out` | `helpful_scripts/samples` | where to write `*.md` sample files |

### Output

Console output is a human-readable summary. The script also writes:

```
helpful_scripts/samples/
├── SUMMARY.md
├── bgl_raw_sample.md          # if BGL.log was found
├── bgl_processed_sample.md    # if bgl_*.jsonl was found
├── synthetic_sample.md        # if synthetic *.jsonl was found
└── inline_demo_sample.md      # only if no data was found anywhere
```

Each `*.md` file shows the class distribution and a few labelled
samples per class, ready to drop into slides or a defense write-up.
