"""Importing this package registers every built-in step."""
from . import crawl, demo, harvest, llm_steps, paid, people_free, sheet_steps  # noqa: F401
from .base import all_steps, get_step, register, steps_for  # noqa: F401
from .custom import reload_custom_steps

reload_custom_steps()          # pipelines/<name>/steps/*.py: broken files become error cards, never crashes
