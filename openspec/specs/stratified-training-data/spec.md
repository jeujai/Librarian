## Purpose

The medical knowledge fine-tuning pipeline currently generates training data from 28 clinical semantic types without controlling distribution. The evaluation set tests only 5 semantic types (balanced at ~10 questions each), but training data is heavily skewed — e.g., Diagnostic Procedure receives 18.4% of pairs while Sign or Symptom gets only 1.8%, and 51% of pairs go to types not even evaluated. This imbalance causes the fine-tuned model to regress on most evaluated categories.

This feature adds two improvements:
1. A configurable semantic type inclusion list that controls which types are used during seed question generation (not post-hoc filtering).
2. Stratified sampling that distributes the training data budget evenly across the included semantic types.


### Key Terms
- **Seed_Question_Generator**: The component within `RAGQAStrategy` responsible for producing seed questions from UMLS concepts and question templates (`generate_seed_questions`, `_generate_umls_concept_seeds`, `_generate_template_seeds`, `_fetch_concept_names_for_templates`).
- **Training_Data_Config**: The `TrainingDataConfig` dataclass that holds all generation parameters, passed from the CLI or API to the generator pipeline.
- **CLI_Orchestrator**: The `scripts/run-training-pipeline.py` script that parses command-line arguments and triggers the pipeline via the API.
- **API_Router**: The FastAPI router at `POST /api/v1/ml/training-data/generate` that accepts generation requests and dispatches Celery tasks.
- **Semantic_Type**: A UMLS semantic type string (e.g., "Pharmacologic Substance", "Disease or Syndrome") that categorises medical concepts.
- **Inclusion_List**: An ordered list of Semantic_Type strings specifying which types to include in training data generation.
- **Per_Type_Budget**: The number of seed questions allocated to each Semantic_Type in the Inclusion_List, computed as `target_count / len(inclusion_list)`.
- **EVAL_SEMANTIC_TYPES**: The 5 semantic types used in the evaluation set: Pharmacologic Substance, Disease or Syndrome, Therapeutic or Preventive Procedure, Sign or Symptom, Diagnostic Procedure.
- **CLINICAL_SEMANTIC_TYPES**: The full list of 28 clinical semantic types currently defined in `rag_qa_strategy.py`.

## Requirements

### Requirement: Semantic Type Inclusion List on TrainingDataConfig

The system SHALL support: As a pipeline operator, I want to specify which semantic types to include in training data generation, so that I can focus training on the types that matter for evaluation.

#### Scenario: THE Training_Data_Config SHALL contain a `semantic_types` fi

- **THEN** THE Training_Data_Config SHALL contain a `semantic_types` field of type `Optional[List[str]]`.

#### Scenario: WHEN `semantic_types` is `None`, THE Seed_Question_Generator

- **THEN** WHEN `semantic_types` is `None`, THE Seed_Question_Generator SHALL use the full CLINICAL_SEMANTIC_TYPES list (preserving backward compatibility).

#### Scenario: WHEN `semantic_types` is provided as a non-empty list, THE S

- **THEN** WHEN `semantic_types` is provided as a non-empty list, THE Seed_Question_Generator SHALL generate seed questions only from the specified Semantic_Type values.

#### Scenario: THE Training_Data_Config SHALL default `semantic_types` to `

- **THEN** THE Training_Data_Config SHALL default `semantic_types` to `None`.

### Requirement: CLI Parameter for Semantic Type Inclusion

The system SHALL support: As a pipeline operator, I want a `--semantic-types` CLI parameter that controls which semantic types are included at generation time, so that I can configure training runs from the command line.

#### Scenario: THE CLI_Orchestrator SHALL accept a `--semantic-types` param

- **THEN** THE CLI_Orchestrator SHALL accept a `--semantic-types` parameter that takes zero or more Semantic_Type strings.

#### Scenario: WHEN `--semantic-types` is provided with values, THE CLI_Orc

- **THEN** WHEN `--semantic-types` is provided with values, THE CLI_Orchestrator SHALL pass those values as the `semantic_types` field in the API request payload.

#### Scenario: WHEN `--semantic-types` is not provided, THE CLI_Orchestrato

- **THEN** WHEN `--semantic-types` is not provided, THE CLI_Orchestrator SHALL omit `semantic_types` from the API request payload (relying on server-side defaults).

#### Scenario: WHEN `--semantic-types` is provided with values, THE CLI_Orc

- **THEN** WHEN `--semantic-types` is provided with values, THE CLI_Orchestrator SHALL skip the existing post-hoc semantic type filtering step (Step 3a), because filtering is now handled at generation time.

### Requirement: API Support for Semantic Type Inclusion

The system SHALL support: As an API consumer, I want to specify semantic types in the generation request, so that the server generates training data only for the requested types.

#### Scenario: THE API_Router request model SHALL accept an optional `seman

- **THEN** THE API_Router request model SHALL accept an optional `semantic_types` field of type `Optional[List[str]]`.

#### Scenario: WHEN `semantic_types` is provided in the request, THE API_Ro

- **THEN** WHEN `semantic_types` is provided in the request, THE API_Router SHALL include the value in the config dict passed to the Celery task.

#### Scenario: WHEN `semantic_types` is not provided in the request, THE AP

- **THEN** WHEN `semantic_types` is not provided in the request, THE API_Router SHALL omit the field from the config dict (preserving backward compatibility).

### Requirement: Stratified Seed Question Budget Allocation

The system SHALL support: As a pipeline operator, I want the training data to be evenly distributed across the included semantic types, so that the fine-tuned model does not regress on under-represented evaluation categories.

#### Scenario: WHEN `semantic_types` is provided, THE Seed_Question_Generat

- **THEN** WHEN `semantic_types` is provided, THE Seed_Question_Generator SHALL compute Per_Type_Budget as `target_count // len(semantic_types)` for each Semantic_Type in the Inclusion_List.

#### Scenario: WHEN `semantic_types` is provided, THE Seed_Question_Generat

- **THEN** WHEN `semantic_types` is provided, THE Seed_Question_Generator SHALL allocate remaining budget (`target_count % len(semantic_types)`) by distributing one extra question to the first types in the list.

#### Scenario: THE Seed_Question_Generator SHALL query UMLS concepts only f

- **THEN** THE Seed_Question_Generator SHALL query UMLS concepts only for the Semantic_Type values in the active inclusion list (either the provided list or the full CLINICAL_SEMANTIC_TYPES).

#### Scenario: THE Seed_Question_Generator SHALL apply the same per-type bu

- **THEN** THE Seed_Question_Generator SHALL apply the same per-type budget logic to both the UMLS concept seed source and the template seed source.

#### Scenario: WHEN `semantic_types` is `None`, THE Seed_Question_Generator

- **THEN** WHEN `semantic_types` is `None`, THE Seed_Question_Generator SHALL preserve the existing budget allocation logic (dividing evenly across all CLINICAL_SEMANTIC_TYPES).

### Requirement: Stratified Template Concept Fetching

The system SHALL support: As a pipeline operator, I want the template-based seed source to also respect the inclusion list, so that template seeds do not introduce concepts from excluded semantic types.

#### Scenario: WHEN `semantic_types` is provided, THE Seed_Question_Generat

- **THEN** WHEN `semantic_types` is provided, THE Seed_Question_Generator SHALL fetch concept names for templates only from the specified Semantic_Type values.

#### Scenario: THE Seed_Question_Generator SHALL allocate the template conc

- **THEN** THE Seed_Question_Generator SHALL allocate the template concept fetch budget evenly across the active semantic types.

#### Scenario: WHEN `semantic_types` is `None`, THE Seed_Question_Generator

- **THEN** WHEN `semantic_types` is `None`, THE Seed_Question_Generator SHALL fetch concepts from all CLINICAL_SEMANTIC_TYPES (preserving existing behavior).

### Requirement: Config Propagation Through the Pipeline

The system SHALL support: As a pipeline operator, I want the semantic types configuration to flow from the CLI through the API, Celery task, TrainingDataGenerator, and into RAGQAStrategy, so that the inclusion list is respected end-to-end.

#### Scenario: THE Training_Data_Config `semantic_types` field SHALL be ser

- **THEN** THE Training_Data_Config `semantic_types` field SHALL be serialisable to and deserialisable from a JSON dict (for Celery task argument passing).

#### Scenario: WHEN the RAG strategy is active, THE `TrainingDataGenerator.

- **THEN** WHEN the RAG strategy is active, THE `TrainingDataGenerator._run_rag_strategy` method SHALL pass the `semantic_types` value from the config to `RAGQAStrategy.generate`.

#### Scenario: THE `RAGQAStrategy.generate` method SHALL accept an optional

- **THEN** THE `RAGQAStrategy.generate` method SHALL accept an optional `semantic_types` parameter and forward the value to `generate_seed_questions`.

#### Scenario: THE `RAGQAStrategy.generate_seed_questions` method SHALL acc

- **THEN** THE `RAGQAStrategy.generate_seed_questions` method SHALL accept an optional `semantic_types` parameter and use the value to determine which types to generate seeds for.

### Requirement: Logging of Stratified Distribution

The system SHALL support: As a pipeline operator, I want to see the per-type seed question counts in the logs, so that I can verify the stratified distribution is working correctly.

#### Scenario: WHEN seed question generation completes, THE Seed_Question_G

- **THEN** WHEN seed question generation completes, THE Seed_Question_Generator SHALL log the count of seed questions generated per Semantic_Type.

#### Scenario: WHEN `semantic_types` is provided, THE Seed_Question_Generat

- **THEN** WHEN `semantic_types` is provided, THE Seed_Question_Generator SHALL log the active inclusion list and the computed Per_Type_Budget.
