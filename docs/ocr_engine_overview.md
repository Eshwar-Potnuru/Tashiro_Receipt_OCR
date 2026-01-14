# OCR Engine Overview

This document summarizes the multi-engine strategy (Document AI, Google Vision, PaddleOCR, OpenAI Vision, etc.).

## Engine Selection Flow

```mermaid
graph TD
    Start[Start]
    DocAI{Document AI available?}
    GV{Google Vision fallback?}
    Paddle{Paddle OCR enabled?}
    OpenAI[OpenAI Vision]
    Result[Normalized OCR Result]

    Start --> DocAI
    DocAI -- Yes --> Result
    DocAI -- No --> GV
    GV -- Yes --> Result
    GV -- No --> Paddle
    Paddle -- Yes --> Result
    Paddle -- No --> OpenAI
    OpenAI --> Result
```

## TODO

- [ ] Capture latency & confidence heuristics per engine.
- [ ] Document merge strategies and weighting.
- [ ] Outline governance for API keys.
