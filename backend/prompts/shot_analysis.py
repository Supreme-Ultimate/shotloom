"""Legacy prompt module.

Prompts and output fields are now loaded from JSON profiles in
`backend/prompt_configs/`. Keep this module as a compatibility shim for older
imports and third-party extensions.
"""

from prompt_config import build_continuity_prompt, build_shot_prompt

SHOT_USER_PROMPT = build_shot_prompt(shot_index=1, total_shots=1)
CONTINUITY_PROMPT = build_continuity_prompt("[]")
