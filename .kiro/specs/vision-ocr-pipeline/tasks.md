# Tasks: Vision OCR Pipeline

## Task 1: Add VisionOCRSettings to configuration

- [ ] 1.1 Add `VisionOCRSettings` Pydantic model with fields: `ocr_enabled` (bool, default True), `ocr_vision_model_structured` (str, default "minicpm-v:8b"), `ocr_vision_model_narrative` (str, default "llama3.2-vision:11b"), `ocr_max_image_dimension` (int, default 1920), `ocr_max_images_per_document` (int, default 1000)
- [ ] 1.2 Register the new settings fields in the application's Pydantic Settings class so they are loaded from environment variables (`OCR_ENABLED`, `OCR_VISION_MODEL_STRUCTURED`, `OCR_VISION_MODEL_NARRATIVE`, `OCR_MAX_IMAGE_DIMENSION`, `OCR_MAX_IMAGES_PER_DOCUMENT`)
- [ ] 1.3 Write unit tests verifying default values and environment variable override behavior

## Task 2: Extend OllamaPoolManager with OCR task type

- [ ] 2.1 Add `OCR = "ocr"` to the `TaskType` enum in `ollama_pool_manager.py`
- [ ] 2.2 Add `_ocr_queue` (queue.Queue) alongside `_bridge_queue` and `_kg_queue` in `OllamaPoolManager.__init__`
- [ ] 2.3 Extend `FairShareState` dataclass with `ocr_completed`, `ocr_target_ratio`, `ocr_actual_ratio`, and `ocr_deficit` fields
- [ ] 2.4 Update `_parse_fair_share_ratio()` to accept three-part format `bridge:kg:ocr` while remaining backward-compatible with two-part format (OCR defaults to 0 share when two-part)
- [ ] 2.5 Update `_pick_next_task_type()` to consider the OCR queue in deficit-based scheduling (pick the task type with the largest deficit among queues that have pending work)
- [ ] 2.6 Update `submit_ollama_work()` to route `task_type=TaskType.OCR` submissions to `_ocr_queue`
- [ ] 2.7 Update `_dispatch_loop()` to dequeue from `_ocr_queue` and increment `ocr_completed` on completion
- [ ] 2.8 Update `get_pool_stats()` to include `ocr_pending`, `ocr_completed`, `ocr_target_ratio`, `ocr_actual_ratio`, `ocr_deficit`
- [ ] 2.9 Update `_total_pending()` to include `_ocr_queue.qsize()`
- [ ] 2.10 Write unit tests: TaskType.OCR exists, two-part ratio backward compat (OCR=0), three-part ratio parsing, OCR stats in get_pool_stats
- [ ] 2.11 Write property-based test for Property 5 (fair share ratio parsing): for any valid 2-part or 3-part ratio string with positive weights, parsed ratios sum to 1.0 and each equals weight/total

## Task 3: Add VISION_PROCESSING stage to ProcessingStatusService

- [ ] 3.1 Add `VISION_PROCESSING = "vision_processing"` to the `ProcessingStatus` enum in `processing_status_service.py`
- [ ] 3.2 Write unit test verifying the new enum value exists and can be used in `update_status()` calls

## Task 4: Create VisionEngine component

- [ ] 4.1 Create `src/multimodal_librarian/components/pdf_processor/vision_engine.py` with `VisionEngine` class, `ContentType` enum (STRUCTURED, NARRATIVE), `ImageInterpretation` dataclass, and `VisionDocumentResult` dataclass
- [ ] 4.2 Implement `check_model_availability()` — call Ollama `/api/tags` endpoint, return dict of model_name -> bool for both configured models
- [ ] 4.3 Implement `resize_image(image_bytes, width, height)` — resize using Pillow to fit within `max_image_dimension` and `max_megapixels` (20M) while preserving aspect ratio, return (resized_png_bytes, new_width, new_height)
- [ ] 4.4 Implement `classify_content_type(page, image_metadata)` — use `page.get_drawings()` line count and `page.get_text("dict")` column positions to classify as STRUCTURED or NARRATIVE
- [ ] 4.5 Implement `_call_vision_model(image_bytes, model, prompt)` — encode image as base64, submit to OllamaPoolManager with `task_type=TaskType.OCR`, return interpretation text
- [ ] 4.6 Define vision model prompts: `STRUCTURED_PROMPT` and `NARRATIVE_PROMPT` as module-level constants
- [ ] 4.7 Implement `interpret_document_images(images_by_page, doc, document_id)` — iterate all images sequentially, classify each, resize, call vision model, collect results, release memory after each image, trigger GC every 20 images when total > 100, report progress via ProcessingStatusService, enforce `max_images_per_document` limit
- [ ] 4.8 Write property-based test for Property 2 (image resize constraints): for any width/height, verify max dimension, megapixel limit, and aspect ratio preservation
- [ ] 4.9 Write property-based test for Property 3 (content-aware model routing): for any line_count/column_count, verify classification and model selection
- [ ] 4.10 Write property-based test for Property 6 (progress percentage): for any (completed, total), verify percentage calculation
- [ ] 4.11 Write property-based test for Property 7 (vision metadata accuracy): for any list of success/failure results, verify vision_images_processed and vision_failures counts
- [ ] 4.12 Write unit tests: check_model_availability with mocked Ollama, single model fallback, Ollama unreachable skip, neither model available skip, image failure continues processing, GC trigger for >100 images

## Task 5: Integrate VisionEngine into PDFProcessor

- [ ] 5.1 Import VisionEngine in `pdf_processor.py` and instantiate it in `PDFProcessor.__init__` using settings (ocr_enabled, model names, max_image_dimension, max_images_per_document)
- [ ] 5.2 Modify `_extract_with_pymupdf()` to collect `images_by_page` dict (page_number -> list of MediaElement) during the page loop
- [ ] 5.3 After the page loop in `_extract_with_pymupdf()`, when `ocr_enabled` is True, call `vision_engine.interpret_document_images(images_by_page, doc, document_id)` to get vision results
- [ ] 5.4 Implement `_build_unified_content(doc, page_texts, vision_result)` — for each page, append image interpretations (prefixed with `[Image {index}]`) after native text. Handle: both text+images, text only, images only
- [ ] 5.5 Update document metadata with `vision_images_processed` and `vision_failures` from the VisionDocumentResult
- [ ] 5.6 Add extraction summary logging: total pages, total images found, pages with zero images
- [ ] 5.7 Write property-based test for Property 1 (image extraction completeness): for any page with N images, verify all N extracted with correct page_number and image_index
- [ ] 5.8 Write property-based test for Property 4 (unified page content): for any native text and list of interpretations, verify unified content contains all parts in correct order with correct prefixes
- [ ] 5.9 Write unit tests: OCR_ENABLED=false bypass, no-image page unchanged, no-text page with images produces interpretations only, page ordering preserved across multiple pages

## Task 6: Progress reporting via WebSocket

- [ ] 6.1 In `VisionEngine.interpret_document_images()`, emit `VISION_PROCESSING` status at start with total image count
- [ ] 6.2 After each image is processed, emit progress update with current image number, total images, model used, and progress percentage
- [ ] 6.3 On completion, emit summary with total images processed, models used, and processing duration
- [ ] 6.4 Write unit tests: VISION_PROCESSING stage emitted at start, per-image progress updates, completion summary emitted

## Task 7: Graceful degradation

- [ ] 7.1 In `VisionEngine.interpret_document_images()`, call `check_model_availability()` before processing. If Ollama is unreachable, log warning and return empty result. If neither model is available, log error and return empty result. If only one model is available, use it for all images.
- [ ] 7.2 In `_call_vision_model()`, catch connection errors and timeouts. On timeout, retry once with extended timeout. On persistent failure, record as failure and continue.
- [ ] 7.3 Write unit tests: Ollama unreachable returns empty result, neither model returns empty result, single model fallback routes all images, individual image failure continues processing

## Task 8: Docker and infrastructure configuration

- [ ] 8.1 Add `OCR_ENABLED`, `OCR_VISION_MODEL_STRUCTURED`, `OCR_VISION_MODEL_NARRATIVE`, `OCR_MAX_IMAGE_DIMENSION`, `OCR_MAX_IMAGES_PER_DOCUMENT` environment variables to `docker-compose.yml` for both `app` and `celery-worker` services
- [ ] 8.2 Update `OLLAMA_FAIR_SHARE_RATIO` default to `2:2:1` in docker-compose.yml
- [ ] 8.3 Add startup model availability check — on application startup, call `check_model_availability()` and log warnings for missing models
- [ ] 8.4 Add documentation for pulling vision models: `ollama pull llama3.2-vision:11b` and `ollama pull minicpm-v:8b`

## Task 9: Integration tests

- [ ] 9.1 Write integration test: end-to-end PDF with embedded images — process a known PDF, verify image interpretations appear in unified content
- [ ] 9.2 Write integration test: OllamaPoolManager OCR routing — submit OCR task, verify it goes to OCR queue and participates in fair-share scheduling
- [ ] 9.3 Write integration test: WebSocket progress updates — verify VISION_PROCESSING stage and per-image updates emitted during processing
- [ ] 9.4 Write integration test: unified content passes through chunking framework without errors
