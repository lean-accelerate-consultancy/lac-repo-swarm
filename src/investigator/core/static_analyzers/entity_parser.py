"""
EntityParser -- extracts core entities from source code: Java classes/interfaces,
Go structs, Python classes, and Terraform resource groups.

Covers section: core_entities
"""

import re
from pathlib import Path
from collections import defaultdict


class EntityParser:
    """Extracts core entity definitions from source code."""

    SKIP_DIRS = {".terraform", "node_modules", ".venv", "venv", "vendor",
                 ".git", "__pycache__", "dist", "build", "target", "test",
                 "tests", "__tests__", "spec"}

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def parse(self) -> dict:
        """Parse the repo for entity definitions."""
        result = {
            "java_entities": [],
            "go_entities": [],
            "python_entities": [],
            "terraform_entities": [],
        }

        if not self.repo_path.exists():
            return result

        self._parse_java(result)
        self._parse_go(result)
        self._parse_python(result)
        self._parse_terraform(result)

        return result

    def _should_skip(self, path: Path) -> bool:
        return any(d in path.parts for d in self.SKIP_DIRS)

    def _parse_java(self, result: dict):
        """Extract Java class, interface, enum, and record declarations."""
        pattern = re.compile(
            r'(?:public\s+|private\s+|protected\s+)?'
            r'(?:abstract\s+|final\s+|static\s+)*'
            r'(class|interface|enum|record)\s+'
            r'(\w+)'
            r'(?:\s+extends\s+(\w+))?'
            r'(?:\s+implements\s+([\w,\s]+))?'
        )

        for f in self.repo_path.rglob("*.java"):
            if self._should_skip(f):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except (OSError, IOError):
                continue

            rel_path = str(f.relative_to(self.repo_path))

            # Extract package
            pkg_match = re.search(r'^package\s+([\w.]+);', content, re.MULTILINE)
            package = pkg_match.group(1) if pkg_match else ""

            for match in pattern.finditer(content):
                entity_type = match.group(1)
                name = match.group(2)
                extends = match.group(3) or ""
                implements = match.group(4) or ""
                implements = [i.strip() for i in implements.split(",") if i.strip()] if implements else []

                result["java_entities"].append({
                    "name": name,
                    "type": entity_type,
                    "package": package,
                    "extends": extends,
                    "implements": implements,
                    "file": rel_path,
                })

    def _parse_go(self, result: dict):
        """Extract Go struct and interface declarations."""
        struct_pattern = re.compile(r'type\s+(\w+)\s+struct\s*\{')
        iface_pattern = re.compile(r'type\s+(\w+)\s+interface\s*\{')

        for f in self.repo_path.rglob("*.go"):
            if self._should_skip(f):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except (OSError, IOError):
                continue

            rel_path = str(f.relative_to(self.repo_path))

            # Extract package
            pkg_match = re.search(r'^package\s+(\w+)', content, re.MULTILINE)
            package = pkg_match.group(1) if pkg_match else ""

            for match in struct_pattern.finditer(content):
                result["go_entities"].append({
                    "name": match.group(1),
                    "type": "struct",
                    "package": package,
                    "file": rel_path,
                })

            for match in iface_pattern.finditer(content):
                result["go_entities"].append({
                    "name": match.group(1),
                    "type": "interface",
                    "package": package,
                    "file": rel_path,
                })

    def _parse_python(self, result: dict):
        """Extract Python class declarations."""
        pattern = re.compile(
            r'^class\s+(\w+)\s*(?:\(([^)]*)\))?\s*:',
            re.MULTILINE,
        )

        for f in self.repo_path.rglob("*.py"):
            if self._should_skip(f):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except (OSError, IOError):
                continue

            rel_path = str(f.relative_to(self.repo_path))

            for match in pattern.finditer(content):
                name = match.group(1)
                bases = match.group(2) or ""
                bases = [b.strip() for b in bases.split(",") if b.strip()] if bases else []

                result["python_entities"].append({
                    "name": name,
                    "type": "class",
                    "bases": bases,
                    "file": rel_path,
                })

    def _parse_terraform(self, result: dict):
        """Group Terraform resources into logical entity groups."""
        resource_pattern = re.compile(
            r'resource\s+"(\w+)"\s+"(\w+)"',
        )

        resources_by_prefix = defaultdict(list)

        for f in self.repo_path.rglob("*.tf"):
            if ".terraform" in str(f):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except (OSError, IOError):
                continue

            rel_path = str(f.relative_to(self.repo_path))

            for match in resource_pattern.finditer(content):
                res_type = match.group(1)
                res_name = match.group(2)
                # Group by service prefix (e.g., aws_vpc, aws_subnet -> vpc group)
                prefix = self._extract_service_prefix(res_type)
                resources_by_prefix[prefix].append({
                    "type": res_type,
                    "name": res_name,
                    "file": rel_path,
                })

        for prefix, resources in resources_by_prefix.items():
            result["terraform_entities"].append({
                "name": prefix.replace("_", " ").title(),
                "type": "resource_group",
                "resource_count": len(resources),
                "resources": resources,
                "files": list(set(r["file"] for r in resources)),
            })

    def _extract_service_prefix(self, resource_type: str) -> str:
        """Extract logical service prefix from a resource type."""
        # Remove provider prefix (aws_, azurerm_, google_)
        for provider in ("aws_", "azurerm_", "google_", "kubernetes_", "helm_"):
            if resource_type.startswith(provider):
                resource_type = resource_type[len(provider):]
                break

        # Group by first meaningful word
        parts = resource_type.split("_")
        if parts:
            return parts[0]
        return resource_type

    def format_as_markdown(self, data: dict) -> str:
        """Format entity data as markdown."""
        java = data.get("java_entities", [])
        go = data.get("go_entities", [])
        python = data.get("python_entities", [])
        terraform = data.get("terraform_entities", [])

        if not java and not go and not python and not terraform:
            return ("*No entity definitions detected (classes, structs, interfaces, or resource groups).*\n\n"
                    "---\n*Generated by static analysis (ENABLE_AI=false)*")

        lines = []

        if java:
            lines.append("**Java Entities:**\n")
            lines.append("| Name | Type | Package | Extends | File |")
            lines.append("|------|------|---------|---------|------|")
            for e in sorted(java, key=lambda x: x["name"]):
                extends = e["extends"] or "-"
                impl = ", ".join(e["implements"]) if e["implements"] else ""
                if impl:
                    extends += f" (implements: {impl})"
                lines.append(f"| `{e['name']}` | {e['type']} | {e['package']} | {extends} | {e['file']} |")
            lines.append("")

        if go:
            lines.append("**Go Entities:**\n")
            lines.append("| Name | Type | Package | File |")
            lines.append("|------|------|---------|------|")
            for e in sorted(go, key=lambda x: x["name"]):
                lines.append(f"| `{e['name']}` | {e['type']} | {e['package']} | {e['file']} |")
            lines.append("")

        if python:
            lines.append("**Python Entities:**\n")
            lines.append("| Name | Bases | File |")
            lines.append("|------|-------|------|")
            for e in sorted(python, key=lambda x: x["name"]):
                bases = ", ".join(e["bases"]) if e["bases"] else "-"
                lines.append(f"| `{e['name']}` | {bases} | {e['file']} |")
            lines.append("")

        if terraform:
            lines.append("**Terraform Resource Groups:**\n")
            lines.append("| Group | Resources | Files |")
            lines.append("|-------|----------:|-------|")
            for e in sorted(terraform, key=lambda x: -x["resource_count"]):
                files = ", ".join(e["files"][:3])
                if len(e["files"]) > 3:
                    files += f" (+{len(e['files']) - 3} more)"
                lines.append(f"| {e['name']} | {e['resource_count']} | {files} |")

        lines.append("\n---")
        lines.append("*Generated by static analysis (ENABLE_AI=false)*")
        return "\n".join(lines)
