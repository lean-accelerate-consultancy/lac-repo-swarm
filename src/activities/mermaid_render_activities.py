"""
Mermaid diagram rendering activities.

Extracts Mermaid code blocks from markdown and renders them to PNG files
using either Docker (preferred) or local mmdc (fallback).
"""

import os
import re
import shutil
import subprocess
from temporalio import activity

from investigator.core.config import Config


def extract_mermaid_blocks(markdown_content: str) -> list:
    """
    Extract all Mermaid code blocks from markdown content.

    Args:
        markdown_content: Markdown string potentially containing ```mermaid blocks

    Returns:
        List of dicts with keys: index, content, type, filename
    """
    pattern = r'```mermaid\s*\n(.*?)```'
    matches = re.findall(pattern, markdown_content, re.DOTALL)

    blocks = []
    for i, content in enumerate(matches):
        content = content.strip()
        if not content:
            continue

        # Detect diagram type from first line
        first_line = content.split('\n')[0].strip()
        if first_line.startswith('graph'):
            diagram_type = 'graph'
        elif first_line.startswith('sequenceDiagram'):
            diagram_type = 'sequence'
        elif first_line.startswith('flowchart'):
            diagram_type = 'flowchart'
        elif first_line.startswith('classDiagram'):
            diagram_type = 'class'
        elif first_line.startswith('stateDiagram'):
            diagram_type = 'state'
        elif first_line.startswith('erDiagram'):
            diagram_type = 'er'
        elif first_line.startswith('gantt'):
            diagram_type = 'gantt'
        elif first_line.startswith('pie'):
            diagram_type = 'pie'
        else:
            diagram_type = 'diagram'

        filename = f"diagram-{i + 1:02d}-{diagram_type}"

        blocks.append({
            "index": i,
            "content": content,
            "type": diagram_type,
            "filename": filename,
        })

    return blocks


def _render_with_docker(mmd_path: str, png_path: str, docker_image: str, timeout: int) -> dict:
    """
    Render a .mmd file to PNG using Docker.

    Args:
        mmd_path: Absolute path to the .mmd file
        png_path: Absolute path for the output .png file
        docker_image: Docker image name (e.g., repo-swarm-mermaid:local)
        timeout: Timeout in seconds

    Returns:
        Dict with status, method, and optional error
    """
    diagrams_dir = os.path.dirname(mmd_path)
    mmd_name = os.path.basename(mmd_path)
    png_name = os.path.basename(png_path)

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{diagrams_dir}:/data",
        docker_image,
        "-i", f"/data/{mmd_name}",
        "-o", f"/data/{png_name}",
        "-b", "white",
        "-w", "2048",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return {"status": "success", "method": "docker"}
        else:
            return {
                "status": "failed",
                "method": "docker",
                "error": result.stderr or f"Exit code {result.returncode}",
            }
    except subprocess.TimeoutExpired:
        return {"status": "failed", "method": "docker", "error": f"Timeout after {timeout}s"}
    except FileNotFoundError:
        return {"status": "failed", "method": "docker", "error": "Docker not found on PATH"}
    except Exception as e:
        return {"status": "failed", "method": "docker", "error": str(e)}


def _render_with_mmdc(mmd_path: str, png_path: str, timeout: int) -> dict:
    """
    Render a .mmd file to PNG using local mmdc.

    Args:
        mmd_path: Absolute path to the .mmd file
        png_path: Absolute path for the output .png file
        timeout: Timeout in seconds

    Returns:
        Dict with status, method, and optional error
    """
    mmdc_path = shutil.which("mmdc")
    if not mmdc_path:
        return {"status": "failed", "method": "mmdc", "error": "mmdc not found on PATH"}

    cmd = [mmdc_path, "-i", mmd_path, "-o", png_path, "-b", "white", "-w", "2048"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return {"status": "success", "method": "mmdc"}
        else:
            return {
                "status": "failed",
                "method": "mmdc",
                "error": result.stderr or f"Exit code {result.returncode}",
            }
    except subprocess.TimeoutExpired:
        return {"status": "failed", "method": "mmdc", "error": f"Timeout after {timeout}s"}
    except Exception as e:
        return {"status": "failed", "method": "mmdc", "error": str(e)}


@activity.defn
async def render_mermaid_pngs_activity(markdown_file_path: str) -> dict:
    """
    Activity to extract Mermaid blocks from a markdown file and render them to PNG.

    Uses Docker with repo-swarm-mermaid image (preferred), falls back to local mmdc,
    or skips gracefully if neither is available.

    Args:
        markdown_file_path: Absolute path to the markdown file containing Mermaid blocks

    Returns:
        Dictionary with status, rendered_count, failed_count, png_files, and message
    """
    activity.logger.info(f"Rendering Mermaid PNGs from: {markdown_file_path}")

    docker_image = getattr(Config, 'MERMAID_DOCKER_IMAGE', 'repo-swarm-mermaid:local')
    timeout = getattr(Config, 'MERMAID_RENDER_TIMEOUT', 120)

    # Read the markdown file
    try:
        with open(markdown_file_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
    except Exception as e:
        activity.logger.error(f"Failed to read markdown file: {e}")
        return {
            "status": "failed",
            "rendered_count": 0,
            "failed_count": 0,
            "png_files": [],
            "message": f"Failed to read markdown file: {e}",
        }

    # Extract mermaid blocks
    blocks = extract_mermaid_blocks(markdown_content)
    if not blocks:
        activity.logger.info("No Mermaid blocks found in markdown")
        return {
            "status": "success",
            "rendered_count": 0,
            "failed_count": 0,
            "png_files": [],
            "message": "No Mermaid blocks found",
        }

    activity.logger.info(f"Found {len(blocks)} Mermaid block(s) to render")
    diagrams_dir = os.path.dirname(markdown_file_path)

    rendered = []
    failed = []

    for block in blocks:
        mmd_filename = f"{block['filename']}.mmd"
        png_filename = f"{block['filename']}.png"
        mmd_path = os.path.join(diagrams_dir, mmd_filename)
        png_path = os.path.join(diagrams_dir, png_filename)

        # Write .mmd file
        try:
            with open(mmd_path, 'w', encoding='utf-8') as f:
                f.write(block['content'])
        except Exception as e:
            activity.logger.error(f"Failed to write {mmd_filename}: {e}")
            failed.append({"filename": mmd_filename, "error": str(e)})
            continue

        # Try Docker first, then local mmdc
        result = _render_with_docker(mmd_path, png_path, docker_image, timeout)

        if result["status"] != "success":
            docker_error = result.get("error", "unknown")
            activity.logger.info(f"Docker rendering failed for {mmd_filename}: {docker_error}, trying local mmdc...")
            result = _render_with_mmdc(mmd_path, png_path, timeout)

        if result["status"] == "success":
            activity.logger.info(f"Rendered {png_filename} via {result['method']}")
            rendered.append({
                "filename": png_filename,
                "path": png_path,
                "method": result["method"],
                "type": block["type"],
            })
        else:
            activity.logger.warning(
                f"Failed to render {mmd_filename}: {result.get('error', 'unknown')} "
                f"(tried: {result['method']})"
            )
            failed.append({
                "filename": mmd_filename,
                "error": result.get("error", "unknown"),
            })

    # Build summary
    total = len(blocks)
    rendered_count = len(rendered)
    failed_count = len(failed)

    if rendered_count == total:
        status = "success"
        message = f"All {total} diagram(s) rendered to PNG"
    elif rendered_count > 0:
        status = "partial"
        message = f"Rendered {rendered_count}/{total} diagrams ({failed_count} failed)"
    else:
        status = "skipped"
        message = f"No diagrams rendered (Docker and mmdc unavailable or all {total} failed)"

    activity.logger.info(f"PNG rendering complete: {message}")

    return {
        "status": status,
        "rendered_count": rendered_count,
        "failed_count": failed_count,
        "png_files": [r["path"] for r in rendered],
        "details": rendered,
        "failures": failed,
        "message": message,
    }
