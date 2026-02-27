# Changelog

## 2026-02-27

### Auto-start Colima/Docker before Mermaid PNG rendering

The Mermaid rendering activity now checks if Docker is running before the rendering loop and auto-starts Colima if it's stopped. This eliminates the repeated per-diagram Docker connection errors in the logs when Colima is not running.

#### Changes

- **src/activities/mermaid_render_activities.py** -- Added `_ensure_docker_running()` helper that checks `docker info`, falls back to `colima status`, and runs `colima start` if needed. Called once before the rendering loop; if Docker is unavailable after the check, all diagrams go straight to local `mmdc` without noisy per-diagram Docker failures.

### Added descriptive filenames to Mermaid PNG outputs

Diagram PNG filenames now include the diagram type and title extracted from YAML front matter, instead of the generic `diagram-NN-diagram.png` naming.

#### Changes

- **src/activities/mermaid_render_activities.py** -- Added `_slugify()` for filesystem-safe title conversion, `_parse_mermaid_content()` to skip YAML front matter and detect diagram type from the first body line. Filenames now follow the pattern `diagram-01-graph-cross-repository-lifecycle.png`. Duplicate type words are stripped from the title slug.

#### Examples

| Before | After |
|---|---|
| `diagram-01-diagram.png` | `diagram-01-graph-cross-repository-lifecycle-how-all-repos-work-together.png` |
| `diagram-05-diagram.png` | `diagram-05-flowchart-data-flow-end-to-end-infrastructure-and-processing-pipeline.png` |
| `diagram-10-diagram.png` | `diagram-10-sequence-infrastructure-provisioning.png` |
| `diagram-09-pie.png` | `diagram-09-pie.png` (no title — unchanged) |

### Added external contributors to README

- **README.md** -- Added Lean Accelerate Consultancy as external contributor under Credits section, with link to Usage Guide.

### Fixed Mermaid Docker rendering permissions issue

Fixed permission denied errors when rendering Mermaid diagrams to PNG using Docker container.

#### Changes

- **src/activities/mermaid_render_activities.py** -- Added `--user "$(id -u):$(id -g)"`, `-e HOME=/tmp`, and `--shm-size=2gb` flags to Docker run command to fix EACCES errors when writing PNG files to mounted volumes
- **mise.toml** -- Updated `mermaid-test` task with same Docker flags for consistency

#### Technical details

The Docker container (`repo-swarm-mermaid:local`) was unable to write PNG output files when using volume mounts because:
1. Container user UID/GID didn't match host user permissions
2. Chromium (used by mermaid-cli) requires writable home directory for crash handler and cache
3. Chromium needs shared memory for rendering

Solution: Run container with host user's UID/GID, set HOME to writable /tmp, and increase shared memory size.

## 2026-02-22

### Added AI vs Static Analyser gap analysis table to USAGE_GUIDE

Documents what each of the 17 base + 2 IaC-specific analysis steps produces in AI mode (Claude) versus Static Analyser mode. Covers depth of analysis, specific scanner classes used, and what each mode does and does not provide.

### Removed design docs

Deleted `mermaid-diagrams-from-static-analysis.md` and `static-analysis-implementation-steps.md` — planning documents that served their purpose during design and are no longer needed as standalone files.

### Consolidated repos.json to unified `uri` field

Replaced the dual `url` + `local_path` fields (and synthetic `local://` scheme) with a single `uri` field using standard URI schemes:

- `file:///path/to/repo` for local repositories
- `https://github.com/org/repo` for remote repositories

#### Breaking changes

- **`url` field removed** from repos.json -- use `uri` instead
- **`local_path` field removed** from repos.json -- use `file://` URI instead
- **`local://` scheme removed** -- use `file://` URI instead
- **`local_path` field removed** from `InvestigateSingleRepoRequest` Pydantic model -- local path is now derived from `file://` URI at runtime
- **`_comment_local` top-level field removed** from repos.json

#### Files changed

- `src/models/workflows.py` -- Removed `local_path` field from `InvestigateSingleRepoRequest`; URI validator now accepts `file://`, `http://`, `https://` only
- `src/workflows/investigate_repos_workflow.py` -- Reads `uri` field only; derives local vs remote from URI scheme; no legacy fallbacks
- `src/workflows/investigate_single_repo_workflow.py` -- Derives `local_path` at runtime from `repo_url[7:]` when URI starts with `file://`; uses `is_local_repo` boolean for branching
- `src/client.py` -- Reads `repo_info.get("uri")`; updated log messages
- `src/utils/section_extractor.py` -- Reads `meta.get("uri")`
- `scripts/update_repos.py` -- Writes `"uri"` key for new repos from GitHub API
- `scripts/local.sh` -- Updated help text to reference `file://` URIs
- `prompts/repos.json.example` -- All entries use `uri` field
- `prompts/METADATA_DETECTION.md` -- Updated JSON examples
- `USAGE_GUIDE.md`, `env.local.example`, `README.md` -- Updated configuration docs and troubleshooting

#### Migration

Before:
```json
{
  "url": "local://my-repo",
  "local_path": "/path/to/repo",
  "type": "backend"
}
```

After:
```json
{
  "uri": "file:///path/to/repo",
  "type": "backend"
}
```

### Fixed status mismatch between SaveMetadataOutput and SaveToDynamoResult

`SaveMetadataOutput` (activity) allowed `success`/`error` while `SaveToDynamoResult` (workflow) allowed `success`/`failed`. When DynamoDB was unavailable in local mode, the activity returned `status="error"` which caused a Pydantic validation error in the workflow.

- Both models now accept `success`, `failed`, and `error`
- Error handlers in `InvestigationCache` and the activity now return `status="failed"` consistently
- Eliminates noisy validation traceback when DynamoDB is unavailable in local mode

### Fixed stale `repo_url` variable reference in chunk_info_map

Missed variable rename from the URI refactor -- `repo_url` was renamed to `repo_uri` in the chunk loop but line 314 still used the old name, causing a `NameError` at runtime.

### Updated mise.toml comment for URI refactor

- `mise.toml` -- Updated `local_path` reference to `file:// URIs` in investigate-local task comment
- `.gitignore` -- Added `outputs_v3/` and `outputs_v3_1/` directories

---

## 2026-02-19

### Enriched static diagrams with AWS services, data flow, narratives, titles, and cross-repo lifecycle

Major quality improvements to the MermaidDiagramGenerator to close the visual gap with AI-generated diagrams (Round 2):

- **AWS Service Nodes in Overview Diagram** -- Added 12+ AWS service types (VPC, EMR, EC2, Lambda, ECS, IAM, S3, EBS, RDS, DynamoDB, ELB, CloudWatch) to the overview `graph TD` diagram, with repo-to-service and service-to-service structural edges inferred from Terraform resource categories and VPC endpoints
- **Data Flow Diagram** (`flowchart LR`) -- New diagram with 6+ subgraphs (Sources, ControlPlane, NetworkLayer, ComputeLayer, SecurityLayer, DataLayer, Monitoring) showing end-to-end infrastructure and processing pipeline
- **CloudFormation Integration Sequence** -- New sequence diagram showing the Terraform->CloudFormation->EMR hybrid IaC flow with S3 template upload, stack creation, polling loop, and output extraction
- **EMR Runtime/Operational Sequence** -- New sequence diagram showing job submission through CI/CD, S3 artifact upload, YARN orchestration, worker allocation, and error handling alt block
- **Narrative Text Generation** -- Added 3 new sections to the output document:
  - Key Connections narrative (EMR as central target, shared VPC, TF-CF bridge, S3 data layer, IAM)
  - Data Flow Summary table (sensitive data types, storage, access controls)
  - Data Governance Concerns (risk items with recommendations)
- **Tech Stack Enrichment** -- Added cross-technology edges between repos sharing technologies, and per-node classDef styling
- **Mermaid Title Front Matter** -- All diagram types now include `---\ntitle: ...\n---` front matter for descriptive titles rendered in the PNG output (overview, tech stack, infrastructure, data flow, module structure, sequence diagrams, lifecycle)
- **Cross-Repository Lifecycle Diagram** -- New overarching `graph LR` diagram showing how all repos work together, with repo nodes (language, LOC, resource summary), shared module edges, alternative IaC approach edges, central AWS Cloud Infrastructure node, and Runtime enablement node

#### New module-level constants

- `_SERVICE_MAP` -- Maps 12 resource categories to AWS service node definitions (id, display, category)
- `_VPC_ENDPOINT_SERVICE_MAP` -- Maps VPC endpoint names (s3, dynamodb, kinesis) to AWS service nodes
- `_SERVICE_EDGES` -- Static service-to-service structural edges (EMR->VPC, EMR->S3, EMR->IAM, etc.)
- `_LAYER_MAP` -- Maps resource categories to architectural layers (network, security, compute, storage, monitoring, loadbalancing)

#### New methods

- `_extract_aws_service_nodes()` -- Extracts distinct AWS service nodes from resource categories and VPC endpoints
- `_map_repo_to_services()` -- Maps a repo to AWS service IDs it provisions with edge labels
- `_generate_data_flow_diagram()` -- `flowchart LR` with 6+ subgraphs
- `_build_cf_integration_flow()` -- CloudFormation sequence with polling loop
- `_build_runtime_sequence_flow()` -- EMR job submission sequence with YARN and alt block
- `_generate_key_connections_narrative()` -- Markdown narrative about architectural connections
- `_generate_data_flow_summary()` -- Markdown table of sensitive data types
- `_generate_governance_concerns()` -- Risk items with recommendations
- `_generate_cross_repo_lifecycle_diagram()` -- Overarching cross-repo lifecycle `graph LR`

#### Tests

- **168 tests passing** (up from 98 in Round 1)
- New test classes: `TestOverviewAWSServiceNodes` (12), `TestDataFlowDiagram` (10), `TestCFIntegrationSequence` (6), `TestRuntimeSequence` (6), `TestNarrativeGeneration` (9), `TestTechStackEnrichment` (3), `TestSequenceFlowPriority` (3), `TestDiagramTitles` (10), `TestCrossRepoLifecycleDiagram` (11)

---

## [0.4.0] - 2026-02-13

### Added ENABLE_AI toggle for no-AI static analysis mode

RepoSwarm can now run a complete investigation pipeline without any AI/Claude API calls. When `ENABLE_AI=false`, all Claude calls are replaced with programmatic static analysis using a suite of specialized scanners, producing `.arch.md` files with the same 19-section structure.

- **`ENABLE_AI`** env var (default `true`) -- controls whether Claude API is used
- When `ENABLE_AI=false`, no `ANTHROPIC_API_KEY` is required
- Shell scripts (`full.sh`, `local.sh`, `single.sh`) skip API key validation when AI is disabled

### Added comprehensive static analysis framework

A full suite of programmatic code scanners that replace Claude analysis when AI is disabled:

- **LanguageDetector** (`language_detector.py`, 401 lines) -- Detects 40+ programming languages, counts LOC/comments/blank lines, identifies tech stack
- **StaticAnalyzer** (`static_analyzer.py`, 322 lines) -- Modular dispatch table supporting 17 analysis sections
- **11 specialized scanners** in `src/investigator/core/static_analyzers/`:
  - `api_scanner.py` -- API endpoint extraction (HTTP methods, paths)
  - `database_scanner.py` -- Database type/connection/schema detection
  - `event_detector.py` -- Event broker/topic/queue identification (Kafka, RabbitMQ, etc.)
  - `security_scanner.py` -- IAM resources, auth mechanisms, authorization patterns
  - `deployment_scanner.py` -- Deployment configs, IaC patterns, container orchestration
  - `terraform_parser.py` -- Terraform resource/provider/VPC endpoint parsing
  - `entity_parser.py` -- Core data entities, domain models, relationships
  - `data_mapping_scanner.py` -- Data flow mapping, PII/sensitive data identification
  - `feature_flag_scanner.py` -- Feature flag detection, A/B test patterns
  - `prompt_security_scanner.py` -- Prompt injection vulnerability analysis
  - `monitoring_scanner.py` -- Monitoring/observability component detection

#### New activity

- `analyze_with_static_context` (`static_analysis_activities.py`) -- Drop-in replacement for Claude API activity; routes to StaticAnalyzer dispatch table

#### Tests

- 15 new test files with 290+ test methods covering all scanners, language detection, and static analysis

### Added MermaidDiagramGenerator for static Mermaid diagram generation (Round 1)

Programmatic Mermaid diagram generation from `.arch.md` files with no AI required:

- **MermaidDiagramGenerator** (`mermaid_diagram_generator.py`) -- Parses `.arch.md` files and generates 6 diagram types:
  - Network/Architecture Overview (`graph TD`) -- repo nodes with connections, event/DB edges
  - Technology Stack (`graph LR`) -- tech items grouped per repo
  - Infrastructure Architecture (`graph TD`) -- layered resource view with categories
  - Module Structure (`graph TD`) -- per-repo directory breakdown with file counts
  - Language Distribution (pie chart) -- aggregated LOC across all repos
  - Sequence Diagrams -- API request flows, event-driven flows, shared DB flows, IaC provisioning with cloud API interactions, state management, polling loops
- Parses 10+ sections from `.arch.md`: metadata, tech stack, languages, modules, APIs, events, databases, service dependencies, infrastructure resources, authentication, module chain, outputs
- Rich connection inference: event broker edges, database sharing edges, service dependency edges with dedup
- `classDef` styling for node types (iac, service, event processor, data, library)
- `autonumber`, `activate`/`deactivate`, `Note`, `loop` in sequence diagrams

#### Tests

- 98 tests passing covering parsing, overview, tech stack, module, pie chart, infrastructure, and sequence diagrams

---

## [0.3.0] - 2026-02-12

### Added automated Mermaid diagram PNG rendering via Docker

Mermaid diagrams can now be rendered to PNG images automatically using a Docker container:

- **`Dockerfile.mermaid`** -- Production Docker image (Node 20 slim + Chromium + mermaid-cli) with non-root user for security
- **`mermaid_render_activities.py`** (275 lines) -- Temporal activity with intelligent fallback:
  - Docker-first rendering (preferred)
  - Automatic fallback to local `mmdc` if Docker unavailable
  - Configurable timeouts and Docker image selection
  - Extracts diagram blocks from markdown with type detection
  - Supports all Mermaid diagram types (graph, sequence, flowchart, class, state, ER, gantt, pie)
- Integrated into `cross_repo_analysis_workflow.py` as non-fatal step (markdown is always source of truth)

#### Configuration

- `RENDER_MERMAID_PNGS` env var (default `false`) -- controls PNG rendering
- `MERMAID_DOCKER_IMAGE` (default `repo-swarm-mermaid:local`) -- Docker image name
- `MERMAID_RENDER_TIMEOUT` (default `120` seconds)

#### mise tasks

- `mermaid-build` -- Build the Docker image
- `mermaid-test` -- Verify Docker rendering works

#### Tests

- 16 tests covering block extraction, Docker rendering, mmdc fallback, and error handling

### Added 4-mode configuration guide

Comprehensive documentation of 4 operational modes:

- **Mode 1**: Local repos + Claude only (no Architecture Hub) -- simplest setup
- **Mode 2**: Remote repos + Claude + Architecture Hub (full cloud integration)
- **Mode 3**: Remote repos + Claude only (GitHub required, no Hub)
- **Mode 4**: Diagrams only (re-render from cached results without investigation)

#### Documentation

- `USAGE_GUIDE.md` -- Complete end-to-end guide with modes comparison table, setup instructions, troubleshooting
- `env.local.example` -- Rewritten with mode-specific commented sections
- `prompts/repos.json.example` -- Added as template
- `prompts/repos.json` added to `.gitignore` (user-specific local paths)

### Fixed Temporal sandbox violations

- Replaced `datetime.utcnow()` with `workflow.now()` in `cross_repo_analysis_workflow.py`
- Removed `os.path` calls that violate Temporal sandbox constraints
- Fixed `os.path` usage in `cross_repo_analysis_workflow.py` for `repo_structure` dict construction

---

## [0.2.0] - 2026-02-11

### Added cross-repo Mermaid diagram generation

After all individual repo analyses complete, RepoSwarm can now optionally generate three cross-repo Mermaid diagram types that provide a joined-up architectural view across all analysed repositories:

- **Network/Architecture diagram** (`graph TD`) -- how repos/services connect to each other
- **Sequence diagrams** (`sequenceDiagram`) -- request flows across services
- **Data flow diagrams** (`flowchart LR`) -- how data moves between repos, including PII tracking

Diagram generation is controlled by the `CREATE_DIAGRAMS` env var and works in both online and local mode. Diagrams are output to `outputs/diagrams/architecture-overview.md`.

### Added full local/offline mode

RepoSwarm can now scan repos directly from local disk paths, run the full Claude analysis pipeline locally, and save all outputs to the local filesystem -- no GitHub cloning or architecture hub required.

### New files

- **`prompts/cross_repo/prompts.json`** -- standalone processing config for the 3 diagram steps, with `input_sections` for token budget management
- **`prompts/cross_repo/network_architecture.md`** -- prompt template for network/architecture `graph TD` diagrams
- **`prompts/cross_repo/sequence_diagrams.md`** -- prompt template for `sequenceDiagram` diagrams
- **`prompts/cross_repo/data_flow_diagrams.md`** -- prompt template for `flowchart LR` data flow diagrams
- **`src/workflows/cross_repo_analysis_workflow.py`** -- new Temporal workflow (`CrossRepoAnalysisWorkflow`) that collects per-repo analysis, extracts relevant sections per diagram step, calls Claude for each, and combines output into a single markdown file
- **`src/activities/cross_repo_activities.py`** -- three new activities: `get_cross_repo_prompts_config_activity`, `read_local_arch_files_activity`, `write_local_diagrams_activity`
- **`src/utils/section_extractor.py`** -- utility for extracting specific H1 markdown sections from arch files to manage token budgets; key functions: `extract_sections()`, `build_cross_repo_analysis_input()`, `build_repos_metadata_text()`
- **`scripts/local.sh`** -- shell script for the new `mise investigate-local` task

### Changes

#### `src/investigator/core/config.py`
- Added `CREATE_DIAGRAMS` env var (default `false`) -- controls whether Mermaid diagrams are generated after multi-repo analysis
- Added `LOCAL_MODE` env var (default `false`) -- enables local/offline mode via environment
- Added `LOCAL_OUTPUT_DIR` env var (default `outputs`) -- configurable output directory for local mode

#### `env.local.example`
- Documented all new env vars: `CREATE_DIAGRAMS`, `LOCAL_MODE`, `LOCAL_OUTPUT_DIR`

#### `src/models/workflows.py`
- Added `local_path`, `local_mode`, `output_dir` fields to `InvestigateSingleRepoRequest`
- Reordered `local_path` and `local_mode` before `repo_url` to fix Pydantic v1-style validator field ordering bug
- Updated `repo_url` validator to accept local paths (`/`), `local://` protocol, and to skip HTTP validation when `local_path` or `local_mode` is set
- Made `CloneRepositoryResult.temp_dir` Optional (for local repos where no temp dir is created)
- Added `local_mode` and `output_dir` fields to `InvestigateReposRequest`
- Added new models: `CrossRepoAnalysisRequest`, `CrossRepoAnalysisResult`

#### `src/models/__init__.py`
- Added exports for `CrossRepoAnalysisRequest`, `CrossRepoAnalysisResult`

#### `src/activities/investigate_activities.py`
- Added `use_local_repo_activity(local_path, repo_name)` -- validates local repo path exists, returns same dict structure as `clone_repository_activity` but with `temp_dir=None`
- Added `write_local_analysis_activity(repo_name, analysis_content, output_dir)` -- writes `{repo_name}-arch.md` to local output directory

#### `src/workflows/investigate_single_repo_workflow.py`
- Step 1 branching: if `local_path` is set, calls `use_local_repo_activity` instead of `_clone_repository`
- Step 8 branching: if `local_mode`, calls `write_local_analysis_activity` instead of `_save_to_hub`
- Step 10 branching: if `local_path`, skips cleanup (we don't own the directory)

#### `src/workflows/investigate_repos_workflow.py`
- Extracts `local_mode` and `output_dir` from request and passes to `_run_investigation()`
- In local mode: skips `update_repos_list` activity
- Repo filtering: in local mode, requires `local_path` in repo info; in online mode, requires `url`
- Passes `local_path`, `local_mode`, `output_dir` to child workflow requests
- Replaced commented-out `AnalyzeArchitectureHubWorkflow` placeholder with real cross-repo diagram generation logic: checks `Config.CREATE_DIAGRAMS`, builds `CrossRepoAnalysisRequest`, starts `CrossRepoAnalysisWorkflow` as child workflow

#### `src/investigate_worker.py`
- Registered `CrossRepoAnalysisWorkflow` in `all_workflows`
- Registered 5 new activities: `use_local_repo_activity`, `write_local_analysis_activity`, `get_cross_repo_prompts_config_activity`, `read_local_arch_files_activity`, `write_local_diagrams_activity`

#### `src/client.py`
- Updated `run_investigate_repos_workflow()` to accept `local_mode` and `output_dir` parameters, passed through to `InvestigateReposRequest`
- Added local mode logging and 12-hour execution timeout (vs 365 days for continuous online mode)
- Added new `investigate-local` CLI command with args: `--force`, `--claude-model=`, `--max-tokens=`, `--chunk-size=`, `--output-dir=`
- Updated help text to show all 3 available commands

#### `mise.toml`
- Added `investigate-local` task pointing to `scripts/local.sh`

#### `prompts/repos.json`
- For local mode usage: repos now use `local_path` field for filesystem paths and `url` field uses `local://` protocol placeholder

### How to use

**Online mode with diagrams** (set `CREATE_DIAGRAMS=true` in `.env.local`):
```
mise dev-server       # terminal 1
mise dev-worker       # terminal 2
mise investigate-all  # terminal 3
```

**Local/offline mode** (set `CREATE_DIAGRAMS=true` and add `local_path` to repos in `repos.json`):
```
mise dev-server          # terminal 1
mise dev-worker          # terminal 2
mise investigate-local   # terminal 3
```

### Notes
- Per-repo analysis files are written to `outputs/{repo-name}-arch.md`
- Cross-repo Mermaid diagrams are written to `outputs/diagrams/architecture-overview.md`
- Token budget management: each diagram step only extracts relevant H1 sections from per-repo arch files via `input_sections` config, rather than sending entire files
- Diagram generation chains context: sequence diagrams build on network architecture output, data flow builds on both

---

## [0.1.0] - 2026-02-10

### Added local-only mode support

RepoSwarm can now run entirely against local desktop repositories without requiring GitHub, AWS, or a remote architecture hub.

### Changes

#### `.env.local`
- Set `GITHUB_TOKEN=` (empty) instead of the placeholder `your-github-token-here`. The non-empty placeholder was being treated as a valid token, causing authentication failures on every GitHub API call and git clone operation.

#### `prompts/repos.json`
- Added the required `"default"` and `"_comment"` fields. The `update_repos_json()` function in `update_repos.py` crashes with a `ValueError` if `"default"` is missing.

#### `scripts/update_repos.py`
- `main()`: When `DEFAULT_ORG_NAME` is `local-only` (or `LOCAL_TESTING=true`), the script now returns cleanly instead of calling the GitHub API for a non-existent org and exiting with `sys.exit(1)`.
- `update_repos_json()`: Relaxed the `default_repo is None` validation when `LOCAL_TESTING=true`, since local-only setups don't need a default remote URL.

#### `src/worker.py`
- `validate_environment()`: When `LOCAL_TESTING=true`, `GITHUB_TOKEN` is no longer required (only logs a warning). When `LOCAL_TESTING=true` and `PROMPT_CONTEXT_STORAGE=file`, AWS credential checks (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) are skipped entirely.

#### `src/workflows/investigate_single_repo_workflow.py`
- `run()` (Step 8): When `ARCH_HUB_REPO_NAME=local-only` or `ARCH_HUB_BASE_URL=https://github.com/local-only`, the architecture hub save step is skipped. Previously it attempted to clone a non-existent remote repo and then `raise Exception` killed the entire workflow.

### Notes

- **Investigation caching**: The DynamoDB-based investigation cache (`check_if_repo_needs_investigation` / `save_investigation_metadata`) will fail gracefully in local mode, defaulting to `needs_investigation=True`. This means every run re-investigates all repos, which is acceptable for local testing.
- **DynamoDB health check**: Already handled local mode correctly (no changes needed).
