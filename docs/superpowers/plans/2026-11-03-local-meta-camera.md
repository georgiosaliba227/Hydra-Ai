# Local Meta camera implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Track steps below.

**Goal:** Run the selected trained Meta adapter from Hydra on the owner's iPhone through their Mac, preserving exact label capacity and Confirm/Edit.

**Architecture:** Add a credential-free local recognition mode around the existing native workers and local Apple Vision OCR. Store bounded nonfinancial receipts in the beverage database and keep hosted billing disabled. Extend existing Swift mode validation and source presentation.

**Tech Stack:** Python/FastAPI/SQLite, SwiftUI, existing MLX Swift executable, macOS Vision.

**Spec:** `docs/architecture/LOCAL_META_CAMERA.md`

## Global constraints

- Pin selected adapter SHA `71a361e862c5e1399b25098601fd7d974253a5f5d285e9ad194f90e38028d48f`.
- No hosted calls, retries, fallback, credential export, financial ledger edits, or concurrent local requests.
- Unknown/conflicting label evidence stays unknown; capacity never establishes actual consumption.
- Preserve personal corrections, default-off training consent, original model output and deterministic fluid accounting.

## Review focus

- OCR serving/multipack/conflicting sizes must not create a guessed capacity (Task 1).
- Timeout/failure/second process must not retry, overlap workers or leak photos (Task 1).
- Wrong model/checkpoint must fail closed (Task 1).
- Receipt tampering or source-mode confusion must not produce a confirmed local log (Task 2).
- Local mode must not display cloud disclosure or mock-result claims (Task 3).

### Task 1: Local adapter and label boundary

Files: `backend/local_meta.py`, `backend/local_meta_runtime.py`, `scripts/local_label_ocr.swift`, `tests/recognition/test_local_meta.py`.
Interface: `LocalMetaRecognizer.analyze(AnalysisRequest) -> AnalysisResult`; runtime `recognize(jpeg: bytes) -> tuple[dict, str]` returns validated native prediction and OCR label evidence.

- [x] Write/run failing tests for prediction identity/checkpoint binding, label-only capacity, conflicts, missing evidence and no retries.
- [x] Implement pinned startup configuration and isolated sequential subprocess execution with timeout, sampled RSS checks and cleanup.
- [x] Compile OCR helper and exercise a real label fixture; run focused tests.
- [x] Commit verified runtime boundary.

### Task 2: API and durable local receipt

Files: `backend/recognition.py`, `backend/app.py`, `backend/recognition_feedback.py`, `backend/schemas.py`, `database/repository.py`, API tests in `tests/recognition/test_local_meta.py`.
Interface: additive `local_meta` recognition mode; repository records/reads/exports/deletes local receipts; confirmed logs retain local model/checkpoint provenance.

- [x] Write/run failing API tests for local mode, consent, result receipts, correction memory, no photo retention, invalid receipt/image/reference rejection, exact hydration volume and unchanged financial bytes.
- [x] Implement mode selection, local receipt checks and bounded storage.
- [x] Run focused tests and complete pytest suite; commit.

### Task 3: iPhone connection and verification

Files: existing Swift camera models/session/views/service and their XCTest files; local setup guide.
Interface: `local_meta` with separate model validation, local source copy, longer bounded timeout, existing confirmation payload.

- [x] Add/run failing XCTest for local source validation, consent gating, timeout, exact capacity and review draft.
- [x] Extend mode/source handling without changing Confirm/Edit accounting.
- [x] Run XCTest and relevant UI checks; build signed physical app.
- [ ] Install/test physical phone: blocked by CoreDevice4016, trusted wireless connection unavailable; USB or restored paired wireless connection required.
- [x] Start credential-free local backend using existing owner app token/database, test real inference, report exact observed status and remaining physical steps.
- [x] Fresh whole-branch review and fixes; commit verified changes.
- [ ] Push feature branch and preserve review handoff; GitHub PR creation previously denied by integration403.
