"""Custom steps: pipelines/<name>/steps/*.py. Each file imports from core.steps.base, defines a Step subclass and registers it with @register.
Discovery is automatic (at import, and on 'Reload steps'). A broken file never crashes the app or the worker: it becomes an error card
(`broken_steps()`) and any step it managed to register before failing is removed again. Files starting with '_' are ignored.

Custom steps are TRUSTED CODE: they run in the worker process as you, with the same access. The app can't sandbox them. What it does enforce
is the gate: a step whose `kind` is paid, llm or write cannot be started without the confirmation screen, and spend recorded through
`ctx.record_spend` shows up in the ledger. A step that claims kind='free' but spends money elsewhere is its author's bug."""
from __future__ import annotations

import importlib.util
import re
import sys
import traceback
from pathlib import Path

from pydantic import BaseModel

from .. import paths
from . import base
from .base import Step

KINDS = ("free", "paid", "llm", "write")
STEP_ID = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def _problems(step_cls: type) -> list[str]:
    out = []
    if not isinstance(getattr(step_cls, "id", None), str) or not STEP_ID.match(step_cls.id):
        out.append("`id` must be a lowercase slug (letters, digits, underscore)")
    if getattr(step_cls, "kind", None) not in KINDS:
        out.append(f"`kind` must be one of {KINDS}")
    pm = getattr(step_cls, "params_model", None)
    if not (isinstance(pm, type) and issubclass(pm, BaseModel)):
        out.append("`params_model` must be a pydantic BaseModel subclass")
    if step_cls.run is Step.run:
        out.append("`run(self, ctx, params)` is not implemented")
    return out


def load_custom_steps(pipelines_dir: Path | None = None) -> dict[str, str]:
    """Import every pipelines/*/steps/*.py. Returns {file key: error} for the files that failed (also kept in base.broken_steps())."""
    root = Path(pipelines_dir or paths.PIPELINES_DIR)
    errors: dict[str, str] = {}
    if not root.exists():
        return errors
    for f in sorted(root.glob("*/steps/*.py")):
        pipeline = f.parent.parent.name
        if f.name.startswith("_") or pipeline.startswith("_"):
            continue
        key = f"{pipeline}/steps/{f.name}"
        before = dict(base._REGISTRY), dict(base._ORIGIN)
        modname = f"lpd_custom_{pipeline}_{f.stem}"
        base._LOADING[0] = pipeline
        try:
            spec = importlib.util.spec_from_file_location(modname, f)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[modname] = mod
            spec.loader.exec_module(mod)
            new = [i for i in base._REGISTRY if i not in before[0] or base._REGISTRY[i] is not before[0][i]]
            if not new:
                raise ValueError("the file registered no step (decorate a Step subclass with @register)")
            for i in new:
                bad = _problems(type(base._REGISTRY[i]))
                if bad:
                    raise ValueError(f"step '{i}': " + "; ".join(bad))
        except BaseException as e:                                     # noqa: BLE001: a custom file must never take the app down
            base._REGISTRY.clear(); base._REGISTRY.update(before[0])    # undo whatever the failed file managed to register
            base._ORIGIN.clear(); base._ORIGIN.update(before[1])
            sys.modules.pop(modname, None)
            tb = traceback.extract_tb(e.__traceback__)
            where = next((f" (line {t.lineno})" for t in reversed(tb) if str(f) in str(t.filename)), "")
            errors[key] = f"{type(e).__name__}: {e}{where}"
            base._BROKEN[key] = errors[key]
        finally:
            base._LOADING[0] = None
    return errors


def reload_custom_steps(pipelines_dir: Path | None = None) -> dict[str, str]:
    base.unregister_custom()
    return load_custom_steps(pipelines_dir)


STEP_TEMPLATE = '''"""Custom step '{step_id}' for pipeline '{pipeline}'. Edit run(); keep it resumable (checkpoint with ctx.save_checkpoint) if it can take long.
Kinds: 'free' costs nothing, 'paid' spends Apify/Tavily money (use ctx.use_key + ctx.record_spend), 'llm' spends LLM tokens, 'write' touches the sheet."""
from pydantic import BaseModel, ConfigDict, Field

from core.steps.base import CostEstimate, Step, StepContext, StepResult, register


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field("hello", max_length=200)


@register
class {class_name}(Step):
    id = "{step_id}"
    kind = "{kind}"
    title = "{step_id} (custom)"
    params_model = Params

    def estimate_cost(self, ctx, params: Params) -> CostEstimate:
        return CostEstimate(max_usd=0.0)          # paid steps: price x maximum results, so the gate can show it before anything runs

    def run(self, ctx: StepContext, params: Params) -> StepResult:
        ctx.check_cancel()                          # call this between units of work so Cancel is graceful
        ctx.log(f"running {step_id}: {{params.note}}")
        (ctx.workdir / "{step_id}_out.txt").write_text(params.note + "\\n", encoding="utf-8")
        return StepResult(counts={{"done": 1}}, artifacts=["{step_id}_out.txt"], message="ok")
'''


def scaffold_step(pipeline: str, step_id: str, kind: str = "free", pipelines_dir: Path | None = None) -> Path:
    """Write pipelines/<pipeline>/steps/<step_id>.py from the template. Never overwrites."""
    root = Path(pipelines_dir or paths.PIPELINES_DIR)
    if not STEP_ID.match(step_id):
        raise ValueError("step id must be a lowercase slug (letters, digits, underscore)")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if step_id in base._REGISTRY and base.origin_of(step_id) != pipeline:
        raise ValueError(f"step id '{step_id}' is already used by {base.origin_of(step_id)}")
    if not (root / pipeline / "pipeline.yaml").exists():
        raise ValueError(f"pipeline '{pipeline}' does not exist")
    target = root / pipeline / "steps" / f"{step_id}.py"
    if target.exists():
        raise FileExistsError(f"{target.name} already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(STEP_TEMPLATE.format(step_id=step_id, pipeline=pipeline, kind=kind, class_name="".join(w.capitalize() for w in step_id.split("_"))), encoding="utf-8")
    return target
