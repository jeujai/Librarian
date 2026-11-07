# Librarian Interview Prep — Production AI Systems

## Core narrative (30-second elevator pitch)

I built Librarian, a GraphRAG medical knowledge platform that retrieves and synthesizes answers from a 7.1M-node, 35.3M-edge knowledge graph. The problem: pure vector search silently fails when you add enough documents — precise terms get diluted in the embedding space. The solution: a document ingestion pipeline that builds a structured knowledge graph, and a query-time pipeline where the graph finds structurally connected chunks before semantic search re-ranks them. The result: retrieval that doesn't degrade when your document library grows.

---

## System overview: two pipelines

Librarian has two distinct pipelines — one for ingestion, one for query. They share infrastructure but operate independently.

![System overview: ingestion pipeline (offline) and query pipeline (online) side by side](system-overview.png)

### What goes where

| Pipeline | When | Input | Output | Stores written |
|----------|------|-------|--------|---------------|
| **Ingestion** | Offline, per-document | PDF | Chunks, concepts, relationships, embeddings | PostgreSQL, Milvus, Neo4j |
| **Query** | Online, per-user-request | Natural language question | Ranked chunks + clinical gloss → LLM answer | None (read-only) |

---

## Pipeline 1: Document ingestion

### Order of operations

**Step 1 — Upload & validate.**
SHA-256 content hash for deduplication. Validate PDF magic bytes, size limits. Store in S3. Insert `knowledge_sources` row with status `PENDING`.

**Step 2 — PDF extraction.**
PyMuPDF extracts text with `[Page N]` markers preserved. pdfplumber detects tables. Embedded images are routed through content-aware vision models — `minicpm-v` for structured content (tables, forms), `llama3.2-vision` for diagrams and anatomical illustrations. The visual interpretation merges into the text stream. A 109MB antimicrobial therapy guide went from one chunk to full searchable content.

**Step 3 — Domain-aware chunking + embedding.**
A `GenericMultiLevelChunkingFramework` profiles each document's domain using Wikidata entity classification and ConceptNet patterns. Based on the profile, it applies domain-specific chunking: medical content gets boundary-aware splitting that keeps clinical entities intact; code and configuration get structural splitting. 768-dim embeddings generated via `bge-base-en-v1.5` model server. Chunks stored in PostgreSQL, embeddings in Milvus — batched 200 at a time.

**Step 4 — Bridge generation (parallel with Step 5).**
Gap analysis measures semantic distance, concept overlap, and cross-reference density between adjacent chunks. When the gap is significant, Llama 3.2 3B via Ollama generates a bridge passage preserving the conceptual thread. Each bridge validated by cross-encoding models for relevance and factual consistency. Failed bridges fall back to intelligent mechanical overlap with sentence-boundary awareness. Bridges stored incrementally — each batch persisted immediately so failures don't lose progress.

**Step 5 — Knowledge graph population (parallel with Step 4).**
Three concept extraction methods run concurrently per chunk:

- **spaCy NER** via model server (confidence 0.85)
- **Ollama LLM** with rationale grounding — keeps concepts only when rationale text appears in the source (confidence 0.65-0.70)
- **Regex/PMI** pattern extraction for multi-word terms, code identifiers, acronyms

Results merged by normalized name, keeping highest confidence. Then:

- **ConceptNet validation** — batch query Neo4j to validate against pre-loaded ConceptNet
- **UMLS linking** — annotate concepts with CUIs, create `SAME_AS` edges to UMLSConcept nodes
- **Relationship extraction** — three sources combined: regex patterns ("X causes Y"), ConceptNet, and embedding similarity (>0.85 cosine) which creates `SIMILAR_TO` edges between concepts with close embeddings ("renal failure" ↔ "kidney failure")
- **Neo4j persistence** — incremental batched UNWIND: MERGE Chunk nodes, MERGE Concept nodes, MERGE EXTRACTED_FROM edges, MERGE typed relationship edges

**Step 6 — Quality gate + finalize.**
Composite quality gate evaluates failure rates across all extraction stages (NER failures, LLM failures, bridge failures) against content-type-specific thresholds. Pass → document marked `COMPLETED` and becomes searchable. Fail → document marked `FAILED` with error detail. Background enrichment (YAGO, ConceptNet API) continues post-completion — cross-document SAME_AS and RELATED_DOCS edges appear as enrichment progresses.

![Document ingestion pipeline: 6 steps from PDF upload through quality gate](ingestion-pipeline.png)

---

## Pipeline 2: RAG query

### Order of operations

**Step 1 — Three-layer NER on the query.**
Same three extractors used in ingestion, now running against the user's natural language question. spaCy for general proper nouns, scispaCy for multi-word scientific terms, UMLS linker for clinical concepts. Results merged with priority hierarchy — UMLS terms override shorter scispaCy terms when fully contained; non-overlapping terms preserved. "Hepatitis B surface antigen" as one entity, not three fragments.

**Step 2 — Concept matching against Neo4j fulltext index.**
Extracted concepts matched against the 756K Concept nodes in the graph via fulltext search on normalized names.

**Step 3 — Four concurrent traversal strategies per concept pair.**
All four strategies pursue the same goal: find chunks where multiple query concepts co-occur via `EXTRACTED_FROM` edges. They differ only in how they get there — direct adjacency through structured relationships, or pure co-occurrence when no relationship edge exists. A shared `chunk_concept_connections` map (`chunk_id → {concept_ids}`) accumulates hits from every strategy. Any chunk connected to ≥2 query concepts becomes an **intersection chunk** and receives the relationship boost in Step 4.

1. **UMLS 1-hop:** Clinical relationships along UMLS_REL edges. Concept A → UMLS relationship → Concept B → both concepts' EXTRACTED_FROM chunks.
2. **UMLS 2-hop:** Two-step clinical reasoning. "metformin" → "may treat" → "Type 2 Diabetes" → "isa" → "Diabetes Mellitus" → chunks.
3. **Direct inter-concept edges:** Typed relationships extracted from documents (CAUSES, TREATS). Only 35 clinically meaningful UMLS relationship types are whitelisted — false positives in clinical retrieval are worse than false negatives.
4. **Shared-chunk co-occurrence:** No intermediate relationship — just checks whether two concepts independently point to the same chunk via EXTRACTED_FROM. This is the simplest path to intersection and the fallback when no relationship edge exists between the concepts.

A **SAME_AS pre-check** determines whether any matched concept bridges to UMLS. For non-medical queries, both UMLS strategies skip entirely — preserving the timeout budget for document-edge and co-occurrence strategies.

**Step 4 — Merge and re-rank.**
Chunk IDs from all four strategies are merged. A `ChainSynthesizer` converts raw graph path annotations into a human-readable clinical reasoning gloss. The merged IDs resolve against Milvus for semantic similarity re-ranking. Final ranking: graph-derived chunks, ordered by semantic relevance to the query.

**Step 5 — LLM synthesis with context.**
The clinical reasoning gloss lands in the system prompt via a `KNOWLEDGE GRAPH INSIGHTS` slot — *before* the LLM reads any retrieved chunks. The model gets explicit clinical relationship context to reason from, not just documents to summarize. Response streams via WebSocket with clickable source citations: document title, page number, relevance score, excerpt from source chunk.

![Query pipeline: 5 steps from user query through LLM synthesis](query-pipeline.png)

---

## Key infrastructure decisions

**Concurrent traversal with adaptive timeout.** At 7.1M nodes with 15 matched concepts, sequential Neo4j traversals timeout. Running four strategies concurrently per pair via `asyncio.gather` means total latency = slowest single query, not sum of all queries. An adaptive timeout budget allocates remaining time to remaining strategies rather than equal fixed slices.

**ML model server in separate container.** 4GB of models (embedding, spaCy, scispaCy, cross-encoders) load asynchronously in their own Docker container. The FastAPI app container starts in 5 seconds and issues requests to the model server when ready. Code changes don't require reloading 4GB of models.

**Seven-service Docker stack.** Neo4j, Milvus, PostgreSQL, Redis, Celery workers (document processing), ML model server, FastAPI app. Dependency-ordered start/stop scripts ensure Milvus waits for etcd+minio.

---

## Secondary example: Quality controls and hallucination reduction

### Problem

I tried using an LLM to judge the relevance of retrieved chunks. It was confident, persuasive, and wrong — accepting chunks that mentioned the right keywords but contradicted clinical consensus. I needed deterministic quality signals.

### What I built

Two explicit relevance signals instead of LLM-as-judge:

1. **Score distribution analysis:** detects when results cluster at the semantic floor — everything scores similarly because nothing is truly relevant
2. **Concept specificity analysis:** distinguishes domain-specific terms from generic words to assess whether the knowledge graph found meaningful matches

A **quality gate** at the end of ingestion validates every pipeline stage: NER failure rates, LLM extraction failure rates, bridge generation success — all tracked per-document against content-type-specific thresholds before marking complete.

The **SAME_AS pre-check** at query time determines whether any matched concept bridges to UMLS. For non-medical queries, clinical strategies skip entirely rather than returning noise.

### Outcome

Deterministic, auditable quality signals that don't hallucinate. Confidence scores adjust downward for uncertain results. When library results are thin, the system supplements with web search via SearXNG and clearly labels the source type.

---

## Anticipated questions — 60-90 second answers

### "Tell me about a production GenAI system you've built."

**Problem:** At Oracle Health, users searched a growing library of clinical documents. Pure vector search had a silent failure mode — adding documents shifted the vector index and pushed previously retrievable content below the similarity threshold. A known parameter would disappear — not ranked lower, gone entirely. No error, no crash.

**Architecture:** I built a system with two pipelines. The ingestion pipeline takes a PDF through extraction, vision OCR for embedded images, domain-aware chunking, embedding generation, and knowledge graph population — extracting concepts with three concurrent methods, validating against ConceptNet, linking to UMLS, and extracting typed relationships. The query pipeline runs three-layer NER on the user's question, matches concepts against Neo4j, runs four concurrent traversal strategies, then re-ranks results via Milvus semantic search. A ChainSynthesizer converts raw graph paths into clinical reasoning context that lands in the LLM's system prompt.

**Outcome:** Structural retrieval that doesn't degrade with library growth. Clinical reasoning chains surfaced that no single document explicitly states. Streaming responses with clickable source citations. 356K searchable chunks across a 7.1M-node graph.

### "How do you reduce hallucination?"

Three layers. First, **structural retrieval** — the knowledge graph uses deterministic EXTRACTED_FROM pointers. A concept either came from a chunk or it didn't. Those pointers don't drift when the index grows. Second, **deterministic quality signals** at both ingestion and query time — score distribution analysis, concept specificity analysis, and a composite quality gate that validates every extraction stage. I learned the hard way that LLMs can't judge their own input quality. Third, **the system prompt** — the ChainSynthesizer gives the LLM explicit clinical relationship context before it reads any chunks, so it reasons from structured knowledge rather than free-associating across retrieved documents.

### "What's your experience with agentic workflows?"

The four concurrent traversal strategies are effectively an agentic pattern — each pursues an independent retrieval path and their results are fused. The system makes autonomous decisions: skip UMLS strategies for non-medical queries, allocate timeout budget adaptively, fall back to web search when library results are thin. The ingestion pipeline uses Celery chords for parallel bridge generation and KG population, with the finalize step gating on both completing. I've also built an agentic healthcare policy analyst using LangGraph for multi-step reasoning with human-in-the-loop review.

### "How do you work with stakeholders?"

[Customize based on your Oracle Health experience — who were the stakeholders, what did they need, how did you translate that into technical requirements?]

### "Why mission-driven work?"

Librarian started because I wanted to operationalize expert knowledge so it reaches the people who need it — doctors, nurses, teachers — especially in contexts where connectivity is limited. The goal is a self-contained tablet-based GraphRAG application that can dispense accurate expert advice on any topic. Government and healthcare work share that DNA: the impact is measured in outcomes, not ad clicks. That's the kind of work I want to do.

### If PhD comes up

I'm exploring it as a long-term possibility — I've been in conversation with researchers about graph embedding approaches — but my focus right now is full-time industry work building production AI systems. The PhD would complement that experience, not replace it.

---

## Key phrases to use

- "Two pipelines: ingestion builds the graph offline, query reads from it online"
- "Structural retrieval that doesn't drift when the index grows"
- "Deterministic quality signals instead of LLM-as-judge"
- "Three concurrent extraction methods per chunk, merged by confidence"
- "Four concurrent traversal strategies with adaptive timeout budgeting"
- "35 clinically meaningful UMLS relationship types — because false positives are worse than false negatives in clinical retrieval"

## Pitfalls to avoid

- Don't conflate ingestion and query — they're separate pipelines with separate timing and infrastructure
- Don't mention the continuous-trust strategic plan unless they ask about future directions
- Don't reference the TDS/Medium article — it's a side project, not the main story
- Don't lead with "7.1M nodes, 35.3M edges" — lead with the problem, mention scale as context
- Don't frame Ollama/local-models as a cost-cutting limitation — frame it as architecture flexibility (runs on local Docker, deploys to AWS Neptune/ECS)
