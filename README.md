# Lead Pipeline Dashboard

Local, single-user Streamlit console for running lead-generation pipelines. Pipelines are YAML configs (plus optional custom Python steps). The first one, `vfx_genai`, finds decision-makers at production companies using generative AI in client work.

**Status: phase 1 of 8 (skeleton).** Config validation, SQLite schema, registry, Settings, Pipelines view. No jobs, paid calls or sheet access yet.

## Setup (Windows)

```
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pip install -e .
copy .env.example .env      # then fill it in; .env is git-ignored
```

## Run

```
.\.venv\Scripts\python -m streamlit run app/Home.py
.\.venv\Scripts\python -m pytest
```

## Layout

- `core/config.py`: pydantic models for `pipeline.yaml`
- `core/db.py`: SQLite (WAL) schema and migrations
- `core/registry.py`: discovers pipelines; a broken YAML shows an error card instead of crashing
- `core/logmask.py`: masks API keys in logs
- `pipelines/vfx_genai/`: config, SOPs and manager overrides
- `app/`: Streamlit pages

Later sections ("Run your first VFX cycle", "Add a new pipeline") are added in phase 8.
