# Prompt Config

This directory contains JSON prompt profiles used by the backend.

- `default.json` is the built-in profile copied into the Docker image.
- Set `PROMPT_CONFIG_PATH` to use another JSON file, for example:
  - local: `PROMPT_CONFIG_PATH=backend/prompt_configs/default.json`
  - docker bind mount: `PROMPT_CONFIG_PATH=/app/prompt_configs/default.json`

What can be customized:

- `role`, `shot_prompt_intro`, `shot_extra_instructions`
- `shot_fields`: fields requested from the multimodal model for each shot
- `continuity_role`, `continuity_extra_instructions`
- `continuity_summary_fields`: which shot-analysis fields are summarized for whole-video analysis
- `continuity_fields`: fields requested from the whole-video model

Field format:

```json
{
  "key": "field_name",
  "description": "What the model should output",
  "type": "array",
  "example": ["optional example"]
}
```

Nested fields are supported with `fields`.
