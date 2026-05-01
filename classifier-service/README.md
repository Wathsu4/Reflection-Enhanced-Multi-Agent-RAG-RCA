# classifier-service

FastAPI service that wraps the fine-tuned ModernBERT log-severity classifier.

## Endpoints

| Method | Path             | Purpose                                                         |
| ------ | ---------------- | --------------------------------------------------------------- |
| POST   | `/classify`      | Classify a log chunk into one of 4 severity buckets             |
| POST   | `/generate-logs` | Produce a synthetic log chunk for the simulator demo            |
| GET    | `/health`        | Liveness + model-load + device info                             |
| GET    | `/docs`          | Auto-generated Swagger UI                                       |

Default port: `8001`. See `§7` of `PROJECT_IMPLEMENTATION_GUIDE.md` for full
request/response shapes.

## Prerequisites

- Python ≥ 3.11
- The fine-tuned model directory dropped at `models/modernbert-log-severity-v1/`
  (this directory is gitignored — download from your training-notebook output).
  It must contain `config.json`, `model.safetensors` (or `pytorch_model.bin`),
  `tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`, and
  `training_metadata.json`.

## Install

Pick one. `uv` is much faster.

```bash
# Option A — uv (recommended)
uv sync

# Option B — plain pip in a venv
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Configure

```bash
cp .env.example .env
# Edit if needed; defaults work for local dev.
```

Key vars (all prefixed `CLASSIFIER_`):

| Var                | Default                                          | Notes                          |
| ------------------ | ------------------------------------------------ | ------------------------------ |
| `MODEL_PATH`       | `./models/modernbert-log-severity-v1`            | Folder containing the model    |
| `DEVICE`           | `auto`                                           | `auto` / `cpu` / `cuda` / `mps` |
| `PORT`             | `8001`                                           |                                |
| `CORS_ORIGINS`     | `http://localhost:3000`                          | Comma-separated list           |
| `MAX_CHUNK_BYTES`  | `500000`                                         | Reject larger payloads         |

## Run

```bash
# uv
uv run uvicorn app.main:app --port 8001 --reload

# plain venv
uvicorn app.main:app --port 8001 --reload
```

Open Swagger at <http://localhost:8001/docs>.

## Test

```bash
# Fast tests that don't need the trained model:
uv run pytest tests/test_log_generator.py

# Full HTTP smoke tests (require model on disk):
uv run pytest

# Skip model-dependent tests explicitly:
CLASSIFIER_SKIP_MODEL_TESTS=1 uv run pytest
```

## Troubleshooting

- **`FileNotFoundError: training_metadata.json not found`** — the model
  directory at `CLASSIFIER_MODEL_PATH` is missing or incomplete. Re-download
  the full output of the training notebook.
- **`torch.cuda.is_available()` returns False on a GPU machine** — your
  `torch` was installed without CUDA support. Reinstall the matching
  CUDA-enabled wheel from <https://pytorch.org/get-started/locally/>.
- **First-request latency spikes** — the constructor runs a one-shot warmup
  call to mitigate this. If you still see ~1s on the first real request,
  the warmup likely failed silently; check the startup logs.
- **CORS errors in the browser** — verify `CLASSIFIER_CORS_ORIGINS` includes
  `http://localhost:3000` and restart the service after editing `.env`.
- **Slow / huge install on Apple Silicon** — `torch` wheels for Apple are
  large (~200 MB). MPS (`CLASSIFIER_DEVICE=mps`) gives a ~2-3x speedup over
  CPU on M-series chips.

