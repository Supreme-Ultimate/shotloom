# Changelog

## 0.1.0 - Initial Open Source Release

### Added

- Docker Compose deployment with Postgres, Redis, backend worker, backend API, and frontend.
- User authentication, admin user management, and credit balance management.
- Video upload, shot detection, thumbnail generation, shot analysis, selected-shot analysis, cancellation, and whole-video analysis.
- Qwen Omni OpenAI-compatible multimodal analysis path with audio-aware prompt fields.
- Configurable prompt and analysis-field profiles via `backend/prompt_configs/default.json` and `PROMPT_CONFIG_PATH`.
- PDF and Excel report export.
- Chinese and English README files.
- MIT license, contribution guide, security policy, and audit notes.

### Fixed

- User data isolation so normal users only see their own videos.
- Stale analysis progress reconciliation after worker failures or page refreshes.
- Re-detect flow clearing stale shot lists and updating status immediately.
- Short video clip handling for models with minimum input duration requirements.
- PDF export runtime dependencies and WeasyPrint/pydyf compatibility.
- PDF report image/text layout overlap.
