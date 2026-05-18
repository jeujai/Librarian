## Purpose

The Multimodal Librarian currently processes PDF documents using PyMuPDF for text extraction. While native text is extracted well, all embedded images (charts, tables, diagrams, figures, scanned pages) are extracted as raw image files but their content is not interpreted. This means a page with a drug interaction table as an image, or a clinical diagram, produces no searchable text from that image content. Scanned PDFs (e.g., the 109MB Sanford Guide to Antimicrobial Therapy) produce as few as 1 chunk for an entire document.

This feature adds a Vision LLM pipeline that processes ALL embedded images in every PDF page through Ollama vision models. Every image is visually interpreted (description + OCR of any text within the image) and the interpretation is seamlessly combined with the page's native text. No information is lost — native text and image interpretations are unified into a single content stream before chunking.


### Key Terms
- **PDF_Processor**: The existing `PDFProcessor` component (`src/multimodal_librarian/components/pdf_processor/pdf_processor.py`) responsible for extracting text, images, and metadata from PDF files using PyMuPDF.
- **Vision_Engine**: A new component that processes images through Vision LLMs via Ollama to produce visual interpretations (descriptions + OCR of text within images).
- **Vision_Model**: An Ollama-hosted multimodal LLM capable of interpreting image content. Two models are used: `minicpm-v:8b` for structured content (tables, forms, charts) and `llama3.2-vision:11b` for narrative content (diagrams, photos, illustrations).
- **Image_Interpretation**: The text output from a Vision_Model for a single image, containing both a visual description and any text found within the image.
- **Unified_Page_Content**: The combined content stream for a page: native text (from PyMuPDF) + all image interpretations. No information is discarded.
- **Ollama_Pool_Manager**: The existing singleton `OllamaPoolManager` that provides fair-share scheduling of Ollama work across task types (currently bridge and KG).
- **Processing_Status_Service**: The existing WebSocket-based progress reporting system that sends real-time updates from Celery workers to the frontend.
- **Chunking_Framework**: The existing adaptive chunking system that processes extracted text into searchable chunks.

## Requirements

### Requirement: Image Extraction from Every Page

The system SHALL support: As a user uploading a PDF, I want every embedded image on every page to be identified and extracted, so that no visual content is missed.

#### Scenario: FOR every page in a PDF document, THE PDF_Processor SHALL ex

- **GIVEN** every page in a PDF document
- **THEN** FOR every page in a PDF document, THE PDF_Processor SHALL extract all embedded images using PyMuPDF's `page.get_images()` and `doc.extract_image()`.

#### Scenario: THE PDF_Processor SHALL track the page number and position i

- **THEN** THE PDF_Processor SHALL track the page number and position index of each extracted image for correct ordering in the unified content stream.

#### Scenario: WHEN all pages have been processed, THE PDF_Processor SHALL

- **THEN** WHEN all pages have been processed, THE PDF_Processor SHALL log a summary indicating total pages, total images found, and pages with zero images.

#### Scenario: THE PDF_Processor SHALL expose an `OCR_ENABLED` boolean sett

- **THEN** THE PDF_Processor SHALL expose an `OCR_ENABLED` boolean setting (default: `true`) as a global kill switch. WHEN `false`, image extraction for vision processing is skipped entirely.

### Requirement: Vision LLM Image Interpretation

The system SHALL support: As a user, I want every extracted image to be visually interpreted by a Vision LLM, so that charts, tables, diagrams, and text within images become searchable content.

#### Scenario: FOR each extracted image, THE Vision_Engine SHALL submit the

- **GIVEN** each extracted image
- **THEN** FOR each extracted image, THE Vision_Engine SHALL submit the image to the appropriate Vision_Model via the Ollama API with a prompt requesting both visual description and transcription of any text within the image.

#### Scenario: THE Vision_Engine SHALL submit vision work through the Ollam

- **THEN** THE Vision_Engine SHALL submit vision work through the Ollama_Pool_Manager using a new `OCR` task type, enabling fair-share scheduling alongside bridge and KG tasks.

#### Scenario: THE Vision_Engine SHALL resize images to a maximum dimension

- **THEN** THE Vision_Engine SHALL resize images to a maximum dimension of 1920 pixels before sending to the Vision_Model to limit memory usage and API payload size.

#### Scenario: THE Vision_Engine SHALL enforce a maximum image size of 20 m

- **THEN** THE Vision_Engine SHALL enforce a maximum image size of 20 megapixels and downscale images that exceed this limit while preserving aspect ratio.

#### Scenario: THE Vision_Engine SHALL expose configurable model names: `OC

- **THEN** THE Vision_Engine SHALL expose configurable model names: `OCR_VISION_MODEL_STRUCTURED` (default: `minicpm-v:8b`) and `OCR_VISION_MODEL_NARRATIVE` (default: `llama3.2-vision:11b`).

### Requirement: Content-Aware Model Routing

The system SHALL support: As a system operator, I want the system to automatically choose the best vision model for each image based on its content type, so that tables get the document-parsing specialist and diagrams get the general comprehension model.

#### Scenario: FOR each extracted image, THE Vision_Engine SHALL classify t

- **GIVEN** each extracted image
- **THEN** FOR each extracted image, THE Vision_Engine SHALL classify the image as either STRUCTURED (tables, forms, charts, multi-column layouts) or NARRATIVE (diagrams, photos, illustrations, prose).

#### Scenario: THE Vision_Engine SHALL use lightweight heuristics from the

- **THEN** THE Vision_Engine SHALL use lightweight heuristics from the PyMuPDF page object (line density via `page.get_drawings()`, text block column positions via `page.get_text("dict")`) to classify content type without requiring a separate model call.

#### Scenario: WHEN an image is classified as STRUCTURED, THE Vision_Engine

- **THEN** WHEN an image is classified as STRUCTURED, THE Vision_Engine SHALL route it to `minicpm-v:8b`.

#### Scenario: WHEN an image is classified as NARRATIVE, THE Vision_Engine

- **THEN** WHEN an image is classified as NARRATIVE, THE Vision_Engine SHALL route it to `llama3.2-vision:11b`.

#### Scenario: WHEN only one vision model is available (the other is not pu

- **THEN** WHEN only one vision model is available (the other is not pulled), THE Vision_Engine SHALL use the available model for all images regardless of content type.

### Requirement: Unified Page Content — No Information Loss

The system SHALL support: As a user, I want native text and image interpretations to be seamlessly combined into a single content stream per page, so that no information is lost and all content is searchable.

#### Scenario: FOR each page, THE PDF_Processor SHALL produce a Unified_Pag

- **GIVEN** each page
- **THEN** FOR each page, THE PDF_Processor SHALL produce a Unified_Page_Content that contains: (a) the full native text extracted by PyMuPDF (unchanged), followed by (b) all image interpretations for that page, each prefixed with `[Image {index}]`.

#### Scenario: THE PDF_Processor SHALL preserve page ordering — page 1 cont

- **THEN** THE PDF_Processor SHALL preserve page ordering — page 1 content before page 2, etc.

#### Scenario: THE PDF_Processor SHALL preserve image ordering within a pag

- **THEN** THE PDF_Processor SHALL preserve image ordering within a page — images appear in extraction order.

#### Scenario: WHEN a page has native text AND images, BOTH are included. I

- **THEN** WHEN a page has native text AND images, BOTH are included. It is never either/or.

#### Scenario: WHEN a page has no images, the page content is the native te

- **THEN** WHEN a page has no images, the page content is the native text only (existing behavior unchanged).

#### Scenario: WHEN a page has images but no native text (scanned page), th

- **THEN** WHEN a page has images but no native text (scanned page), the page content is the image interpretations only.

#### Scenario: THE Chunking_Framework SHALL process unified page content id

- **THEN** THE Chunking_Framework SHALL process unified page content identically to native-extracted text, with no special handling required.

### Requirement: Configuration

The system SHALL support: As a system operator, I want to configure vision processing via environment variables, so that I can tune behavior for different deployments.

#### Scenario: THE Settings SHALL expose `OCR_ENABLED` (bool, default `true

- **THEN** THE Settings SHALL expose `OCR_ENABLED` (bool, default `true`) as a global kill switch for all vision processing.

#### Scenario: THE Settings SHALL expose `OCR_VISION_MODEL_STRUCTURED` (str

- **THEN** THE Settings SHALL expose `OCR_VISION_MODEL_STRUCTURED` (str, default `minicpm-v:8b`) for the structured content model.

#### Scenario: THE Settings SHALL expose `OCR_VISION_MODEL_NARRATIVE` (str,

- **THEN** THE Settings SHALL expose `OCR_VISION_MODEL_NARRATIVE` (str, default `llama3.2-vision:11b`) for the narrative content model.

#### Scenario: THE Settings SHALL expose `OCR_MAX_IMAGE_DIMENSION` (int, de

- **THEN** THE Settings SHALL expose `OCR_MAX_IMAGE_DIMENSION` (int, default `1920`) for the max pixel dimension before resize.

#### Scenario: THE Settings SHALL expose `OCR_MAX_IMAGES_PER_DOCUMENT` (int

- **THEN** THE Settings SHALL expose `OCR_MAX_IMAGES_PER_DOCUMENT` (int, default `1000`) to limit total images processed per document.

#### Scenario: THE Settings SHALL expose `OLLAMA_FAIR_SHARE_RATIO` in three

- **THEN** THE Settings SHALL expose `OLLAMA_FAIR_SHARE_RATIO` in three-part format (`bridge:kg:ocr`, default `2:2:1`) while remaining backward-compatible with two-part format.

### Requirement: Ollama Pool Manager OCR Task Type

The system SHALL support: As a system operator, I want vision LLM tasks to participate in the Ollama pool's fair-share scheduling, so that image processing does not starve bridge generation or knowledge graph extraction.

#### Scenario: THE Ollama_Pool_Manager SHALL support a third task type `OCR

- **THEN** THE Ollama_Pool_Manager SHALL support a third task type `OCR` in the `TaskType` enum alongside `BRIDGE` and `KG`.

#### Scenario: THE Ollama_Pool_Manager SHALL maintain a separate queue for

- **THEN** THE Ollama_Pool_Manager SHALL maintain a separate queue for `OCR` tasks and include OCR in the fair-share scheduling algorithm.

#### Scenario: THE Ollama_Pool_Manager SHALL accept three-part ratio format

- **THEN** THE Ollama_Pool_Manager SHALL accept three-part ratio format (`bridge:kg:ocr`) while remaining backward-compatible with two-part format (OCR defaults to 0 share).

#### Scenario: THE Ollama_Pool_Manager SHALL report OCR queue depth and com

- **THEN** THE Ollama_Pool_Manager SHALL report OCR queue depth and completion counts in `get_pool_stats()`.

### Requirement: Memory Management

The system SHALL support: As a system operator, I want image processing to be memory-efficient, so that PDFs with hundreds of images do not cause out-of-memory errors.

#### Scenario: THE Vision_Engine SHALL process images sequentially (one at

- **THEN** THE Vision_Engine SHALL process images sequentially (one at a time) and release each image from memory before processing the next.

#### Scenario: THE Vision_Engine SHALL enforce a maximum image size of 20 m

- **THEN** THE Vision_Engine SHALL enforce a maximum image size of 20 megapixels and downscale images exceeding this limit.

#### Scenario: WHEN processing a document with more than 100 images, THE Vi

- **THEN** WHEN processing a document with more than 100 images, THE Vision_Engine SHALL trigger garbage collection after every 20 images.

#### Scenario: IF an image fails to process (MemoryError or vision model er

- **GIVEN** an image fails to process (MemoryError or vision model error)
- **THEN** IF an image fails to process (MemoryError or vision model error), THE Vision_Engine SHALL skip that image, log the error, and continue processing remaining images.

### Requirement: Progress Reporting

The system SHALL support: As a user watching a document upload, I want to see real-time vision processing progress, so that I know the system is actively interpreting images.

#### Scenario: WHEN vision processing begins, THE Processing_Status_Service

- **THEN** WHEN vision processing begins, THE Processing_Status_Service SHALL emit a status update with a `VISION_PROCESSING` stage.

#### Scenario: THE Processing_Status_Service SHALL emit progress updates af

- **THEN** THE Processing_Status_Service SHALL emit progress updates after each image is processed, including current image number, total images, and model used.

#### Scenario: WHEN vision processing completes, THE Processing_Status_Serv

- **THEN** WHEN vision processing completes, THE Processing_Status_Service SHALL emit a summary with total images processed, models used, and processing duration.

### Requirement: Infrastructure

The system SHALL support: As a DevOps engineer, I want the Docker environment configured for vision processing out of the box.

#### Scenario: THE docker-compose configuration SHALL expose `OCR_ENABLED`

- **THEN** THE docker-compose configuration SHALL expose `OCR_ENABLED` and vision model environment variables for both `app` and `celery-worker` services.

#### Scenario: THE application startup SHALL verify that configured vision

- **THEN** THE application startup SHALL verify that configured vision models are available in Ollama and log warnings for missing models.

#### Scenario: THE documentation SHALL include instructions for pulling vis

- **THEN** THE documentation SHALL include instructions for pulling vision models: `ollama pull llama3.2-vision:11b` and `ollama pull minicpm-v:8b`.

### Requirement: Graceful Degradation

The system SHALL support: As a user, I want document processing to complete even if vision models are unavailable, so that I still get native text extraction.

#### Scenario: IF the Ollama service is unreachable, THE Vision_Engine SHAL

- **GIVEN** the Ollama service is unreachable
- **THEN** IF the Ollama service is unreachable, THE Vision_Engine SHALL skip all image processing, log a warning, and allow native text extraction to proceed normally.

#### Scenario: IF neither vision model is pulled, THE Vision_Engine SHALL s

- **GIVEN** neither vision model is pulled
- **THEN** IF neither vision model is pulled, THE Vision_Engine SHALL skip image processing and log an error.

#### Scenario: IF only one vision model is available, THE Vision_Engine SHA

- **GIVEN** only one vision model is available
- **THEN** IF only one vision model is available, THE Vision_Engine SHALL use it for all images regardless of content type.

#### Scenario: WHEN vision processing fails for an individual image, THE Vi

- **THEN** WHEN vision processing fails for an individual image, THE Vision_Engine SHALL skip that image and continue.

#### Scenario: THE document metadata SHALL include `vision_images_processed

- **THEN** THE document metadata SHALL include `vision_images_processed` and `vision_failures` counts.
