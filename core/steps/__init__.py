"""Importing this package registers every built-in step."""
from . import crawl, demo, discover, harvest, llm_steps, paid, people_free, sheet_steps  # noqa: F401
from .base import all_steps, get_step, register, steps_for  # noqa: F401
from . import pipeline_run  # noqa: F401,E402  (last: it imports core.jobs, which imports get_step from here)
from .custom import reload_custom_steps

reload_custom_steps()          # pipelines/<name>/steps/*.py: broken files become error cards, never crashes
