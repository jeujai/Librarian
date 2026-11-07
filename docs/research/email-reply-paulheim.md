# Reply to Dr. Paulheim — May 27, 2026

---

**Subject: Re: Graph-Guided Retrieval — Strategic Plan Attached**

Dear Dr. Paulheim (he/him — and I use he/him as well, thank you for asking),

Thank you for this thoughtful response. I received it yesterday and it landed at exactly the right time — your points about evaluation protocols, graph embeddings, and reusing existing pre-computed embeddings directly shaped the strategic plan I've spent the day developing.

I've written a strategic plan (attached) that maps out the journey from the current binary-gate system to a continuous-scoring, multi-domain retrieval architecture. The plan covers five phases over 12 months:

- **Phase 1:** Train heterogeneous graph embeddings across all three layers (document graph, Wikidata/ConceptNet, UMLS), with learned transformation matrices per edge type. Reuse existing pre-computed embeddings where available — your point about combining existing embeddings without recomputation is exactly the right instinct, and it's called out as a design principle in the plan.

- **Phase 2:** Replace the hardcoded relationship-type whitelist (35 types) with scored universal traversal. Every edge gets a score; low-scoring paths deprioritize themselves without being explicitly excluded.

- **Phase 3:** Replace the binary SAME_AS pre-check with continuous bridge scores, enabling partial cross-ontology reasoning — UMLS contributes proportionally to how well a concept aligns rather than being all-or-nothing.

- **Phase 4:** Fused NER representations and adaptive α/β weights that self-calibrate based on graph signal confidence per query.

- **Phase 5:** Evaluation against the gold-standard dataset (200+ Q&A pairs across clinical, technical, and mixed domains), with domain-expert blind ratings against baselines (Milvus-only, text RAG, current binary-gate system, and any comparable GraphRAG systems).

Your Gene Ontology embedding reuse work sounds directly relevant — I'd love to read it if you have a reference handy. The bridge matrix approach in the plan (learning transformations between independently-trained embedding spaces rather than retraining jointly) seems like it might share some DNA with what you did.

On your question about my situation: I'm pursuing a PhD seriously — paid or not, though a paid position would be ideal. My larger goal is to operationalize expert knowledge as a self-contained, tablet-based GraphRAG application that can dispense expert advice on any topic, especially off-grid — financed by NGO grants to communities and equipping doctors, nurses, and teachers with the facility. A paid position in Germany would also align well with my family situation: my younger daughter has a strong interest in studying in Europe, and my elder daughter begins at University of Michigan this fall, so I'm balancing continued financial support for her with the opportunity to be closer to my younger one's path. My wife is considering re-entering the job market as a project manager, which would help as well.

I have two questions where your perspective would be especially valuable:

1. **HGT vs. R-GCN as a starting point.** For a graph at this scale (7.1M nodes, 35.3M edges, 4 node types, 60+ edge types), the plan currently leans toward HGT for scalability. But R-GCN might offer a cleaner baseline. Given your experience, would you recommend establishing an R-GCN baseline first, or going directly to heterogeneous attention?

2. **Gold-standard dataset construction.** Are there established biomedical-KG QA benchmarks you'd point to as a starting point, or does this need to be built from scratch with domain experts?

I'd be grateful for any feedback on the plan — particularly whether the phase ordering makes sense and whether there are pitfalls you see that I don't.

Best,
Peter

---

Attachment: `continuous-trust-strategic-plan.docx`
