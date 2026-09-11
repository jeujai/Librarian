# Emergent Concepts Architecture

**Status:** Draft (for review)
**Scope:** Knowledge graph concept model, extraction, bridging, and retrieval
**Related:** `bridge_status`, compositional grounding, the "second layer" of direct inter-document association

---

## 1. Problem

The knowledge graph bridges document-extracted concepts to canonical ontologies
(ConceptNet, Wikidata/YAGO, UMLS) via `SAME_AS` (exact/typed) and `SIMILAR_TO`
(semantic) edges. The intent of this design is deliberately **ontology-as-hub**:
indirect association *through* a shared ontological concept, to buy canonical
precision and smallest-blast-radius canvassing across a minimum number of hops.

That design has a structural vulnerability. A concept with **zero ontological
coverage** has nothing to hub through, and becomes an orphan — invisible to the
conversational bridging that the rest of the graph provides.

"work restrictions" is the canonical example. It is *compositional* — a
multi-word compound — which is exactly why it appears in no existing ontology:

- **spaCy NER** tags named entities (`ORG`/`PERSON`/`LOC`), not generic noun
  compounds; "work restrictions" is not a named entity.
- **ConceptNet** encodes *atomic* commonsense concepts with relational edges; it
  likely holds "work" and "restriction" separately, but the compound was never
  crowdsourced as a single node.
- **UMLS/SNOMED** cover biomedical vocabulary; "work restrictions" is
  organizational/policy, outside that ontology.

This is not a few missing rows. It is a **systematic class** — compositional,
domain-adjacent, multi-word terms — that falls between every ontology's
granularity. It cannot be fixed by "add more terms to UMLS." It needs a tier of
its own.

The escape hatch (§4.5) narrows — but does not eliminate — the class: a compound
whose parts are *both* ontology-anchored *and* connected there by an edge can
re-anchor to that subgraph. The residual orphan is the compound whose parts lack
coverage, or whose parts the ontology never connects.

---

## 2. Design principles

1. **Ontology remains the hub, but it is not the only layer.** Keep the
   hub-and-spoke precision for everything that has an ontological home. Add a
   second, ontology-independent layer for everything that does not.

2. **Emergent concepts are first-class.** They are not second-class citizens and
   not a staging area waiting for an ontology that may never adopt them. In the
   beginning, the numerical superiority of canonical relationships will dominate
   inference; that is expected and acceptable, not a defect.

3. **The second layer is permanent.** Direct inter-document `Concept → Concept`
   association persists forever. It is *not* promoted out of existence.

4. **The Latin / Italian metaphor governs lifecycle.** The canonical ontology is
   *Latin* — dead, unchanging, human-gated, stable precisely because its terms
   must not drift (science and medicine need "hepatitis B surface antigen" to
   mean the same thing in 2040 as in 2020). The emergent layer is *Italian* —
   living, evolving, ungated, changing as usage changes, with no single conscious
   decision point. The **language model is the translator** that keeps the dead
   layer readable to the living layer as idioms drift.

5. **Compositional grounding, not whole-compound bridging.** An emergent
   compound is never linkable to an atomic ontology node as a whole — but it is
   always linkable through its parts.

6. **Recomposition completes decomposition.** A compound whose parts are anchored
   in an ontology *and* connected there by an edge forms a subgraph. That subgraph
   — not any single atom — is the compound's canonical equivalent, so the compound
   can be re-anchored to it. The anchor target is generalized from "atomic node"
   to "subgraph equivalent," discovered by Cypher relationship patterns rather
   than node lookups.

---

## 3. Terminology

| Term | Definition |
| --- | --- |
| **Emergent concept** | A `Concept` in the Librarian's own KG with no definitive canonical anchor; it lives in the living layer and bridges directly to other concepts. |
| **Canonical concept** | A `Concept` frozen into the stable layer via human gate, or an ontology node (`UMLSConcept`, `ConceptNetConcept`) itself. |
| **`bridge_status`** | Node property: `emergent` \| `canonical`. The lifecycle state. |
| **`provenance`** | Node property: how an emergent concept was born — `seed` \| `corpus-mined` \| `llm-bootstrap`. |
| **Seed** | An explicitly curated bootstrap concept (e.g. "work restrictions") inserted without any `SAME_AS`. |
| **Compositional grounding** | Persisting a compound's decomposition (head noun + modifier) as first-class edges to lower-granularity concepts that *do* have coverage. |
| **Recomposition** | The inverse of decomposition: re-assembling a compound's meaning from its parts plus the ontology edge that connects them, and tagging that composite meaning back onto the compound. |
| **Subgraph equivalent** | A compound's canonical anchor expressed as a multi-node structure (head + modifier + connecting edge) in ConceptNet/UMLS, rather than a single atomic concept. |
| **Reified anchor** | A Librarian-side `:Anchor` node that reifies *what* a `SAME_AS` points at, because `SAME_AS` must terminate on a node. Not an ontology node. Two kinds: `:Reading` (one sense — type- or context-scoped — of a polysemous concept) and `:CompositeAnchor` (a subgraph equivalent). |
| **Reading** | An `:Anchor` reifying one sense of a polysemous concept, keyed by a sense discriminator (`concept_type` or co-extraction `sense_terms`); carries the `SAME_AS` for that sense. |
| **Composite anchor** | An `:Anchor` reifying a subgraph equivalent (head + modifier + connecting edge) so `SAME_AS` can point at the structure rather than a single atom. |
| **Second layer** | The permanent set of direct inter-document `SIMILAR_TO` (and compositional) edges, independent of any ontology. |

---

## 4. Data model

### 4.1 New `ConceptNode` fields (`models/knowledge_graph.py:65`)

Add these fields to the `ConceptNode` dataclass (and their `to_dict`/`from_dict`
round-trips):

```python
bridge_status: str = "emergent"      # "emergent" | "canonical"
provenance: Optional[str] = None     # "seed" | "corpus-mined" | "llm-bootstrap" | "materialized-for-grounding"
scope: str = "private"               # "public" | "private"
owner_id: Optional[str] = None       # owning user for private concepts; null for public/seed
```

`bridge_status` defaults to `emergent`. A concept becomes `canonical` only by the
human gate (Section 5.4) or by construction as an ontology node. A `SAME_AS`
edge to UMLS/ConceptNet does **not** flip `bridge_status`: anchoring is a
semantic-equivalence claim, not a freeze. A colloquial term that happens to mean
the same thing as a UMLS concept remains a living, evolving, ungated term — and
therefore stays `emergent`. `bridge_status` is a lifecycle flag, orthogonal to
whether the node is anchored.

### 4.2 New Neo4j node properties

Persisted on the `Concept` node (write path at `celery_service.py:3555`,
`:3584`):

| Property | Type | Index | Notes |
| --- | --- | --- | --- |
| `bridge_status` | string | range index | `emergent` \| `canonical` |
| `provenance` | string | range index | `seed` \| `corpus-mined` \| `llm-bootstrap` \| `materialized-for-grounding`, null for canonical |
| `scope` | string | range index | `public` \| `private`, set at birth, inherited from the source content (conversation or upload) |
| `owner_id` | string | range index | owning user for `private` concepts; null for `public`/`seed` — enforces "no one but that user" (§5.6) |

The existing `concept_type` index (`neo4j_client.py:285`, on `c.type`) is
unaffected; `bridge_status` and `scope` are orthogonal to `concept_type`.

**Scope-aware identity.** A concept's identity is `(name_lower, scope)` — the
case-normalized surface form plus scope — so a private "light duty" and a
public "light duty" are distinct nodes, and wholesale deletion of private
content never contaminates the shared KG (§5.6). The old stopword-stripped
`_normalize_concept_name` slug is *not* used for identity, because it over-merges
distinct senses ("work restrictions" and "restrictions for work" both slug to
`work_restrictions`); identity keys on the raw `name_lower` instead.

```cypher
CREATE CONSTRAINT concept_scope_unique IF NOT EXISTS
FOR (c:Concept) REQUIRE (c.name_lower, c.scope) IS UNIQUE
```

**`concept_id` demoted to a derived surrogate.** `concept_id` is no longer
identity but a derived convenience key: `f"{scope}:{name_lower}"` (e.g.
`public:light duty`), recomputed from the identity at write time. Because the
value remains unique and is still what the ~40 retrieval sites `MATCH` on, the
read path is unchanged — those sites keep working with no read-site re-keying.
(Audited 2026-09-08: no read site *parses* `concept_id` — all treat it as an
opaque MATCH/dict key — so the read path is genuinely unchanged. One
*construction* site, `_link_acronym_expansions` (`kg_builder.py:1242-1245`),
hardcodes the old `{type}_{normalized}` shape to build in-memory lookup keys
(`acronym_...`, `entity_...`, `multi_word_...`); it must be re-keyed to
`(name_lower, scope)` or it silently misses.)
`concept_id_unique` is re-keyed during migration (the value shape changes) but
the constraint itself survives as a uniqueness check on the derived surrogate,
not identity.

**Migration hazard (verified 2026-09-06).** `concept_id` is type-prefixed
(`{type}_{normalized}`), so the same surface name extracted by different
extractors becomes multiple nodes sharing one `name_lower` — all public today.
Against the live graph, 41,677 `name_lower` values are duplicated across 94,169
nodes (e.g. `"izenman"` → `person_`/`code_term_`/`org_`; `"artificial
intelligence"` → `multi_word_`/`org_`). The `(name_lower, scope)` constraint
therefore **cannot be created until those duplicates are merged** (dedup by
`name_lower`, earliest-wins provenance), and `concept_id_unique` is re-keyed
to the derived surrogate (`{scope}:{name_lower}`). The write path stops keying
MERGE on `concept_id` alone.

The merge is a **single atomic pass** (Phase 1 step 3), not a blind
earliest-wins collapse: each duplicate's type is stamped onto its
`EXTRACTED_FROM` edges as `r.concept_type` before those edges are re-pointed to
the survivor, and the survivor is **re-embedded with the pinned model** (§4.4)
rather than inheriting one of N divergent vectors. The *cross-chunk* type split
is recoverable from the graph (each `{type}_`-prefixed node carries its own
edges); only the *within-chunk* minority type — dropped by the per-chunk dedup
(`kg_builder.py:919-929`) before anything was written — is irrecoverable, and
was lost before this spec existed.

### 4.3 New edge types: compositional grounding

Two `Concept → Concept` edges, produced directly by the dependency parse:

```
(compound:Concept)-[:HAS_HEAD]->(head:Concept)
(compound:Concept)-[:HAS_MODIFIER]->(modifier:Concept)
```

"work restrictions" → `HAS_HEAD` → "restrictions", `HAS_MODIFIER` → "work".

The head and modifier are Librarian `Concept` nodes, **not** `ConceptNetConcept`
or `UMLSConcept` nodes. They may themselves carry `SAME_AS` anchors to an
ontology, but the grounding edge terminates on a `Concept`. Implication: the
parts must already exist as `Concept` nodes (extracted from a document or
seeded). If "restrictions" or "work" was never materialized, compositional
grounding mints it first with `provenance = "materialized-for-grounding"` — a
bare Librarian `Concept` carrying no `EXTRACTED_FROM` and possibly no embedding
— and that part is itself possibly emergent (the recursion is inherent, not an
error). As a background process (zero-latency UX), the minted part is then
connected to existing concepts by embedding similarity or subgraph equivalent
(§4.5), so it does not stay bare.

**Part lookup crosses scope; identity does not.** A `HAS_HEAD`/`HAS_MODIFIER`
edge is a *reference*, not a merge. Grounding a private compound looks up the
part in **public scope first** and reuses it if present; a private part is
minted only when no public one exists. This keeps the KG from filling with
per-document private copies of common nouns ("work", "restrictions") while the
`(name_lower, scope)` identity still keeps the private compound and the public
part distinct nodes (§5.6).

These are **grounding** edges, not semantic relations. Their purpose is to let
the compound reach canonical anchors *through its parts*, not to surface chunks
directly. They are intentionally **not** added to the retrieval traversal lists
(`PRIORITY_RELATIONSHIP_TYPES`, `CLINICALLY_RELEVANT_RELATIONSHIPS`) — see
Section 6.2.

**Per-chunk type on `EXTRACTED_FROM`.** The evidence edge
`Concept -[:EXTRACTED_FROM]-> Chunk` currently carries only `created_at`
(`celery_service.py:3638`). It gains `r.concept_type`, preserving the
extractor's per-chunk type guess: when the same surface form is extracted as
different types in different chunks ("izenman" as `PERSON` vs `ORG`), the edge
records which type each chunk supports. The type is a per-chunk *fact*, not a
node property to collapse away — the node keeps a single dominant
`concept_type`, while the edges carry the full distribution. This split is what
makes polysemy explicit (§4.5) instead of silently overwriting the minority
type.

`concept_type` is the **stored `ConceptNode.concept_type` value** — an
uppercase, *heterogeneous, open-ended* tag, not a closed enum. It is the union
of six extractor vocabularies: spaCy NER labels (`PERSON`, `ORG`, `GPE`, `LOC`,
`PRODUCT`, `WORK_OF_ART`, `EVENT`, `LAW`, `NORP`, `FAC`, ...), the pattern types
(`CODE_TERM`, `MULTI_WORD`, `ACRONYM`), the UMLS literal (`UMLS`), the `ENTITY`
fallback, and the per-domain LLM type sets (`GUIDELINE`, `POLICY`,
`RESTRICTION`, `API`, `STATUTE`, ...). The lowercased `_`-suffixed forms
(`person_`, `org_`, `code_term_`) appear *only* in the old `concept_id` prefix
(`concept_type.lower() + "_"`), which §4.2 demotes away — they are not a
separate vocabulary.

### 4.4 Vector indexing

Emergent seeds participate in `concept_embedding_index` (768-dim cosine,
`neo4j_client.py:301`) exactly like any other `Concept`. This is what makes the
idiom → seed match work: the embedding of "I can't go back to my job yet"
top-hits the seed's embedding and `SIMILAR_TO`-bridges to it (query-time lookup
at `query_decomposer.py:730`).

**Pinned-model invariant.** Cosine similarity between two vectors is only
meaningful if both were produced by the same embedding model. One pinned model
version produces every vector in the index — the ingestion-time corpus, the
`seed`, the `llm-bootstrap`, and the `materialized-for-grounding` parts. There
is no cross-model comparison, ever. A model upgrade is a **full-index re-embed
event**: the surviving node after a merge is re-embedded with the pinned model
(it does not inherit one of N divergent vectors), and grounding-by-similarity
embeds the minted part with the same pinned model before the ANN query. No
vector is ever compared against a vector from a different model.

**Private embeddings are owner-scoped.** Private concepts do **not** live in
the shared `concept_embedding_index` (§5.6): their vectors sit in a per-owner
(or per-tenant) index, so a private concept can never surface to another user
through an ANN match. Private retrieval queries the owner's index and the public
index, then merges them under the "private first" ordering (§5.6).

### 4.5 Subgraph equivalent — the anchor that is a structure, not a node

A compound whose head and modifier are **both** anchored to the same ontology
**and** connected there by a *typed path* is not fully orphaned: its canonical
equivalent is that path — the specific subgraph of constituent concepts joined by
specific, directed edges — not any single atom. The base case is a direct edge
(head → modifier); longer paths are admissible only if *faithful* — but the
empirical check below shows multi-hop paths are overwhelmingly spurious, so in
practice the direct edge is the only reliably-faithful case. ConceptNet and UMLS
are graphs, not bags of nodes, so this is queryable with a
relationship pattern, not a node lookup. The direct-edge case is **already
implemented**: `get_relationships_for_concepts` (`conceptnet_validator.py:129`)
matches `(a)-[r:ConceptNetRelation]->(b)` between pinned names.

```cypher
MATCH (h:ConceptNetConcept)-[r]->(m:ConceptNetConcept)
WHERE h.name IN ['work'] AND m.name IN ['restriction']
RETURN type(r)
```

If such a path exists, the compound can be re-anchored to it. The path must be
*pinned* — specific nodes and specific edge types — never an existential
traversal: an unbounded "any path" query degenerates in ConceptNet's dense graph,
where nearly every pair of concepts is connected by *some* path. Pinning is what
keeps "work → restriction → types" from ever matching "dietary → restriction →
types"; the two are distinct paths because their pinned nodes differ.

**Empirical check (2026-09-04, against the loaded graph).** For the running
example the query returns empty: there is no `work-[ConceptNetRelation]->`
`restriction` edge, nor its reverse. The only intra-part edges are inflectional
(`restrictions-[RelatedTo|FormOf]->restriction`) and `work` self-loops. Short
paths *do* exist (`work→act→restriction`, `work→worker→person→restrictions`,
`work→network→network neutrality→restriction`), but they are semantically
spurious — they join the parts through incidental intermediates, not through a
modifier-head relation. The `restriction` node's dominant sense is molecular
biology (`DerivedFrom → "restriction enzyme"`, `HasContext → biology`) plus a
general constraint/rule sense; it has a dietary context (`RelatedTo → diet`,
`5 2 diet`, `cheat meal`) and a legal one (`curfew`, `law`, `regulation`) but
**no work/employment context**. So "work restrictions" is *not* rescued by §4.5 —
it remains the residual orphan of §1, and its value comes from the second layer
(grounding + direct `SIMILAR_TO`), not from any ontological subgraph.

Implication: §4.5 is real but narrow — it fires only where the ontology *already*
connects the parts with a semantically-faithful edge. *(Resolved.)* `SAME_AS` is
restricted to **faithful subgraph matches only** — direct, existing ontology
edges between the pinned parts. The LM does **not** reconstruct missing pathways
under `SAME_AS`: a reconstructed path has no ground truth, so its terminal
concepts (e.g. one of `restriction`'s actual neighbors — `curfew`, `age limit`,
`diet`, `price control`) may not be a work restriction at all, and asserting
identity to them corrupts the one edge type whose precision retrieval depends
on. LM-reconstructed structure stays on the emergent side (`llm-bootstrap`,
`SIMILAR_TO`, grounding), never `SAME_AS`.

**Why the asymmetry — checkable vs. uncheckable claims.** The division is not
"safe vs. unsafe" but "checkable vs. uncheckable." Evidence edges
(`EXTRACTED_FROM`, `HAS_HEAD`/`HAS_MODIFIER`) point at an independent source of
truth: you can audit an `EXTRACTED_FROM` edge against its chunk's text in
Postgres, or re-run the dependency parse behind `HAS_HEAD`. A model
hallucination there is mechanically detectable. A `SAME_AS` identity claim has
no such oracle — there is nothing in the system against which to check "work
restrictions means the same as curfew," because the reconstruction exists
precisely where the ontology is silent. So the LM is confined to the checkable
channels, where its mistakes are recoverable, and barred from the uncheckable
one, where they are not.

**Representation — the reified anchor.** `SAME_AS` is a *transitive* identity
relation: a single node holding two `SAME_AS` edges to non-identical targets
forces those targets to be equal by transitivity. So whenever a concept has more
than one canonical target — a subgraph, or multiple type-dependent senses — the
target is reified as an `:Anchor` node (a Librarian-side construct, *not*
injected into ConceptNet/UMLS — no cartridge error). No single `Concept` ever
carries two competing `SAME_AS` edges; the identity claim terminates on the
`:Anchor`. The `:Anchor` inherits the `scope` and `owner_id` of its `Concept`
at materialization, so a private concept's readings and subgraph anchors are as
private as the concept itself. Two kinds:

- **Composite anchor** (`kind: "composite"`) — a subgraph equivalent:

  ```
  (:Concept {name: "work restrictions"})
      -[:SAME_AS]->(:Anchor {kind: "composite", relationship_type: "RelatedTo"})
          -[:HAS_PART]->(:ConceptNetConcept {name: "work"})
          -[:HAS_PART]->(:ConceptNetConcept {name: "restriction"})
  ```

  `relationship_type` records the ontology edge that connects the parts; the
  parts themselves are the real ontology nodes.

- **Reading** (`kind: "reading"`) — one sense — *type-* or *context-scoped* —
  of a *polysemous* concept. When the same surface form is extracted as different types in
  different chunks, `r.concept_type` on `EXTRACTED_FROM` (§4.3) preserves the
  split, and each type is reified as its own sense with its own `SAME_AS`:

  ```
  (:Concept {name_lower: "izenman", scope: "public"})
      -[:EXTRACTED_FROM {concept_type: "PERSON"}]->(:Chunk A)
      -[:EXTRACTED_FROM {concept_type: "ORG"}]   ->(:Chunk C)
  (:Concept)-[:HAS_READING]->(:Anchor {kind: "reading", concept_type: "PERSON"})
      -[:SAME_AS]->(:ConceptNetConcept {name: "izenman person sense"})
  (:Concept)-[:HAS_READING]->(:Anchor {kind: "reading", concept_type: "ORG"})
      -[:SAME_AS]->(:ConceptNetConcept {name: "izenman org sense"})
  ```

  A bare `Concept → SAME_AS → ontology` edge on both senses would assert that the
  person-sense and org-sense are identical, which is false. The reading breaks
  that: identity lives on the sense, not the surface form. Retrieval walks
  `Concept → HAS_READING → Anchor → SAME_AS → ontology` and can prefer the
  reading whose `concept_type` matches the query context.

  When the polysemy is **same-type** — the surface form keeps one `concept_type`
  but means different things in different contexts — the discriminator is the
  **co-extraction neighborhood** (§5.5): the concepts extracted alongside the
  surface form in the same chunk, keyed on the reading as `sense_terms`. "light
  duty" is always one noun phrase, but the medical sense co-extracts with "work
  restrictions"/"convalescence" while the trucking sense co-extracts with
  "truck"/"freight". The reading is keyed by `sense_terms` instead of
  `concept_type`, and the `SAME_AS` is materialized **only when the ontology
  actually supports it** — ConceptNet has `duty → work` (IsA) but no
  `duty → truck/vehicle/freight/cargo` edge, so the medical reading carries a
  `SAME_AS` while the trucking reading stays unanchored rather than asserting a
  false identity. A reading with no `SAME_AS` is still legitimate: it partitions
  the sense so retrieval can match the right one. *(This sense-scoped path is
  **deferred to a later phase** — the co-extraction clustering mechanism is not
  yet pinned; see §8.)*

**Promotion.** The semantic `SIMILAR_TO` link that first associated the compound
with its parts is *promoted* to `SAME_AS` once the subgraph match is verified —
an identity claim, but to a subgraph equivalent rather than an atomic node. The
promotion does **not** flip `bridge_status` (consistent with §4.1): anchoring to
a subgraph is still anchoring, not freezing.

---

## 5. Lifecycle

### 5.1 Birth — orphaned

A seed enters as an `emergent` concept, typed provisionally (LLM/bootstrap), with
`provenance` set and **no `SAME_AS`** to anything. It is a single node — never
duplicated across ontologies, never confined to a domain (that would be the
"cartridge" error).

### 5.2 Direct bridging — immediately useful

The seed immediately accrues corpus-local `SIMILAR_TO` edges to other concepts
(and to the idiomatic variants that embed near it). This is the direct
inter-document linkage, and it is what keeps the concept useful for
conversational bridging from day one, independent of any ontology.

### 5.3 Compositional grounding — the promotion that always works

"Promotion" does **not** mean "adopt the compound into ConceptNet" (which has no
atomic target). It means compositional grounding: the dependency parse already
decomposes the compound into head + modifier, so every emergent concept is born
decomposable. The head and modifier are lower-granularity and far more likely to
have canonical anchors, so "link the parts" always has a target.

Grounding is the floor, not the ceiling. When the anchored parts are *also*
connected by an edge in the ontology, the compound gains a stronger outcome than
per-part grounding: a `SAME_AS` to the subgraph equivalent (§4.5). Decomposition
and recomposition are duals — the same dependency parse that splits the compound
provides the parts that, rejoined across the ontology's own edge, yield the
composite meaning.

### 5.4 Freezing — rare, human-gated

Only when a term has become stable enough to *need* freezing does it cross into
the canonical layer, by explicit human gate. The emergent layer is **not**
depleted by this; it persists as the living layer. "Promotion" is therefore a
misnomer — the emergent concept does not leave; a frozen *copy* of its meaning is
what enters the ontology.

### 5.5 Provenance values

- `seed` — explicitly curated, inserted out-of-band (like the "work restrictions"
  example, or the existing `DomainAbbreviation` seeding in
  `scripts/seed_domain_abbreviations.py`).
- `corpus-mined` — produced by the normal extraction pipeline
  (`kg_builder.py`), found to have no ontological coverage, and retained as
  emergent rather than discarded. The mining mechanism is a **fusion**, not the
  LM alone: `extract_all_concepts_async` (`kg_builder.py:890`) runs spaCy NER,
  Ollama LLM (Gemini failover), UMLS n-gram lookup, and regex concurrently, then
  dedupes by normalized name keeping the highest confidence. "corpus-mined"
  therefore means "born from any of those four extractors, then left unanchored."
  This population already exists today — unanchored concepts are persisted
  silently; the tag only makes that state explicit.
- `llm-bootstrap` — generated at **query/conversation time**, but not blindly:
  when the live conversation surfaces an idiom that no document or ontology
  supplies, the model does **not** silently mint a node. It is transparent about
  not understanding the idiom, and offers a **ranked candidate list** built from
  two sources concatenated: (1) the KG concepts whose embeddings best match the
  idiom — the closest existing seeds/idiomatic concepts; and (2), when the idiom
  has **no close embedding** (a true orphan), an **LM-generated set of composite
  candidates** — decompositions of the idiom into head + modifier — each
  **pre-screened through ConceptNet** for actual viability (both parts present
  and connected by a faithful edge, §4.5). Only ConceptNet-viable composites are
  offered, so a chosen composite maps to a real subgraph equivalent. The chosen
  interpretation drives two things at once: (a) a **real-time phrase
  substitution** in the prompt, so the system answers without delay using the
  concept the user already selected; and (b) a **background linkage pass** that
  wires the minted node to the choice — `SIMILAR_TO` to a chosen Librarian
  concept, or `SAME_AS` to a chosen (pre-verified) subgraph equivalent (§4.5).
  If both candidate sources come back empty, the system **asks the user to
  rephrase the idiom** and proceeds with query resolution on whatever idioms
  *are* resolvable. The minted
  `Concept {name: "light duty", provenance: "llm-bootstrap"}` is embedded into
  `concept_embedding_index` and, over time, accrues the `SIMILAR_TO` edges the
  user's choices implied. This is the living layer *in motion* — it grows as the
  conversation happens, but every growth step is anchored to a human choice, not
  a hallucinated guess.
- `materialized-for-grounding` — minted by compositional grounding (§4.3) when a
  compound's head or modifier was never itself extracted or seeded: a bare
  Librarian `Concept` created solely to give `HAS_HEAD`/`HAS_MODIFIER` a target,
  carrying no `EXTRACTED_FROM` and possibly no embedding. It is then connected,
  as a background process, to existing concepts by similarity or subgraph
  equivalent (§4.5), so it does not stay bare.

  The provenances differ by *who* creates the node and *when*:

  | provenance | created by | when |
  | --- | --- | --- |
  | `seed` | human, out-of-band | offline, in a seed script |
  | `corpus-mined` | extraction pipeline | at ingestion, from document text |
  | `llm-bootstrap` | the model, guided by a user choice | at query/conversation time, on first encounter |
  | `materialized-for-grounding` | compositional grounding | at extraction, when a part is missing |

  The `llm-bootstrap` row is what makes the living layer *alive*: the graph
  sharpens with each conversation and never forgets — every minted node is a
  durable `Concept` (not the transient expansion of
  `_expand_domain_abbreviations`), so the next time the idiom surfaces the
  concept is already there. (Persistence is currently gated by the
  orphan-cleanup path — see §8.)

  **Earliest wins.** `provenance` is set once, at first birth, and never
  overwritten — a concept cannot be duplicated, even if the same surface form
  later surfaces with a different connotation. Divergent senses fork in two
  ways, neither of which re-provenances the lexical node:

  - **Type fork** — through a *reading*: when the same surface form is
    extracted as different `concept_type`s in different chunks ("izenman" as
    `PERSON` vs `ORG`), each type is reified as an `:Anchor` reading (§4.5),
    and the per-chunk type is preserved on `EXTRACTED_FROM.concept_type`
    (§4.3).
  - **Sense fork** *(deferred to a later phase)* — through a
    *co-extraction-neighborhood reading*: when a single surface form keeps one
    `concept_type` but means different things in
    different contexts, the sense is carried structurally by the concepts
    extracted alongside it in the same chunk. "light duty" is one noun phrase,
    but the medical sense co-extracts with "work restrictions"/"convalescence"
    while the trucking sense co-extracts with "truck"/"freight". Each
    neighborhood is reified as an `:Anchor {kind: "reading", sense_terms}`
    (§4.5) — the divergent meaning lives in the reading, not in a modifier
    branch, because "light duty" is not a compositional compound ("duty" is the
    head; "light" is not the sense-carrier).

  The lexical node keeps its original provenance; the reading is where the
  divergent meaning lives.

### 5.6 Content privacy scope (public | private)

Every piece of content — a **conversation** or an **uploaded document** — is
**private by default**, and the choice is **irreversible**: a public item cannot
later be made private, nor a private one public. The scope governs where the
concepts minted from it live and who can delete them. It does not matter whether
a concept is `corpus-mined` or `llm-bootstrap`: scope is inherited from the
source content, not from the birth mechanism. `seed` concepts are
human-curated out-of-band and default to `public`;
`materialized-for-grounding` parts reuse an existing **public** part when one
exists and mint a private part only when it does not (§4.3) — grounding edges
cross scope, node identity does not. Content that predates the feature is
unaffected: it remains **public** before and after implementation.

**The checkbox.** New content starts with **Private checked**. To publish, the
user unchecks it — and the moment it is unchecked, the checkbox **greys out**,
locking the choice to public. If it is never unchecked, it greys out **before
the upload or conversation begins**, locking the choice to private. Either way
the box is non-interactive once decided: private is the safe default, public is
an explicit opt-in, and the greyed-out box is the UI's guarantee that the
selection cannot be reversed after the fact.

- **Private.** Concepts minted from a private conversation or upload carry an
  `owner_id` and are self-contained to that user's segment of the KG — no one
  but that user can access them. Their embeddings live in a per-owner vector
  index, not the shared `concept_embedding_index` (§4.4), so a private concept
  cannot leak to another user through an ANN match. Learning still happens, but
  the "currency" of any idiom or axiom minted there ends at the content's
  borders: it does not extend into any other conversation or upload, and if that
  extension is wanted after the fact, the only recourse is to begin again from
  scratch (the concept cannot be retroactively published). The payoff is clean
  separation: when the private content is deleted, everything — including its
  concepts — is removed in its entirety, and the impact is felt solely by that
  user's private segment.
- **Public.** The owner retains ownership of their *public content*, but not of
  the public KG, which is owned by everyone. Public content contributes its
  concepts to the shared layer, where they are subject to the normal
  earliest-wins and orphan-cleanup rules — the contributor cannot unilaterally
  delete a concept the shared KG has since adopted.

**Scope-filtered traversal.** Private concepts are isolated not only at the
embedding layer (§4.4) but at the *graph-traversal* layer: any hop that would
land on (or expand through) a `scope=private` node not owned by the querying
user is dropped, in both directions. This is mandatory because cross-scope
edges are deliberate — a private compound reuses public parts (§4.3) and a
private `llm-bootstrap` links to public concepts (§5.5) — and each such edge is
a reverse path from the public side back to the private node. Without the
filter, "no one but that user can access them" is false the moment grounding
mints its first cross-scope edge.

This resolves the multi-provenance deletion problem: a concept that would be
born in both private content and the public corpus never merges across the
boundary — the private copy and the public copy are distinct nodes, keyed by
`(name_lower, scope)` (§4.2), so the private one can be deleted without
the consent of the public owners, and vice versa. The rule of the road is
intuitive (you own your private segment; you share the public KG), but the
limitations of each scope must be clearly posted in the UI to avoid
misunderstanding.

**Private first, public for richness.** When a concept exists in both scopes,
the private copy **outranks** the public copy within that private content's
retrieval context: private concepts always sort first, and public concepts are
still included — just behind them, for richness. Mechanically this is a merge
of two ANN result sets — the owner's private index and the shared public index
(§4.4) — ordered private-first. Nothing is overridden in the KG — both copies
persist unchanged — this is purely a retrieval-ordering preference for the
private content, not a mutation of either node.

---

## 6. Retrieval implications

### 6.1 `SIMILAR_TO` is *not* deprioritized (verified)

`SIMILAR_TO` already sits on equal footing with `IS_A`/`PART_OF`/`CAUSES`:

- `PRIORITY_RELATIONSHIP_TYPES` — `kg_retrieval_service.py:268` (and `SimilarTo`
  at `:281`)
- `CLINICALLY_RELEVANT_RELATIONSHIPS` — `relationship_traverser.py:52` (and
  `SimilarTo` at `:57`)

The surfacing problem is not relationship-type weight. It is two concrete,
fixable levers:

1. **Match threshold.** `SIMILAR_TO` edges are created at cosine `0.85` both
   within-document (`kg_builder.py:1401`, `:1443`) and in the UMLS bridge
   (`umls_bridger.py:157`). `0.85` is too high for idiomatic paraphrase — the
   idiom→seed match ("I can't go back to my job yet" → "work restrictions")
   will not reliably fire.
2. **Grounding.** A bare bootstrap seed with no `EXTRACTED_FROM` edges returns no
   chunks no matter how high it ranks. It only surfaces through a 2-hop path
   (`query → seed → document concept → chunk`), which the retrieval is tuned
   against: `hop_distance_decay = 0.5` (`kg_retrieval_service.py:324`) and
   `_MAX_CONCEPTS_FOR_1HOP = 10` (`:255`).

### 6.2 Fixes

- **Adaptive match threshold.** Lower/adapt the idiomatic-paraphrase match
  threshold for the emergent layer (a separate `emergent` threshold below the
  `0.85` canonical bar), so the living-layer match fires without re-opening the
  canonical layer to noise.
- **Ground every seed.** A seed's value is realized by being *extracted and
  grounded*: the noun-chunk "work restrictions" is persisted with its own
  `EXTRACTED_FROM` edges whenever it appears in a document. Once grounded, the
  seed carries its own chunks and the 2-hop disadvantage mostly disappears
  (`query → seed → chunk` becomes direct). This is **retroactive**: chunk
  full-text is authoritative in Postgres `knowledge_chunks.content` (with a GIN
  FTS index) — the Neo4j `Chunk` node is a thin mirror carrying no content — so
  a backfill pass selects every chunk containing the phrase and MERGEs
  `EXTRACTED_FROM`. The same holds for `SIMILAR_TO`: embeddings already live in
  `concept_embedding_index` (a Neo4j 768-dim vector index), so a backfill queries
  it with **ANN top-k** — not brute-force pairwise cosine — and MERGEs the
  returned semantic edges. The two are complementary —
  literal-phrase grounding catches exact matches; `SIMILAR_TO` catches the
  idiomatic paraphrases that never contain the literal term.
- **Compositional edges are for grounding, not traversal.** `HAS_HEAD` /
  `HAS_MODIFIER` are excluded from the priority traversal lists to avoid
  transitive fan-out (the same rationale already documented in
  `scripts/seed_domain_abbreviations.py`: vocabulary bridges that ride the same
  edges as true acronyms overwhelm the phrase cap).

---

## 7. Implementation plan

Phased, each independently shippable.

**Retroactive backfill is universal.** The corpus and KG already exist, so every
phase below ships with a one-shot backfill script (the pattern is already in
`scripts/enrich_rationales.py`, `scripts/embed_conceptnet.py`,
`scripts/cleanup_orphan_conversation_chunks.py`). There is no green-field phase:
schema changes default existing nodes to `emergent`; grounding and `SIMILAR_TO`
are backfilled from Postgres chunks plus the existing embedding index; and
compositional edges are re-derived by reprocessing the chunk text the concepts
were extracted from.

### Phase 0 — Orphan-cleanup predicate (privacy safety net)

1. Fix the orphan-cleanup predicate (`document_manager.py:825`,
   `privacy.py:402`) to be provenance- and privacy-scope-aware *before* any
   minting phase ships. Preserve: `bridge_status = 'canonical'`, and
   `provenance IN ['seed', 'llm-bootstrap', 'materialized-for-grounding']`
   (any scope); preserve public `corpus-mined` only while its evidence
   survives. Public scope is *not* blanket immunity. Delete only:
   `corpus-mined` whose evidence is gone, and private-scope concepts — and then
   only when the specific private content that minted them is deleted (§5.6).
   Without this, the very next content deletion erases every minted node.
   Phase 0 and Phase 1 steps 2–3 ship as **one atomic deploy**: the predicate
   references fields (`bridge_status`, `provenance`, `scope`) that Phase 1
   introduces, and the backfill must land with or before the predicate — a
   predicate that runs against a graph where those fields are still NULL would
   delete the entire emergent layer.

### Phase 1 — Schema and model

1. Add `bridge_status` + `provenance` + `scope` + `owner_id` to `ConceptNode`
   (`models/knowledge_graph.py:65`), including the full provenance enum
   (`seed` | `corpus-mined` | `llm-bootstrap` | `materialized-for-grounding`),
   `scope` (`public` | `private`), and `owner_id` (owning user for private
   concepts).
2. Add the Neo4j properties + range indexes alongside the existing `concept_*`
   indexes (`clients/neo4j_client.py:281-301`, `database/init_neo4j.cypher`).
   Declare the `:Anchor` node type (`kind: "composite" | "reading"`) with its
   supporting properties (`relationship_type`, `concept_type`, `sense_terms`,
   `scope`, `owner_id`) and the `HAS_READING` / `HAS_PART` edge labels (§4.5).
   `:Anchor` inherits `scope` + `owner_id` from its `Concept` at materialization
   (§4.5).
3. **Dedup migration (single atomic pass, §4.2).** Backfill
   `bridge_status = 'emergent'`, `provenance = 'corpus-mined'`,
   `scope = 'public'`, and `owner_id = NULL` for the 94,169 existing nodes.
   Stamp `r.concept_type` on **all** `EXTRACTED_FROM` edges — duplicated
   `name_lower` nodes recover the true per-chunk type (each source node's type
   onto its own edges, before re-pointing), unique nodes stamp their single
   `concept_type` uniformly (no recovery — it was already uniform). Then, for
   each `name_lower` with multiple nodes, in one pass: re-point those edges to
   the survivor, re-embed the survivor with the pinned model (§4.4), recompute
   the survivor's `concept_id` as the derived surrogate `f"{scope}:{name_lower}"`
   (§4.2), and delete the superseded nodes. Only after this pass declares the
   composite uniqueness constraint `(name_lower, scope)` and re-keys
   `concept_id_unique` to the derived surrogate (§4.2).
4. Change the Concept `MERGE` write path
   (`services/celery_service.py:3555`, `:3584`) to key on `(name_lower, scope)`
   so the composite constraint is respected (§4.2), write `scope` + `owner_id`
   on every node, persist `r.concept_type` on the `EXTRACTED_FROM` edge write
   (`services/celery_service.py:3615-3643`) so the per-chunk extractor type
   survives going forward (§4.3), and recompute `concept_id` as the derived
   surrogate `f"{scope}:{name_lower}"` on every write — `concept_id` is demoted
   to a derived key, not the identity (§4.2). Hardcode `scope='public'`
   (`owner_id=NULL`) through Phases 1–5 — the private-by-default mechanism
   activates in Phase 6, and the dataclass `"private"` default must not leak
   before then. Re-key `_link_acronym_expansions` (`kg_builder.py:1242-1245`)
   from the old type-prefix lookup keys to `(name_lower, scope)` (§4.2).

### Phase 2 — Compositional grounding at extraction

1. In the extraction path (`kg_builder.py`), capture the dependency head +
   modifier for each noun chunk. spaCy already exposes `token.head` / `dep_`;
   the `noun_chunks` are already enumerated (`relevance_detector.py:475`,
   `:926`; `ner_extractor.py:202`).
2. Emit `HAS_HEAD` / `HAS_MODIFIER` edges for multi-word compounds, linking the
   compound to the (lower-granularity) head/modifier concepts.
3. When a head or modifier has no existing `Concept`, look it up in **public
   scope first** (§4.3) and reuse it; only if absent, mint it with
   `provenance = "materialized-for-grounding"` and embed it with the **pinned
   model** (§4.4). Then connect it (as a background process) to existing
   concepts by similarity or subgraph equivalent, materializing an
   `:Anchor {kind: "composite"}` with `HAS_PART` edges when the match is a
   multi-part structure (§4.5) — zero-latency at extraction, enrichment
   deferred.
4. Reify polysemous senses: when a concept's `EXTRACTED_FROM` edges carry more
   than one distinct `concept_type`, materialize an
   `:Anchor {kind: "reading", concept_type}` per type during background
   enrichment (§4.5), each holding its own `SAME_AS` — or none, when the
   ontology has no supporting edge for that sense — so no single `Concept`
   carries two competing identity claims. (Sense-scoped readings keyed by
   `sense_terms` are **deferred to a later phase** — the co-extraction
   clustering mechanism is not yet pinned, §8.)

### Phase 3 — Seed bootstrap path

1. Generalize the `DomainAbbreviation` seeding pattern
   (`scripts/seed_domain_abbreviations.py`) into an emergent-concept seeding
   path that writes a `Concept` node with `bridge_status=emergent`,
   `provenance=seed`, and an embedding into `concept_embedding_index`.
2. Keep `DomainAbbreviation` scoped to true acronyms (per its docstring); do not
   fold vocabulary bridges into it.

### Phase 4 — Retrieval tuning

1. Introduce an emergent-layer match threshold distinct from the canonical
   `0.85`.
2. Ensure seeds are grounded (`EXTRACTED_FROM`) before they participate in
   surface-time retrieval.
3. Verify `SIMILAR_TO` traversal is exercised for emergent matches (it already
   is — this phase is about threshold + grounding, not adding the edge type).
4. Generate a **small regression set** of idiomatic→seed query pairs with
   expected top-k outcomes (e.g. "I can't go back to my job yet" → "work
   restrictions" must rank in top-k). Threshold tuning is falsifiable against
   this set, not vibes-based (§8).

### Phase 5 — Provenance tagging + interactive bootstrap

1. Tag `corpus-mined` for extraction outputs that find no ontological coverage.
2. Add the `llm-bootstrap` hook for **query/conversation-time** scaffolding,
   guided by the user rather than blind. When query decomposition (or
   conversation handling) encounters an idiom that no document and no ontology
   supplies:
   - be transparent that the idiom is not understood, and offer a **ranked
     candidate list** — closest existing Librarian concepts by embedding,
     concatenated with LM-generated **composite candidates pre-screened through
     ConceptNet** for viability (§4.5), offered when the idiom has no close
     embedding;
   - on selection, perform a **real-time phrase substitution** in the prompt so
     the answer proceeds without delay; and
   - in the **background**, mint the `Concept` node
     (`bridge_status=emergent`, `provenance=llm-bootstrap`, embedding into
     `concept_embedding_index`) and wire it to the choice — `SIMILAR_TO` for a
     Librarian concept, `SAME_AS` for a pre-verified subgraph equivalent (§4.5)
     — so it persists (the graph "remembers" it for the next conversation);
   - if both candidate sources are empty, **ask the user to rephrase the idiom**
     and proceed with query resolution on the resolvable idioms.
   This is a *persistent* write, distinct from the transient term-expansion
   already in `_expand_domain_abbreviations` / `_find_semantic_matches`.

### Phase 6 — Content privacy scope (public | private)

1. Add a public/private scope to every conversation *and* upload: **private by
   default**, public via explicitly unchecking the Private checkbox, locked
   (greyed-out) once decided — unchecking locks immediately; leaving it checked
   locks before upload/conversation begins. Pre-existing content stays public
   (§5.6).
2. Key concepts by `(name_lower, scope)` (§4.2), stamp `owner_id` on every
   private concept, and isolate private-scope concepts from the shared KG so
   they can be deleted wholesale with their content (no shared-node
   contamination).
3. Give private concepts a **per-owner vector index**, separate from the shared
   `concept_embedding_index` (§4.4), so private embeddings never leak through
   an ANN match to another user.
4. Wire deletion: private-content deletion removes its concepts in entirety
   (including their private-index vectors); public content retains ownership of
   the content but not of the shared KG.
5. Post the limitations of each scope in the UI (private concepts do not extend
   beyond the content; public contributions are owned by everyone).
6. Implement "private first, public for richness" retrieval ordering: merge the
   owner's private index with the public index and sort private ahead of public
   (§5.6). Grounding parts reuse public-first and mint private only when absent
   (§4.3).
7. Enforce scope-filtered traversal: drop any graph hop into a `scope=private`
   node not owned by the querying user, in both directions (§5.6). This is the
   traversal-side complement to the per-owner vector index (step 3) —
   cross-scope edges exist by design (§4.3, §5.5), so embeddings-only isolation
   is insufficient.

---

## 8. Risks and open questions

- **Threshold choice.** The exact emergent-layer threshold needs empirical
  tuning against real idiomatic queries; too low re-introduces noise into a
  layer whose precision is currently its strength. Made falsifiable by the
  Phase 4 regression set (idiomatic→seed pairs with expected top-k outcomes)
  rather than vibes-based tuning.
- **Compositional edge traversal.** Whether `HAS_HEAD`/`HAS_MODIFIER` should ever
  be traversed at query time (e.g. to surface a compound given its head) is left
  open; the default is grounding-only.
- **Sense-scoped reading clustering (deferred).** The co-extraction-neighborhood
  reading (§4.5, §5.5) is specified in shape (`sense_terms` on `:Anchor`) but its
  mechanism is deferred: the chunk unit, `sense_terms` encoding, clustering
  algorithm/threshold, and retrieval-side matching are not yet pinned. Phase 2
  ships type-scoped readings only.
- **Subgraph match scope.** *(Resolved.)* The subgraph equivalent (§4.5) is
  defined by its *pinned* constituent nodes and typed edges, not by a hop radius
  — there is no arbitrary hop cap, and exact subgraph matching is unambiguous
  ("work → restriction → types" ≠ "dietary → restriction → types"). The
  discipline is pinned paths, never existential traversal. Absent a faithful
  (direct, existing) edge between the parts, there is **no** `SAME_AS` — the LM
  does not reconstruct a named path, because the terminal concepts of a
  reconstructed path are unverified and may not be the compound's meaning at all.
  LM-reconstructed structure stays on the emergent side (`llm-bootstrap` /
  `SIMILAR_TO`), not `SAME_AS`.
- **Reified anchor vs. canonical node.** `:Anchor` (composite or reading, §4.5)
  reifies what a `SAME_AS` points at and must not be mistaken for a canonical
  ontology node by downstream `SAME_AS` traversal (which currently assumes
  `UMLSConcept`/`ConceptNetConcept` targets). Retrieval that walks `SAME_AS`
  must handle the anchor class explicitly — including the extra
  `HAS_READING`/`HAS_PART` hop, and preferring the reading whose `concept_type`
  matches the query context.
- **Canonical default semantics.** *(Resolved.)* A `SAME_AS` to UMLS does **not**
  auto-flip `bridge_status`. Anchoring is semantic equivalence, not a freeze; a
  colloquial term that matches an ontology node by meaning stays `emergent`.
  `canonical` is reached only by human gate or by construction as an ontology
  node. This removes the Phase 1 ambiguity: `bridge_status` is a lifecycle flag,
  orthogonal to anchoring.
- **Ontology death.** The emergent layer is the resilience: if ConceptNet/UMLS
  cease maintenance, seeded/generated conventions must survive and retain the
  "linkages to the past" (whether to real ontology or to emergent). This is a
  property to preserve, not a feature to bolt on later.
- **Persistence of emergent nodes ("never forgets").** The orphan-cleanup pass
  (`document_manager.py:825`, `privacy.py:402`) deletes any `Concept` with no
  `EXTRACTED_FROM` and no incoming `SAME_AS` — which is exactly an ungrounded
  `seed`, a freshly-minted `llm-bootstrap` node, or a
  `materialized-for-grounding` part. The predicate is unaware of the new
  `bridge_status`/`provenance`/privacy-scope fields, so a document deletion
  would erase conversation memory. Fix: exempt whatever is worth preserving and
  delete only the rest. The preserve set is stated positively — canonical / seed / llm-bootstrap /
  materialized-for-grounding (any scope), plus public `corpus-mined` while its
  evidence survives — rather than "delete NULL-provenance." Public scope is not
  blanket immunity. Deletable: `corpus-mined` whose evidence is gone (document
  deletion), and private-scope concepts — the latter only when the specific
  private content that minted them is deleted (§5.6).
  The gate is on provenance and privacy scope, not `bridge_status`: the
  retroactive backfill (§7) fills `bridge_status` for all legacy content, so
  `bridge_status IS NULL` is never a meaningful discriminator. (Canonical nodes
  carry `provenance IS NULL` by §4.2.)
- **Two-tier memory (hollow nodes).** Preserving a node from orphan-cleanup keeps
  the *concept* but not its *evidence*: document deletion severs the concept's
  `EXTRACTED_FROM` edges and deletes its chunks, so the preserved concept can no
  longer surface its own content. It retains recognition (name/embedding still
  match the idiom) and indirect bridging (via surviving `SIMILAR_TO`/`SAME_AS` to
  concepts that still carry chunks, at the 2-hop decay penalty), but it becomes a
  hollow bridge, not a source. `llm-bootstrap` is the exception that proves the
  rule: its memory is conversational, not chunk-grounded, so its utility survives
  document deletion — though a *private*-scope bootstrap is removed in entirety
  when its private content is deleted (§5.6). This is the correct privacy-respecting
  outcome — deletion is honored
  — but "never forgets" is true at the concept tier only; the evidence tier is
  forgotten with the document.
