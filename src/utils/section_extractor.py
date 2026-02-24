"""
Section extractor utility for parsing markdown architecture files.

Extracts specific H1 sections from arch file content to reduce token usage
when building cross-repo analysis prompts.
"""

import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)


def extract_sections(arch_content: str, section_names: List[str]) -> str:
    """
    Extract specific H1 sections from markdown arch file content.

    Parses the markdown by H1 headers (# section_name) and returns
    only the requested sections concatenated together.

    Args:
        arch_content: Full markdown content of an arch file
        section_names: List of section names to extract (case-insensitive)

    Returns:
        Concatenated content of the matching sections, or empty string if none found
    """
    if not arch_content or not section_names:
        return ""

    # Normalize section names to lowercase for case-insensitive matching
    target_sections = {name.lower().strip() for name in section_names}

    # Split content into sections by H1 headers
    sections = _parse_h1_sections(arch_content)

    # Filter to only the requested sections
    matched_sections = []
    for section_name, section_content in sections:
        if section_name.lower().strip() in target_sections:
            matched_sections.append(f"# {section_name}\n\n{section_content}")

    if not matched_sections:
        logger.warning(
            f"No matching sections found. "
            f"Requested: {section_names}, "
            f"Available: {[name for name, _ in sections]}"
        )
        return ""

    logger.debug(
        f"Extracted {len(matched_sections)}/{len(section_names)} sections "
        f"({sum(len(s) for s in matched_sections)} chars)"
    )

    return "\n\n".join(matched_sections)


def _parse_h1_sections(content: str) -> List[tuple]:
    """
    Parse markdown content into H1 sections.

    Args:
        content: Markdown content to parse

    Returns:
        List of (section_name, section_content) tuples
    """
    sections = []

    # Split on H1 headers (lines starting with "# ")
    # Use regex to find all H1 header positions
    h1_pattern = re.compile(r'^# (.+)$', re.MULTILINE)
    matches = list(h1_pattern.finditer(content))

    if not matches:
        return sections

    for i, match in enumerate(matches):
        section_name = match.group(1).strip()

        # Get content between this header and the next (or end of file)
        start = match.end()
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(content)

        section_content = content[start:end].strip()
        sections.append((section_name, section_content))

    return sections


def get_available_sections(arch_content: str) -> List[str]:
    """
    Get a list of all H1 section names in the arch file content.

    Args:
        arch_content: Full markdown content of an arch file

    Returns:
        List of section names found in the content
    """
    if not arch_content:
        return []

    sections = _parse_h1_sections(arch_content)
    return [name for name, _ in sections]


def build_cross_repo_analysis_input(
    repo_contents: dict,
    section_names: Optional[List[str]] = None
) -> str:
    """
    Build the {all_repos_analysis} placeholder content for cross-repo prompts.

    Concatenates analysis content from multiple repos, optionally extracting
    only specific sections from each.

    Args:
        repo_contents: Dict mapping repo_name to arch_file_content
        section_names: Optional list of section names to extract from each repo.
                      If None, includes full content.

    Returns:
        Formatted string with all repos' analysis content
    """
    if not repo_contents:
        return ""

    parts = []
    for repo_name, content in sorted(repo_contents.items()):
        if not content:
            logger.warning(f"Empty content for repo: {repo_name}")
            continue

        if section_names:
            extracted = extract_sections(content, section_names)
            if extracted:
                parts.append(f"## Repository: {repo_name}\n\n{extracted}")
            else:
                logger.warning(f"No matching sections found in {repo_name}")
        else:
            parts.append(f"## Repository: {repo_name}\n\n{content}")

    result = "\n\n---\n\n".join(parts)
    logger.info(
        f"Built cross-repo analysis input: {len(repo_contents)} repos, "
        f"{len(parts)} with content, {len(result)} chars total"
    )
    return result


def build_repos_metadata_text(repos_metadata: dict) -> str:
    """
    Build the {repos_metadata} placeholder content for cross-repo prompts.

    Formats repository metadata into a readable text block.

    Args:
        repos_metadata: Dict mapping repo_name to {url, type, description}

    Returns:
        Formatted metadata text
    """
    if not repos_metadata:
        return "No repository metadata available."

    lines = []
    for repo_name, meta in sorted(repos_metadata.items()):
        repo_type = meta.get("type", "generic")
        description = meta.get("description", "No description")
        uri = meta.get("uri", "N/A")
        lines.append(f"- **{repo_name}** ({repo_type}): {description} [{uri}]")

    return "\n".join(lines)
