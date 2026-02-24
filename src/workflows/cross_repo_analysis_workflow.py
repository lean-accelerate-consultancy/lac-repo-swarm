"""
Cross-Repo Analysis Workflow for Mermaid Diagram Generation.

This workflow takes analysis results from all individual repo investigations
and generates cross-repo Mermaid diagrams (network architecture, sequence,
and data flow diagrams) via Claude prompts.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Dict, List, Optional
import logging

from activities.investigate_activities import (
    read_prompt_file_activity,
    save_prompt_context_activity,
    analyze_with_claude_context,
    retrieve_all_results_activity,
    save_to_arch_hub,
)
from activities.cross_repo_activities import (
    get_cross_repo_prompts_config_activity,
    read_local_arch_files_activity,
    write_local_diagrams_activity,
)
from activities.mermaid_render_activities import render_mermaid_pngs_activity
from models import (
    AnalyzeWithClaudeInput,
    PromptContextDict,
    ClaudeConfigOverrides,
    CrossRepoAnalysisRequest,
    CrossRepoAnalysisResult,
    ConfigOverrides,
)

logger = logging.getLogger(__name__)

# Cross-repo analysis uses a virtual repo name for storage
CROSS_REPO_NAME = "cross-repo-analysis"


@workflow.defn
class CrossRepoAnalysisWorkflow:
    """
    Workflow that generates cross-repo Mermaid diagrams.

    Takes all repos' analysis data and produces:
    1. Network/architecture diagram (graph TD)
    2. Sequence diagrams (sequenceDiagram)
    3. Data flow diagrams (flowchart LR)
    """

    def __init__(self) -> None:
        self._status = "initialized"
        self._diagram_count = 0

    @workflow.run
    async def run(self, request: CrossRepoAnalysisRequest) -> CrossRepoAnalysisResult:
        """
        Execute cross-repo analysis to generate Mermaid diagrams.

        Args:
            request: CrossRepoAnalysisRequest with repo results and metadata

        Returns:
            CrossRepoAnalysisResult with diagram generation results
        """
        logger.info(f"Starting cross-repo analysis workflow (local_mode={request.local_mode})")
        self._status = "running"

        try:
            # Step 1: Collect all repo analysis content
            repo_contents = await self._collect_repo_contents(request)

            if not repo_contents:
                logger.warning("No repo analysis content available for cross-repo analysis")
                return CrossRepoAnalysisResult(
                    status="skipped",
                    diagram_count=0,
                    message="No repo analysis content available"
                )

            logger.info(f"Collected analysis content from {len(repo_contents)} repos")

            # Step 2: Get cross-repo prompts config
            config_result = await workflow.execute_activity(
                get_cross_repo_prompts_config_activity,
                args=[],
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            if config_result["status"] != "success":
                raise Exception("Failed to load cross-repo prompts config")

            prompts_dir = config_result["prompts_dir"]
            processing_order = config_result["processing_order"]
            prompt_versions = config_result.get("prompt_versions", {})

            logger.info(f"Loaded {len(processing_order)} cross-repo prompt steps")

            # Step 3: Build metadata text and process each diagram step
            from utils.section_extractor import build_repos_metadata_text
            repos_metadata_text = build_repos_metadata_text(request.repos_metadata)

            step_results = {}
            diagram_outputs = []

            for step in processing_order:
                step_name = step["name"]
                file_name = step["file"]
                description = step.get("description", "")
                input_sections = step.get("input_sections", None)
                context_config = step.get("context", None)

                logger.info(f"Processing cross-repo step: {step_name}")

                # Build the analysis input for this step
                from utils.section_extractor import build_cross_repo_analysis_input
                all_repos_text = build_cross_repo_analysis_input(
                    repo_contents, input_sections
                )

                if not all_repos_text:
                    logger.warning(f"No content for step {step_name}, skipping")
                    continue

                # Read the prompt file
                prompt_result = await workflow.execute_activity(
                    read_prompt_file_activity,
                    args=[prompts_dir, file_name],
                    start_to_close_timeout=timedelta(minutes=1),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )

                if prompt_result["status"] == "not_found":
                    logger.error(f"Prompt file not found: {file_name}")
                    continue

                prompt_content = prompt_result["prompt_content"]
                prompt_version = prompt_result.get("prompt_version", "1")

                # Replace cross-repo placeholders in the prompt
                prompt_content = prompt_content.replace("{all_repos_analysis}", all_repos_text)
                prompt_content = prompt_content.replace("{repos_metadata}", repos_metadata_text)

                # Build context dict for storage
                context_dict = {
                    "repo_name": CROSS_REPO_NAME,
                    "step_name": step_name,
                    "prompt_version": prompt_version,
                    "context_reference_keys": []
                }

                # Add context references from previous cross-repo steps
                if context_config:
                    for context_step in context_config:
                        if isinstance(context_step, dict) and "val" in context_step:
                            step_ref = context_step["val"]
                        else:
                            step_ref = context_step
                        if step_ref and step_ref in step_results:
                            result_key = step_results[step_ref]
                            if result_key is not None:
                                context_dict["context_reference_keys"].append(result_key)

                # Save prompt data to storage
                # Pass all_repos_text as repo_structure so analyze_with_claude_context has content
                save_result = await workflow.execute_activity(
                    save_prompt_context_activity,
                    args=[context_dict, prompt_content, all_repos_text, ""],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )

                if save_result["status"] != "success":
                    raise Exception(f"Failed to save prompt context for step {step_name}")

                updated_context = save_result["context"]

                # Check ENABLE_AI toggle
                from investigator.core.config import Config
                enable_ai = Config.ENABLE_AI

                if not enable_ai:
                    # Use static diagram generation instead of Claude
                    # Only generate once on the first step -- all diagrams in one pass
                    if not step_results:
                        logger.info("Generating static Mermaid diagrams (ENABLE_AI=false)")
                        from activities.static_analysis_activities import generate_static_diagrams_activity
                        static_result = await workflow.execute_activity(
                            generate_static_diagrams_activity,
                            args=[repo_contents],
                            start_to_close_timeout=timedelta(minutes=5),
                            retry_policy=RetryPolicy(maximum_attempts=2),
                        )
                        if static_result["status"] == "success":
                            static_content = static_result["content"]
                            self._diagram_count = static_result["diagram_count"]
                            # Save and return immediately
                            output_result = await self._save_output(request, static_content)
                            self._status = "completed"
                            return CrossRepoAnalysisResult(
                                status="success",
                                diagrams_file_path=output_result.get("file_path") or output_result.get("arch_file_path"),
                                diagram_count=self._diagram_count,
                                hub_save_result=output_result if not request.local_mode else None,
                                message=f"Generated {self._diagram_count} Mermaid diagrams from {len(repo_contents)} repos (static analysis)"
                            )
                        else:
                            logger.error("Static diagram generation failed")
                    continue

                # Call Claude for diagram generation
                config_overrides = request.config_overrides
                # Use higher max_tokens for diagram output
                diagram_overrides = ConfigOverrides(
                    max_tokens=12000,
                    **(config_overrides.model_dump(exclude={'max_tokens'}) if config_overrides else {})
                )

                claude_input = AnalyzeWithClaudeInput(
                    context_dict=PromptContextDict(**updated_context),
                    config_overrides=ClaudeConfigOverrides(**diagram_overrides.model_dump()) if diagram_overrides else None,
                    latest_commit=None  # No commit tracking for cross-repo
                )

                logger.info(f"Calling Claude for cross-repo step: {step_name}")
                claude_result = await workflow.execute_activity(
                    analyze_with_claude_context,
                    args=[claude_input],
                    start_to_close_timeout=timedelta(minutes=20),
                    retry_policy=RetryPolicy(
                        maximum_attempts=3,
                        initial_interval=timedelta(seconds=5),
                        maximum_interval=timedelta(seconds=30),
                        backoff_coefficient=2.0
                    ),
                )

                if claude_result.status != "success":
                    logger.error(f"Claude analysis failed for step {step_name}")
                    continue

                # Store result key for context chaining
                result_context = claude_result.context.model_dump()
                result_key = result_context.get("result_reference_key")
                step_results[step_name] = result_key
                self._diagram_count += 1

                logger.info(f"Cross-repo step {step_name} completed (result key: {result_key})")

            # Step 4: Retrieve all results and combine into final output
            if not step_results:
                from investigator.core.config import Config
                if not Config.ENABLE_AI:
                    return CrossRepoAnalysisResult(
                        status="failed",
                        diagram_count=0,
                        message="Static diagram generation failed (ENABLE_AI=false). Check activity logs for details."
                    )
                return CrossRepoAnalysisResult(
                    status="failed",
                    diagram_count=0,
                    message="No diagram steps completed successfully"
                )

            # Retrieve results from storage
            # Build manager_dict directly to avoid os.path calls in workflow sandbox
            manager_dict = {
                "repo_name": CROSS_REPO_NAME,
                "step_results": step_results,
            }

            retrieve_result = await workflow.execute_activity(
                retrieve_all_results_activity,
                args=[manager_dict],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            if retrieve_result["status"] != "success":
                raise Exception("Failed to retrieve cross-repo analysis results")

            results_map = retrieve_result["results"]

            # Build the final diagram document
            final_content = self._build_final_document(processing_order, results_map, step_results)

            # Step 5: Save output
            output_result = await self._save_output(request, final_content)

            self._status = "completed"
            return CrossRepoAnalysisResult(
                status="success",
                diagrams_file_path=output_result.get("file_path") or output_result.get("arch_file_path"),
                diagram_count=self._diagram_count,
                hub_save_result=output_result if not request.local_mode else None,
                message=f"Generated {self._diagram_count} Mermaid diagrams from {len(repo_contents)} repos"
            )

        except Exception as e:
            logger.error(f"Cross-repo analysis workflow failed: {str(e)}")
            self._status = "failed"
            return CrossRepoAnalysisResult(
                status="failed",
                diagram_count=self._diagram_count,
                message=f"Cross-repo analysis failed: {str(e)}"
            )

    async def _collect_repo_contents(self, request: CrossRepoAnalysisRequest) -> Dict[str, str]:
        """
        Collect analysis content from all repos.

        Combines content from request.repo_results and fills in missing repos
        from local arch files if in local mode.
        """
        repo_contents = {}

        # First, collect from the request results
        for result in request.repo_results:
            repo_name = result.get("repo_name")
            content = result.get("arch_file_content")
            if repo_name and content:
                repo_contents[repo_name] = content

        # If in local mode and we have an output_dir, also check for existing arch files
        if request.local_mode and request.output_dir:
            try:
                local_result = await workflow.execute_activity(
                    read_local_arch_files_activity,
                    args=[request.output_dir],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(maximum_attempts=2),
                )

                if local_result["status"] == "success":
                    local_contents = local_result.get("repo_contents", {})
                    # Add any repos not already collected
                    for repo_name, content in local_contents.items():
                        if repo_name not in repo_contents:
                            repo_contents[repo_name] = content
                            logger.info(f"Added {repo_name} from local arch files")
            except Exception as e:
                logger.warning(f"Failed to read local arch files: {str(e)}")

        return repo_contents

    def _build_final_document(
        self,
        processing_order: List[Dict],
        results_map: Dict[str, str],
        step_results: Dict[str, str]
    ) -> str:
        """
        Build the final architecture-overview.md document from diagram results.
        """
        # Use workflow.now() instead of datetime.utcnow() to comply with Temporal sandbox
        now = workflow.now().strftime('%Y-%m-%d %H:%M:%S UTC')

        sections = [
            "# Cross-Repository Architecture Overview",
            "",
            "This document was automatically generated by RepoSwarm's cross-repo analysis.",
            f"Generated on: {now}",
            "",
            "---",
            "",
        ]

        for step in processing_order:
            step_name = step["name"]
            description = step.get("description", "")

            if step_name not in step_results:
                continue

            # Get the result content
            result_key = step_results[step_name]
            content = results_map.get(step_name, "")

            if not content:
                # Try to find by result key
                for key, val in results_map.items():
                    if val and step_name in key:
                        content = val
                        break

            if content:
                sections.append(f"## {description}")
                sections.append("")
                sections.append(content)
                sections.append("")
                sections.append("---")
                sections.append("")

        return "\n".join(sections)

    async def _save_output(self, request: CrossRepoAnalysisRequest, content: str) -> dict:
        """
        Save the diagram output to the appropriate location.
        Optionally renders Mermaid blocks to PNG if RENDER_MERMAID_PNGS is enabled.
        """
        if request.local_mode:
            # Save locally to outputs/diagrams/
            output_dir = request.output_dir or "outputs"
            result = await workflow.execute_activity(
                write_local_diagrams_activity,
                args=[output_dir, content, "architecture-overview.md"],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            # Render Mermaid blocks to PNG if enabled (non-fatal)
            from investigator.core.config import Config
            if Config.RENDER_MERMAID_PNGS and result.get("status") == "success":
                file_path = result.get("file_path", "")
                if file_path:
                    try:
                        render_result = await workflow.execute_activity(
                            render_mermaid_pngs_activity,
                            args=[file_path],
                            start_to_close_timeout=timedelta(minutes=15),
                            retry_policy=RetryPolicy(maximum_attempts=2),
                        )
                        result["png_rendering"] = render_result
                        logger.info(f"PNG rendering: {render_result.get('message', 'unknown')}")
                    except Exception as e:
                        logger.warning(f"PNG rendering failed (non-fatal): {str(e)}")
                        result["png_rendering"] = {"status": "failed", "error": str(e)}

            return result
        else:
            # Save to architecture hub
            arch_data = [{
                "repo_name": "architecture-overview",
                "arch_file_content": content
            }]
            result = await workflow.execute_activity(
                save_to_arch_hub,
                args=[arch_data],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=5),
                    maximum_interval=timedelta(seconds=30),
                ),
            )
            return result
