"""
Static analysis activities for no-AI mode (ENABLE_AI=false).

These activities replace Claude API calls with automated static code
analysis. They reuse the same input/output models as the Claude activities
so the workflow layer requires minimal changes.
"""

import os
import sys

from temporalio import activity

from models.activities import (
    AnalyzeWithClaudeInput,
    AnalyzeWithClaudeOutput,
    PromptContextDict,
)


@activity.defn
async def analyze_with_static_context(
    input_params: AnalyzeWithClaudeInput,
) -> AnalyzeWithClaudeOutput:
    """
    Activity to analyze repository content using static code analysis (no AI).

    Drop-in replacement for analyze_with_claude_context. Reuses the same
    input/output models so the workflow routing is a simple conditional.

    The flow mirrors the Claude activity:
    1. Check prompt-level cache (reuse if available)
    2. Retrieve repo_structure from storage
    3. Run StaticAnalyzer instead of ClaudeAnalyzer
    4. Save result to cache (same format)
    5. Return AnalyzeWithClaudeOutput

    Args:
        input_params: Same AnalyzeWithClaudeInput used by Claude activity.
                      repo_path field must be populated for static analysis.

    Returns:
        AnalyzeWithClaudeOutput with the static analysis result.
    """
    context_dict = input_params.context_dict.model_dump()
    latest_commit = input_params.latest_commit
    repo_path = input_params.repo_path

    repo_name = context_dict.get("repo_name")
    step_name = context_dict.get("step_name")

    activity.logger.info(
        f"Starting static analysis for step: {step_name} (ENABLE_AI=false)"
    )

    if not repo_path:
        raise Exception(
            f"repo_path is required for static analysis mode. "
            f"Ensure the workflow passes repo_path when ENABLE_AI=false."
        )

    try:
        # Import inside activity to avoid Temporal sandbox issues
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from utils.prompt_context import create_prompt_context_from_dict
        from activities.investigation_cache import InvestigationCache
        import logging

        # ------------------------------------------------------------------
        # Step 1: Check prompt-level cache (identical to Claude activity)
        # ------------------------------------------------------------------
        if latest_commit and repo_name and step_name:
            prompt_version = context_dict.get("prompt_version", "1")

            activity.logger.info(
                f"Checking prompt cache for {repo_name}/{step_name} "
                f"at commit {latest_commit[:8]} version={prompt_version}"
            )

            if os.environ.get("PROMPT_CONTEXT_STORAGE") == "file":
                from utils.prompt_context import create_prompt_context_manager
                storage_client = create_prompt_context_manager(repo_name)
            else:
                from utils.dynamodb_client import get_dynamodb_client
                storage_client = get_dynamodb_client()
            cache = InvestigationCache(storage_client)

            cache_check = cache.check_prompt_needs_analysis(
                repo_name, step_name, latest_commit, prompt_version
            )

            if cache_check["cached_result"]:
                cached_result = cache_check["cached_result"]
                result_key = cache_check.get("cached_result_key")
                if not result_key:
                    from utils.storage_keys import KeyNameCreator
                    cache_key_obj = KeyNameCreator.create_prompt_cache_key(
                        repo_name=repo_name,
                        step_name=step_name,
                        commit_sha=latest_commit,
                        prompt_version=prompt_version,
                    )
                    result_key = cache_key_obj.to_storage_key()

                activity.logger.info(
                    f"Using cached static result for {repo_name}/{step_name}"
                )

                context_dict_with_result = context_dict.copy()
                context_dict_with_result["result_reference_key"] = result_key

                return AnalyzeWithClaudeOutput(
                    status="success",
                    context=PromptContextDict(**context_dict_with_result),
                    result_length=len(cached_result),
                    cached=True,
                    cache_reason=cache_check["reason"],
                )
            else:
                activity.logger.info(
                    f"No cache hit for {repo_name}/{step_name} - "
                    f"{cache_check['reason']}"
                )

        # ------------------------------------------------------------------
        # Step 2: Retrieve repo_structure from storage
        # ------------------------------------------------------------------
        context = create_prompt_context_from_dict(context_dict)
        data = context.get_prompt_and_context()

        repo_structure = data["repo_structure"]
        context_to_use = data["context"]

        if not repo_structure:
            raise Exception(
                f"Invalid data: missing repo_structure for static analysis"
            )

        # ------------------------------------------------------------------
        # Step 3: Run StaticAnalyzer
        # ------------------------------------------------------------------
        from investigator.core.static_analyzer import StaticAnalyzer

        logger = logging.getLogger(__name__)
        analyzer = StaticAnalyzer(repo_path, logger)

        activity.logger.info(f"Running static analysis for '{step_name}'")
        result = analyzer.analyze_section(
            step_name=step_name,
            repo_structure=repo_structure,
            previous_context=context_to_use,
            deps_data=None,  # TODO: pass deps from workflow in Phase 2
        )

        activity.logger.info(
            f"Static analysis completed for '{step_name}' "
            f"({len(result)} characters)"
        )

        # ------------------------------------------------------------------
        # Step 4: Save result to cache (identical to Claude activity)
        # ------------------------------------------------------------------
        result_key = None
        prompt_version = context_dict.get("prompt_version", "1")

        if os.environ.get("PROMPT_CONTEXT_STORAGE") == "file":
            from utils.prompt_context import create_prompt_context_manager
            storage_client = create_prompt_context_manager(repo_name)
        else:
            from utils.dynamodb_client import get_dynamodb_client
            storage_client = get_dynamodb_client()
        cache = InvestigationCache(storage_client)

        commit_to_use = latest_commit if latest_commit else "no-commit"

        cache_save_result = cache.save_prompt_result(
            repo_name=repo_name,
            step_name=step_name,
            commit_sha=commit_to_use,
            result_content=result,
            prompt_version=prompt_version,
            ttl_days=90,
        )

        if cache_save_result["status"] == "success":
            result_key = cache_save_result["cache_key"]
            activity.logger.info(
                f"Saved static analysis result with key: {result_key}"
            )
        else:
            raise Exception(
                f"Failed to save result: {cache_save_result.get('message')}"
            )

        # ------------------------------------------------------------------
        # Step 5: Return result
        # ------------------------------------------------------------------
        context_dict_after_save = context.to_dict()
        context_dict_after_save["result_reference_key"] = result_key

        return AnalyzeWithClaudeOutput(
            status="success",
            context=PromptContextDict(**context_dict_after_save),
            result_length=len(result),
            cached=False,
        )

    except Exception as e:
        activity.logger.error(f"Static analysis failed: {str(e)}")
        raise Exception(
            f"Failed to analyze with static analysis: {str(e)}"
        ) from e


@activity.defn
async def generate_static_diagrams_activity(
    repo_contents: dict,
) -> dict:
    """
    Activity to generate Mermaid diagrams from static analysis .arch.md data.

    Replaces Claude-based diagram generation when ENABLE_AI=false.
    Parses existing .arch.md files and produces four diagram types:
    overview, tech stack, module structure, and language distribution.

    Args:
        repo_contents: dict mapping repo_name -> arch.md content string

    Returns:
        dict with status, content (markdown string), and diagram_count
    """
    activity.logger.info(
        f"Generating static Mermaid diagrams from {len(repo_contents)} repos"
    )

    try:
        from investigator.core.mermaid_diagram_generator import MermaidDiagramGenerator

        generator = MermaidDiagramGenerator(repo_contents)
        content = generator.generate_all()

        # Count mermaid code blocks in the output
        diagram_count = content.count("```mermaid")

        activity.logger.info(
            f"Generated {diagram_count} Mermaid diagrams "
            f"({len(content)} characters)"
        )

        return {
            "status": "success",
            "content": content,
            "diagram_count": diagram_count,
        }

    except Exception as e:
        activity.logger.error(f"Static diagram generation failed: {str(e)}")
        raise Exception(
            f"Failed to generate static diagrams: {str(e)}"
        ) from e
