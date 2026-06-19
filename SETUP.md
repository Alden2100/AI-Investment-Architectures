# Setup

Everything runs **keyless** on free data sources and a local model. A Claude API
key is optional and only changes *which* model handles the heavy steps.

## 1. Install Ollama and pull the local model
The systems route cheap/bulk work (and, keyless, all model work) to **qwen3.5:9b**.

```bash
# macOS:  brew install ollama        # or download from https://ollama.com
ollama serve &                       # starts the server on localhost:11434
ollama pull qwen3.5:9b               # ~6.5 GB
# verify:
curl -s http://localhost:11434/api/tags | grep qwen3.5:9b
```

> The model id is pinned to `qwen3.5:9b` throughout. Don't substitute another model
> unless you also set `OLLAMA_MODEL`.

## 2. Python virtual environment + dependencies
```bash
cd "AI Investment Architectures"
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
```
(or just run `./setup.sh`, which does the venv + install.)

## 3. Environment variables (all optional)
```bash
cp .env.example .env
# edit .env — leave it empty to stay fully keyless, or add:
#   ANTHROPIC_API_KEY=...   -> heavy reasoning/synthesis/drafting go to Claude
#   BRAVE_API_KEY=...       -> web-search upgrades from DuckDuckGo to Brave
```
Each orchestrator auto-loads `.env` from the repo root. Secrets live only in `.env`
(git-ignored); nothing is ever hard-coded.

## 4. Materialize the systems
Manifests pin which skills/agents each system uses; `link.py` turns them into
symlinks under each system's `.claude/`:
```bash
./.venv/bin/python link.py            # all systems
./.venv/bin/python link.py --check    # validate manifests vs library (no writes)
```
These symlinks are git-ignored — re-run `link.py` after any clone.

## 5. Run a system
```bash
./.venv/bin/python systems/valuation/orchestrator.py --ticker MSFT --peers AAPL GOOGL
```
First run fetches from SEC/Yahoo and caches to the system's SQLite DB
(`systems/<name>/data/`); later runs are fast and resilient to flaky sources.

## 6. Run the tests
```bash
./.venv/bin/python tests/run_smoke_tests.py            # all full systems
./.venv/bin/python systems/idea-sourcing/tests/smoke_test.py   # just one
```
Tests are keyless and exercise the real pipeline (live free data + qwen).

## Troubleshooting
- **`skill 'X' not found`** → run `python link.py`.
- **Router always says `chosen: local`** → no `ANTHROPIC_API_KEY`; that's the
  keyless fallback. Add the key to `.env` to route heavy steps to Claude.
- **qwen slow / first call hangs** → the model loads into memory on first call;
  subsequent calls are fast.
- **A price/news source is down** → the data layer falls back across sources and
  serves cache; a warm DB keeps runs working offline-ish.
