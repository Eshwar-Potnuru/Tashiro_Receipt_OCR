# Folder Structure

This guide outlines the evolving directory taxonomy for the project.

```mermaid
graph LR
    Root[Repo Root]
    App[app/]
    Docs[docs/]
    Artifacts[artifacts/]
    Tests[tests/]
    Scripts[scripts/]
    TemplateDir[Template/]

    Root --> App
    Root --> Docs
    Root --> Artifacts
    Root --> Tests
    Root --> Scripts
    Root --> TemplateDir
```

## Highlights

- `app/` – Core application code (API, services, pipeline, OCR, Excel writers).
- `docs/` – Architectural references, onboarding guides.
- `artifacts/` – Non-source outputs (uploads, logs, exports).
- `tests/` – Automated validation suites.
- `scripts/` – Operational utilities.
- `Template/` – Master Excel templates managed outside the code flow.

## TODO

- [ ] Document retention policy for `artifacts/`.
- [ ] Add per-folder ownership and review notes.
