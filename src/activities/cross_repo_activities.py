"""
Cross-repo analysis activities for Mermaid diagram generation.

These activities support the CrossRepoAnalysisWorkflow by providing
file I/O operations for reading arch files and writing diagram output.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import glob
import logging
from temporalio import activity

logger = logging.getLogger(__name__)


@activity.defn
async def get_cross_repo_prompts_config_activity() -> dict:
    """
    Activity to read the cross-repo prompts configuration.

    Reads prompts/cross_repo/prompts.json and returns the processing order.

    Returns:
        Dictionary with processing_order and prompts_dir
    """
    activity.logger.info("Reading cross-repo prompts configuration")

    try:
        # Get the prompts directory path
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        prompts_dir = os.path.join(project_root, "prompts", "cross_repo")
        config_path = os.path.join(prompts_dir, "prompts.json")

        if not os.path.exists(config_path):
            raise Exception(f"Cross-repo prompts config not found: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        processing_order = config.get("processing_order", [])
        activity.logger.info(f"Loaded {len(processing_order)} cross-repo prompt steps")

        # Extract prompt versions
        from investigator.core.file_manager import FileManager
        file_manager = FileManager(activity.logger)
        prompt_versions = {}

        for step in processing_order:
            prompt_file = step.get("file", "")
            prompt_content = file_manager.read_prompt_file(prompts_dir, prompt_file)
            if prompt_content:
                from investigator.core.analysis_results_collector import AnalysisResultsCollector
                try:
                    version = AnalysisResultsCollector.extract_prompt_version(prompt_content)
                    prompt_versions[step["name"]] = version
                except ValueError:
                    prompt_versions[step["name"]] = "1"

        return {
            "status": "success",
            "prompts_dir": prompts_dir,
            "processing_order": processing_order,
            "prompt_versions": prompt_versions
        }

    except Exception as e:
        activity.logger.error(f"Failed to read cross-repo prompts config: {str(e)}")
        raise Exception(f"Failed to read cross-repo prompts config: {str(e)}") from e


@activity.defn
async def read_local_arch_files_activity(input_dir: str) -> dict:
    """
    Activity to read all *.arch.md files from a local directory.

    Used in local mode to collect analysis results that were previously
    saved locally, for feeding into cross-repo diagram generation.

    Args:
        input_dir: Path to directory containing *.arch.md files

    Returns:
        Dictionary mapping repo_name to arch file content
    """
    # Resolve relative paths against project root (worker may run from src/)
    if not os.path.isabs(input_dir):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        input_dir = os.path.join(project_root, input_dir)

    activity.logger.info(f"Reading local arch files from: {input_dir}")

    try:
        if not os.path.exists(input_dir):
            raise Exception(f"Input directory does not exist: {input_dir}")

        # Find all *.arch.md files
        pattern = os.path.join(input_dir, "*.arch.md")
        arch_files = glob.glob(pattern)

        # Also check for *-arch.md pattern
        pattern_alt = os.path.join(input_dir, "*-arch.md")
        arch_files_alt = glob.glob(pattern_alt)

        # Combine and deduplicate
        all_files = list(set(arch_files + arch_files_alt))

        if not all_files:
            activity.logger.warning(f"No .arch.md files found in {input_dir}")
            return {
                "status": "success",
                "repo_contents": {},
                "file_count": 0,
                "message": f"No .arch.md files found in {input_dir}"
            }

        repo_contents = {}
        for file_path in all_files:
            filename = os.path.basename(file_path)
            # Extract repo name: remove .arch.md or -arch.md suffix
            repo_name = filename
            if repo_name.endswith('.arch.md'):
                repo_name = repo_name[:-8]
            elif repo_name.endswith('-arch.md'):
                repo_name = repo_name[:-8]

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            repo_contents[repo_name] = content
            activity.logger.info(f"Read {filename}: {len(content)} chars")

        activity.logger.info(f"Read {len(repo_contents)} arch files from {input_dir}")

        return {
            "status": "success",
            "repo_contents": repo_contents,
            "file_count": len(repo_contents),
            "message": f"Read {len(repo_contents)} arch files"
        }

    except Exception as e:
        activity.logger.error(f"Failed to read local arch files: {str(e)}")
        raise Exception(f"Failed to read local arch files: {str(e)}") from e


@activity.defn
async def write_local_diagrams_activity(output_dir: str, content: str, filename: str = "architecture-overview.md") -> dict:
    """
    Activity to write cross-repo diagram output to a local directory.

    Writes to outputs/diagrams/ by default.

    Args:
        output_dir: Base output directory (e.g., 'outputs')
        content: The diagram markdown content to write
        filename: Output filename (default: architecture-overview.md)

    Returns:
        Dictionary with the path to the written file
    """
    activity.logger.info(f"Writing diagrams to {output_dir}/diagrams/{filename}")

    try:
        # Get the project root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        diagrams_dir = os.path.join(project_root, output_dir, "diagrams")

        # Create directory if it doesn't exist
        os.makedirs(diagrams_dir, exist_ok=True)

        # Write the file
        file_path = os.path.join(diagrams_dir, filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        activity.logger.info(f"Diagrams written to: {file_path} ({len(content)} chars)")

        return {
            "status": "success",
            "file_path": file_path,
            "message": f"Diagrams written to {file_path}"
        }

    except Exception as e:
        activity.logger.error(f"Failed to write diagrams: {str(e)}")
        raise Exception(f"Failed to write diagrams: {str(e)}") from e
