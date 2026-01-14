# Pipelines Overview

This document captures the planned pipelines for single and multi-receipt processing.

## Receipt Intake Flow

```mermaid
graph TD
    Upload[Upload Receipts]
    Preprocess[Image Preprocessing]
    OCR[Multi-Engine OCR]
    Mapping[Mapping & Extraction]
    Validation[Validation & Duplicate Checks]
    Excel[Excel Writers]
    History[Submission History]

    Upload --> Preprocess --> OCR --> Mapping --> Validation --> Excel --> History
```

## Batch Pipeline Considerations

- Sequential placeholder pipeline (`MultiReceiptPipeline`) stands in until concurrency strategy is defined.
- Background tasks should queue file-level work with telemetry hooks.
- Submission history must record batch + per-file states.

## TODO

- [ ] Add error-handling and retry flows.
- [ ] Define metrics/observability plan per stage.
