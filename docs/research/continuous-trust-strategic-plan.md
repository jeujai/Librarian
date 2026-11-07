# From Binary Gates to Continuous Trust: A Strategic Plan for Multi-Domain Graph-Guided Retrieval

## 1. Current State: What Exists Now

The Librarian retrieves relevant document chunks using a two-stage pipeline:

**Stage 1 — Knowledge Graph Retrieval.** A Neo4j graph (7.1M nodes, 35.3M relationships) enriched with Wikidata, ConceptNet, and UMLS. Four traversal strategies run concurrently per concept pair (UMLS 1-hop, UMLS 2-hop, direct inter-concept edges, shared-chunk co-occurrence). Retrieved chunk IDs feed into Stage 2.

**Stage 2 — Semantic Re-ranking.** Chunk IDs resolve against Milvus and re-rank by semantic similarity. The LLM receives graph-derived clinical gloss (ChainSynthesizer) alongside retrieved chunks.

The system uses binary gates throughout:

| Gate | Mechanism | Limitation |
|------|-----------|------------|
| UMLS relationship whitelist | 35 types in, all others out | Requires domain expert curation; doesn't scale to new domains |
| SAME_AS pre-check | Yes/no: skip UMLS entirely for non-medical queries | Throws away partial signal; can't express "weakly connected to UMLS" |
| NER merge hierarchy | UMLS > scispaCy > spaCy (binary promotion) | Can't express "scispaCy is 60% confident, UMLS is 40%" |
| Path quality | All edges trusted equally within whitelisted types | No mechanism to detect noisy extraction edges |
| Quality gate | Percentage co-occurrence of identified concepts | Binary threshold; no per-relationship confidence |

These gates work. They're the reason the system produces correct answers. But each one encodes a human decision that can't adapt to new domains or express uncertainty.

---

## 2. Target State: Continuous-Scoring, Multi-Domain Inference

Every binary gate becomes a continuous score. The system expresses *how much* it trusts each signal, and a fusion mechanism resolves competing confidences into a single ranking per chunk.

### Core principle

> Instead of deciding what to include, the system scores everything and lets the scores decide.

### What changes

| Current (binary) | Target (continuous) |
|------------------|---------------------|
| UMLS types in/out | Every edge type gets a learned transformation matrix; edge scores reflect geometric fit |
| SAME_AS bridge: yes/no | Bridge score: continuous alignment between embedding spaces |
| NER promotion hierarchy | Each NER layer contributes to a fused concept representation weighted by layer confidence |
| All edges within a type trusted equally | Each edge scored individually by how well it conforms to its type's learned geometry |
| Fixed λ weights per layer | Per-query, per-concept-pair adaptive weights driven by bridge scores and edge confidence |
| α/β fixed or absent | Graph-vs-semantic balance learned per query from signal confidence |

### Target architecture

![Target architecture: continuous-scoring, multi-domain inference pipeline](target-architecture.png)

---

## 3. The Transformation: Binary → Continuous

Every gate in the current system maps to a research contribution.

### 3.1 Relationship type whitelist → learned edge matrices

**Current:** 35 UMLS relationship types hardcoded. Document edges partially used. All other types ignored.

**Target:** Every relationship type gets a learned transformation matrix during training. At query time, each edge receives a score: how well does this specific edge conform to the geometric pattern of its type?

- `Hepatitis B → CAUSES → liver failure`: score 0.89 (fits the causal pattern)
- `aspirin → CAUSES → headache`: score 0.23 (edge exists but doesn't *behave* causal)
- `metformin → QB_qualifier → diagnosis`: score 0.12 (QB edges never fit any clinical pattern — automatically filtered without being explicitly excluded)

**How:** Train heterogeneous graph embeddings (node types: Concept, Chunk, UMLSConcept, ExternalEntity; edge types: all 60+ document extraction types + all UMLS_REL types). Each edge type gets its own transformation matrix. The training objective: source_emb × edge_matrix ≈ target_emb. After training, score every edge in the graph once. Store scores as edge properties in Neo4j. At query time, path scores = product of constituent edge scores.

**Research contribution:** Learned edge scoring replaces domain-specific relationship whitelisting. The system discovers which relationship types carry signal for which query domains without human curation.

### 3.2 SAME_AS pre-check → bridge score

**Current:** Does any matched concept have a SAME_AS bridge to UMLS? Yes → run UMLS strategies. No → skip both. Binary.

**Target:** Every bridge edge gets a score. The bridge matrix maps Concept space to UMLS space. The score is the cosine distance between the predicted location and the actual UMLSConcept embedding.

- "metformin" → SAME_AS → UMLS: bridge_score = 0.91 (well-aligned)
- "Chelsea" → SAME_AS → UMLS: bridge_score = 0.14 or no bridge (weakly aligned or absent)
- "allow_dangerous_code=True" → no bridge (score = 0)

Rather than a binary skip, λ_UMLS is set proportional to the bridge score per concept pair. A concept with bridge_score = 0.55 gets partial UMLS contribution — the system doesn't throw away the signal, it weights it appropriately.

**How:** Train bridge matrices alongside edge matrices in Step 1. The SAME_AS matrix is just another transformation matrix, but between spaces rather than within a space. At query time, compute bridge score for every concept with a UMLS mapping. Set λ_UMLS = f(bridge_score) where f can be linear, sigmoid, or learned.

**Research contribution:** Bridge scoring enables partial cross-ontology reasoning. The system uses UMLS when it's confident and relies on document edges when it's not, without a binary switch.

### 3.3 NER merge hierarchy → fused concept representation

**Current:** UMLS terms override scispaCy terms when fully contained; scispaCy terms override spaCy terms. Non-overlapping terms preserved. Binary promotion.

**Target:** Each NER layer produces not just a text span but a confidence vector. The fused concept representation is a weighted combination:

```
concept_rep = w_spaCy × spaCy_span + w_sci × sci_span + w_UMLS × UMLS_span
```

Where w_UMLS is higher for medical terms (backed by the UMLS embedding space) and w_spaCy is higher for general proper nouns. The weights aren't hardcoded — they're learned from how often each layer's output correctly maps to an existing node in the Concept space.

**How:** During training, compute alignment between each NER layer's output and existing graph nodes. spaCy's "hepatitis" → partial match to Concept node "hepatitis B surface antigen." UMLS linker's "hepatitis B surface antigen" → exact match. The weights emerge from which layer consistently maps to correct nodes for which term types.

**Research contribution:** Fused NER representations eliminate the hardcoded promotion hierarchy. The system learns per-term-type confidence from graph alignment rather than being told.

### 3.4 Fixed quality threshold → per-path confidence scoring

**Current:** Quality gate: percentage co-occurrence of identified concepts. Binary pass/fail. If concepts co-occur above threshold, the chunk passes. Otherwise filtered.

**Target:** Every path from concept to chunk produces a score. The score is the product of edge scores along the path. Multiple paths to the same chunk accumulate. A chunk reached via strong CAUSES and TREATS edges gets a higher score than one reached via weak RELATES_TO edges. The quality gate becomes a ranking, not a filter.

**How:** Path scoring at query time (Steps 2-3 in the pipeline). Walk the graph, compute edge scores, multiply along paths, accumulate at chunks.

**Research contribution:** Quality becomes continuous. Chunks aren't accepted or rejected — they're ranked by the aggregate confidence of every path that reaches them.

### 3.5 Fixed layer weights → adaptive per-query fusion

**Current:** All layers contribute equally within the traversal. UMLS is either fully on or fully off (SAME_AS pre-check).

**Target:** Fusion weights λ_UMLS, λ_external, λ_document, λ_cooccur are computed per query based on bridge scores and edge confidence:

```
λ_UMLS = f(mean_bridge_score, concept_specificity)
λ_external = f(mean_bridge_score_to_Wikidata, concept_coverage)
λ_document = 1.0 (always active — document graph is the backbone)
λ_cooccur = f(chunk_density, concept_pair_count)
```

For a clinical query with high bridge scores: λ_UMLS dominates. For a general query with no bridges: λ_UMLS ≈ 0, λ_document and λ_cooccur carry retrieval. For a mixed query (clinical + general concepts): all layers contribute proportionally.

**How:** Learn global λ functions during training (how should bridge scores map to layer weights?). Optionally fine-tune per query based on concept specificity (Step 5).

**Research contribution:** Multi-layer fusion that adapts to query domain without domain labels. The query itself determines which knowledge sources to trust.

### 3.6 Graph-vs-semantic balance → learned α, β

**Current:** Stage 2 semantic re-ranking treats all Stage 1 chunks equally. No weighting of graph confidence vs. semantic similarity.

**Target:** α weights the graph contribution; β weights semantic similarity. When graph paths are high-confidence (strong UMLS bridges, high edge scores), α increases. When graph signal is sparse or noisy, β takes over. The system expresses its certainty through the ratio.

**How:** α and β can be: (a) global constants learned on a held-out evaluation set, or (b) computed per query from the variance of graph scores (high variance across chunks = graph is discriminating well → increase α; low variance = graph is uncertain → decrease α).

**Research contribution:** Continuous graph-vs-semantic tradeoff that self-calibrates per query.

---

## 4. Implementation Plan

### Phase 1: Embed everything (months 1-3)

**Goal:** Train heterogeneous graph embeddings across all three layers, producing edge matrices and bridge matrices.

**Tasks:**
1. Map all node types and edge types in the current Neo4j graph
2. Select heterogeneous GNN framework (HGT or R-GCN as starting point; HGT recommended for scale)
3. Train Layer A (document graph) embeddings: Concept space + Chunk space + all document edge matrices
4. Train Layer B (external) embeddings: Wikidata + ConceptNet entity space + edge matrices. Reuse existing pre-computed Wikidata/ConceptNet embeddings where available (Paulheim's suggestion)
5. Train Layer C (UMLS) embeddings: UMLSConcept space + 35 UMLS_REL edge matrices (expand to all UMLS_REL types, not just the 35 whitelisted)
6. Train bridge matrices: SAME_AS (Concept↔UMLS, Concept↔ExternalEntity)
7. Score every edge in Neo4j and store scores as edge properties
8. **Validation gate:** Confirm that edge scores correlate with clinical correctness on known-good paths (e.g., metformin → may_treat → T2D should score high; aspirin → CAUSES → headache should score low)

### Phase 2: Path scoring at query time (months 4-5)

**Goal:** Replace binary traversal with scored path traversal.

**Tasks:**
1. Implement per-edge score lookup during traversal (read pre-computed scores from Neo4j edge properties)
2. Compute path scores as product of edge scores
3. Replace the whitelist with universal edge traversal + score-based ranking — all relationship types traversed, low-scoring paths deprioritized naturally
4. Implement accumulated chunk scoring (multiple paths → same chunk → sum or max-pool scores)
5. **Baseline comparison:** Run the current whitelisted system vs. scored-universal system on a held-out query set. Measure precision/recall. Expectation: scored-universal ≥ whitelisted on clinical queries, strictly better on non-clinical queries (where whitelist provides zero signal)

### Phase 3: Bridge scoring and adaptive layer fusion (months 6-7)

**Goal:** Replace binary SAME_AS pre-check and fixed layer weights.

**Tasks:**
1. Implement bridge score computation at query time
2. Implement λ weight functions: map bridge scores → per-layer weights
3. Implement fused chunk scoring: Σ(λ_layer × path_score) per chunk
4. Train global λ functions on evaluation set
5. Implement per-query λ adaptation based on concept specificity and bridge score variance
6. **Evaluation:** Compare fused scoring vs. binary UMLS on/off. Expectation: improved recall without precision loss on mixed-domain queries

### Phase 4: Fused NER and adaptive α/β (months 8-9)

**Goal:** Replace NER promotion hierarchy and fixed graph-semantic balance.

**Tasks:**
1. Train per-layer NER confidence weights from graph alignment
2. Implement fused concept representation at query time
3. Implement α/β computation per query from graph score variance
4. Integrate fused NER output into concept matching and traversal
5. Integrate α/β into Stage 2 semantic re-ranking
6. **Full system evaluation:** End-to-end comparison against current binary-gate system. Metrics: precision@k, recall@k, MRR, human preference (domain expert ratings)

### Phase 5: Research packaging and publication (months 10-12)

**Goal:** Produce publishable results from the system evaluation.

**Tasks:**
1. Construct gold-standard evaluation dataset: question/answer pairs across clinical, technical, and general domains
2. Recruit domain experts for blind rating of system outputs (current system vs. continuous-scoring system vs. baselines)
3. Baselines to compare against:
   - Pure vector search (Milvus-only)
   - Plain text-based RAG (no KG)
   - Current Librarian with binary gates
   - Continuous-scoring Librarian
   - External GraphRAG systems if publicly available
4. Statistical analysis of results
5. Write and submit papers targeting:
   - **Paper 1:** "Learned Edge Scoring Replaces Domain-Specific Relationship Whitelisting in Graph-Guided Retrieval" (JAMIA or similar)
   - **Paper 2:** "Continuous Multi-Layer Fusion for Cross-Domain Knowledge Graph Retrieval" (ISWC or similar)
   - **Paper 3:** Full system paper (JOSS or JMLR)

---

## 5. Evaluation Framework

### Gold standard dataset

- 200+ question/answer pairs
- Domains: clinical (~70), technical/general (~70), mixed (~60)
- Each pair annotated with: relevant document IDs, relevant chunk IDs, answer quality rating
- Source: domain experts + existing biomedical QA benchmarks

### Metrics

| Metric | What it measures |
|--------|------------------|
| Precision@k | How many of the top-k chunks are relevant? |
| Recall@k | How many of all relevant chunks are in the top-k? |
| MRR | Where does the first relevant chunk rank? |
| NDCG | Quality-weighted ranking |
| Domain expert rating | 1-5 human judgment of answer quality |
| Edge score calibration | Do edge scores correlate with clinical correctness? |

### Comparison systems

1. Milvus-only semantic search
2. Text-based RAG (no KG, vector search on chunks with LLM)
3. Current Librarian (binary gates, whitelisted UMLS types)
4. Continuous-scoring Librarian (full system)
5. Any publicly available GraphRAG system on the same dataset

---

## 6. Research Contributions Summary

| Contribution | Current → Target | Novelty |
|-------------|-----------------|---------|
| Learned edge scoring | Whitelist → all edges scored by geometric fit | High: replaces domain-specific curation with learned geometry |
| Bridge scoring | Binary SAME_AS → continuous cross-space alignment | High: partial cross-ontology reasoning without domain labels |
| Fused NER | Promotion hierarchy → weighted concept representation | Medium: applies fusion principle to NER, building on existing multi-layer NER work |
| Adaptive layer fusion | Fixed/skip weights → per-query λ from bridge scores | High: domain-adaptive retrieval without domain classification |
| Self-calibrating α/β | Absent → graph confidence drives semantic tradeoff | Medium: novel application of uncertainty weighting to retrieval |
| Universal relationship traversal | 35 types → all types, scored | High: system discovers signal in relationship types humans excluded |

---

## 7. Immediate Next Steps

1. **This week:** Map all node types and edge types currently in Neo4j. Export the schema. Identify every relationship type and its frequency.
2. **This week:** Begin literature review on heterogeneous graph transformers (HGT, R-GCN) and existing graph embedding approaches for biomedical KGs.
3. **Within 2 weeks:** Contact Paulheim with a concrete proposal — "Here's the current graph schema. Here's the binary-to-continuous transformation plan. Would you advise on the embedding framework choice and evaluation design?"
4. **Within 1 month:** Select and begin training the first embedding layer (document graph). Validate that edge scores make intuitive sense on known-good and known-noisy edges.

---

*Strategic plan — May 2026. Target completion: May 2027.*
