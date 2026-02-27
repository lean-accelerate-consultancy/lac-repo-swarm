"""
Mermaid diagram rendering activities.

Extracts Mermaid code blocks from markdown and renders them to PNG files
using either Docker (preferred) or local mmdc (fallback).
"""

import os
import re
import shutil
import subprocess
import time
from temporalio import activity

from investigator.core.config import Config


def _slugify(text: str, max_length: int = 100) -> str:
    """
    Convert text to a filesystem-safe slug.

    Args:
        text: The text to slugify
        max_length: Maximum length of the resulting slug

    Returns:
        Lowercase, hyphen-separated slug string
    """
    # Lowercase and replace non-alphanumeric chars with hyphens
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower())
    # Strip leading/trailing hyphens
    slug = slug.strip('-')
    # Collapse multiple hyphens
    slug = re.sub(r'-{2,}', '-', slug)
    # Truncate to max_length at a word boundary
    if len(slug) > max_length:
        slug = slug[:max_length].rsplit('-', 1)[0]
    return slug


def _parse_mermaid_content(content: str) -> tuple:
    """
    Parse Mermaid content to extract front matter title and diagram type,
    skipping YAML front matter (--- ... ---) if present.

    Args:
        content: Raw Mermaid block content

    Returns:
        Tuple of (diagram_type, title_or_none)
    """
    lines = content.split('\n')
    title = None
    body_start = 0

    # Skip YAML front matter if present
    if lines and lines[0].strip() == '---':
        for j, line in enumerate(lines[1:], start=1):
            stripped = line.strip()
            # Extract title from front matter
            if stripped.lower().startswith('title:'):
                title = stripped.split(':', 1)[1].strip().strip('"').strip("'")
            if stripped == '---':
                body_start = j + 1
                break

    # Detect diagram type from first non-empty body line
    diagram_type = 'diagram'
    type_map = {
        'graph': 'graph',
        'sequenceDiagram': 'sequence',
        'flowchart': 'flowchart',
        'classDiagram': 'class',
        'stateDiagram': 'state',
        'erDiagram': 'er',
        'gantt': 'gantt',
        'pie': 'pie',
    }

    for line in lines[body_start:]:
        stripped = line.strip()
        if not stripped:
            continue
        for keyword, dtype in type_map.items():
            if stripped.startswith(keyword):
                diagram_type = dtype
                break
        break  # Only check the first non-empty line after front matter

    return diagram_type, title


def extract_mermaid_blocks(markdown_content: str) -> list:
    """
    Extract all Mermaid code blocks from markdown content.

    Args:
        markdown_content: Markdown string potentially containing ```mermaid blocks

    Returns:
        List of dicts with keys: index, content, type, title, filename
    """
    pattern = r'```mermaid\s*\n(.*?)```'
    matches = re.findall(pattern, markdown_content, re.DOTALL)

    blocks = []
    for i, content in enumerate(matches):
        content = content.strip()
        if not content:
            continue

        diagram_type, title = _parse_mermaid_content(content)

        # Build descriptive filename: diagram-01-graph-cross-repository-lifecycle
        if title:
            title_slug = _slugify(title)
            # Remove diagram type word from title slug to avoid duplication
            # e.g. "sequence-infrastructure-provisioning-sequence" -> "infrastructure-provisioning"
            type_word = diagram_type.lower()
            parts = title_slug.split('-')
            parts = [p for p in parts if p != type_word]
            title_slug = '-'.join(parts)
            filename = f"diagram-{i + 1:02d}-{diagram_type}-{title_slug}"
        else:
            filename = f"diagram-{i + 1:02d}-{diagram_type}"

        blocks.append({
            "index": i,
            "content": content,
            "type": diagram_type,
            "title": title,
            "filename": filename,
        })

    return blocks


def _ensure_docker_running(logger=None) -> bool:
    """
    Check if Docker is running and responsive. If not, attempt to start Colima.

    Returns:
        True if Docker is available, False otherwise.
    """
    def _log(msg, level="info"):
        if logger:
            getattr(logger, level)(msg)

    # Quick check: is Docker already responsive?
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    _log("Docker is not running. Checking for Colima...")

    # Check if colima is installed
    colima_path = shutil.which("colima")
    if not colima_path:
        _log("Colima not found on PATH, cannot auto-start Docker", level="warning")
        return False

    # Check colima status
    try:
        result = subprocess.run(
            [colima_path, "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            # Colima says it's running but Docker didn't respond — give it a moment
            _log("Colima reports running but Docker not responsive, waiting...")
            time.sleep(5)
            try:
                check = subprocess.run(
                    ["docker", "info"], capture_output=True, text=True, timeout=10
                )
                if check.returncode == 0:
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Colima is not running — start it
    _log("Starting Colima...")
    try:
        result = subprocess.run(
            [colima_path, "start"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            _log(f"Colima start failed: {result.stderr.strip()}", level="warning")
            return False
    except subprocess.TimeoutExpired:
        _log("Colima start timed out after 120s", level="warning")
        return False
    except Exception as e:
        _log(f"Failed to start Colima: {e}", level="warning")
        return False

    # Wait for Docker to become responsive after Colima starts
    _log("Colima started, waiting for Docker to be ready...")
    for attempt in range(6):
        time.sleep(5)
        try:
            check = subprocess.run(
                ["docker", "info"], capture_output=True, text=True, timeout=10
            )
            if check.returncode == 0:
                _log("Docker is now ready")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        _log(f"Waiting for Docker... (attempt {attempt + 1}/6)")

    _log("Docker did not become responsive after starting Colima", level="warning")
    return False


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

    import os as _os
    user_id = _os.getuid()
    group_id = _os.getgid()
    
    cmd = [
        "docker", "run", "--rm",
        "--user", f"{user_id}:{group_id}",
        "-e", "HOME=/tmp",
        "--shm-size=2gb",
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

    # Check Docker availability once before rendering all diagrams
    docker_available = _ensure_docker_running(logger=activity.logger)
    if docker_available:
        activity.logger.info("Docker is available — will use Docker for rendering")
    else:
        activity.logger.info("Docker is not available — will use local mmdc for rendering")

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

        # Use Docker if available, otherwise go straight to local mmdc
        if docker_available:
            result = _render_with_docker(mmd_path, png_path, docker_image, timeout)
        else:
            result = {"status": "failed", "method": "docker", "error": "skipped — Docker not available"}

        if result["status"] != "success":
            if docker_available:
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
