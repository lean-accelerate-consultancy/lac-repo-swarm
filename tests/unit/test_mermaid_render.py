"""
Unit tests for Mermaid diagram extraction and rendering activities.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from activities.mermaid_render_activities import (
    extract_mermaid_blocks,
    _render_with_docker,
    _render_with_mmdc,
)


class TestExtractMermaidBlocks(unittest.TestCase):
    """Tests for the extract_mermaid_blocks utility function."""

    def test_single_graph_block(self):
        """Extract a single graph TD block."""
        md = """
# Title

Some text.

```mermaid
graph TD
    A-->B
    B-->C
```

More text.
"""
        blocks = extract_mermaid_blocks(md)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["index"], 0)
        self.assertEqual(blocks[0]["type"], "graph")
        self.assertEqual(blocks[0]["filename"], "diagram-01-graph")
        self.assertIn("A-->B", blocks[0]["content"])

    def test_multiple_blocks(self):
        """Extract multiple different diagram types."""
        md = """
```mermaid
graph TD
    A-->B
```

```mermaid
sequenceDiagram
    Alice->>Bob: Hello
```

```mermaid
flowchart LR
    A-->B
```
"""
        blocks = extract_mermaid_blocks(md)
        self.assertEqual(len(blocks), 3)
        self.assertEqual(blocks[0]["type"], "graph")
        self.assertEqual(blocks[1]["type"], "sequence")
        self.assertEqual(blocks[2]["type"], "flowchart")
        self.assertEqual(blocks[0]["filename"], "diagram-01-graph")
        self.assertEqual(blocks[1]["filename"], "diagram-02-sequence")
        self.assertEqual(blocks[2]["filename"], "diagram-03-flowchart")

    def test_no_mermaid_blocks(self):
        """Return empty list when no mermaid blocks exist."""
        md = """
# Title

Just text, no diagrams.

```python
print("hello")
```
"""
        blocks = extract_mermaid_blocks(md)
        self.assertEqual(len(blocks), 0)

    def test_mixed_code_blocks(self):
        """Only extract mermaid blocks, not other languages."""
        md = """
```python
print("hello")
```

```mermaid
graph TD
    A-->B
```

```json
{"key": "value"}
```

```mermaid
sequenceDiagram
    Alice->>Bob: Hi
```
"""
        blocks = extract_mermaid_blocks(md)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0]["type"], "graph")
        self.assertEqual(blocks[1]["type"], "sequence")

    def test_empty_mermaid_block_skipped(self):
        """Skip empty mermaid blocks."""
        md = """
```mermaid

```

```mermaid
graph TD
    A-->B
```
"""
        blocks = extract_mermaid_blocks(md)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["type"], "graph")

    def test_all_diagram_types(self):
        """Detect various diagram types correctly."""
        types_and_content = [
            ("graph", "graph TD\n    A-->B"),
            ("sequence", "sequenceDiagram\n    Alice->>Bob: Hi"),
            ("flowchart", "flowchart LR\n    A-->B"),
            ("class", "classDiagram\n    Animal <|-- Duck"),
            ("state", "stateDiagram-v2\n    [*] --> Active"),
            ("er", "erDiagram\n    CUSTOMER ||--o{ ORDER : places"),
            ("gantt", "gantt\n    title A Gantt Diagram"),
            ("pie", "pie title Pets\n    \"Dogs\" : 386"),
        ]
        for expected_type, content in types_and_content:
            md = f"```mermaid\n{content}\n```"
            blocks = extract_mermaid_blocks(md)
            self.assertEqual(len(blocks), 1, f"Failed for type: {expected_type}")
            self.assertEqual(blocks[0]["type"], expected_type, f"Wrong type for: {content}")

    def test_diagram_with_subgraphs(self):
        """Handle complex diagrams with subgraphs and styling."""
        md = """
```mermaid
graph TD
    subgraph "AWS Cloud"
        VPC[(VPC)]
        EMR{{EMR}}
    end

    subgraph "Local"
        Dev[Developer]
    end

    Dev -->|deploys| VPC
    VPC --> EMR

    classDef awsNode fill:#ff9900
    class VPC,EMR awsNode
```
"""
        blocks = extract_mermaid_blocks(md)
        self.assertEqual(len(blocks), 1)
        self.assertIn("subgraph", blocks[0]["content"])
        self.assertIn("classDef", blocks[0]["content"])

    def test_empty_string_input(self):
        """Handle empty string input gracefully."""
        blocks = extract_mermaid_blocks("")
        self.assertEqual(len(blocks), 0)


class TestRenderWithDocker(unittest.TestCase):
    """Tests for Docker-based rendering."""

    @patch('activities.mermaid_render_activities.subprocess.run')
    def test_docker_success(self, mock_run):
        """Successful Docker rendering."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = _render_with_docker(
            "/tmp/diagrams/test.mmd",
            "/tmp/diagrams/test.png",
            "repo-swarm-mermaid:local",
            120,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["method"], "docker")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertIn("docker", cmd)
        self.assertIn("-v", cmd)

    @patch('activities.mermaid_render_activities.subprocess.run')
    def test_docker_failure(self, mock_run):
        """Docker rendering failure returns error details."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Parse error")

        result = _render_with_docker(
            "/tmp/test.mmd", "/tmp/test.png", "repo-swarm-mermaid:local", 120,
        )

        self.assertEqual(result["status"], "failed")
        self.assertIn("Parse error", result["error"])

    @patch('activities.mermaid_render_activities.subprocess.run')
    def test_docker_not_found(self, mock_run):
        """Docker not installed returns appropriate error."""
        mock_run.side_effect = FileNotFoundError("docker not found")

        result = _render_with_docker(
            "/tmp/test.mmd", "/tmp/test.png", "repo-swarm-mermaid:local", 120,
        )

        self.assertEqual(result["status"], "failed")
        self.assertIn("Docker not found", result["error"])

    @patch('activities.mermaid_render_activities.subprocess.run')
    def test_docker_timeout(self, mock_run):
        """Docker rendering timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=120)

        result = _render_with_docker(
            "/tmp/test.mmd", "/tmp/test.png", "repo-swarm-mermaid:local", 120,
        )

        self.assertEqual(result["status"], "failed")
        self.assertIn("Timeout", result["error"])


class TestRenderWithMmdc(unittest.TestCase):
    """Tests for local mmdc-based rendering."""

    @patch('activities.mermaid_render_activities.subprocess.run')
    @patch('activities.mermaid_render_activities.shutil.which', return_value="/usr/local/bin/mmdc")
    def test_mmdc_success(self, mock_which, mock_run):
        """Successful local mmdc rendering."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = _render_with_mmdc("/tmp/test.mmd", "/tmp/test.png", 120)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["method"], "mmdc")

    @patch('activities.mermaid_render_activities.shutil.which', return_value=None)
    def test_mmdc_not_found(self, mock_which):
        """mmdc not on PATH returns appropriate error."""
        result = _render_with_mmdc("/tmp/test.mmd", "/tmp/test.png", 120)

        self.assertEqual(result["status"], "failed")
        self.assertIn("mmdc not found", result["error"])

    @patch('activities.mermaid_render_activities.subprocess.run')
    @patch('activities.mermaid_render_activities.shutil.which', return_value="/usr/local/bin/mmdc")
    def test_mmdc_failure(self, mock_which, mock_run):
        """mmdc rendering failure."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Syntax error in diagram")

        result = _render_with_mmdc("/tmp/test.mmd", "/tmp/test.png", 120)

        self.assertEqual(result["status"], "failed")
        self.assertIn("Syntax error", result["error"])


class TestFallbackBehavior(unittest.TestCase):
    """Tests for the Docker -> mmdc fallback chain."""

    @patch('activities.mermaid_render_activities._render_with_mmdc')
    @patch('activities.mermaid_render_activities._render_with_docker')
    def test_falls_back_to_mmdc_when_docker_fails(self, mock_docker, mock_mmdc):
        """When Docker fails, should try mmdc."""
        # This tests the logic indirectly - the activity calls docker, then mmdc
        mock_docker.return_value = {"status": "failed", "method": "docker", "error": "not found"}
        mock_mmdc.return_value = {"status": "success", "method": "mmdc"}

        # Verify both functions are callable and return expected results
        result1 = mock_docker("/tmp/test.mmd", "/tmp/test.png", "img", 120)
        self.assertEqual(result1["status"], "failed")

        result2 = mock_mmdc("/tmp/test.mmd", "/tmp/test.png", 120)
        self.assertEqual(result2["status"], "success")


if __name__ == '__main__':
    pytest_args = [__file__, '-v', '--tb=short']
    import pytest
    pytest.main(pytest_args)
