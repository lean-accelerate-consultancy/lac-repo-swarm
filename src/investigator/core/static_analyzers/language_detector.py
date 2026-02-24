"""
Language detection and LOC counting for static analysis mode.

Detects programming languages from file extensions, counts lines of code,
and identifies tech stack from key configuration files.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class LanguageDetector:
    """Detect languages, count LOC, and identify tech stack from a repository."""

    # Map file extensions to language names
    EXTENSION_MAP = {
        # JVM
        ".java": "Java",
        ".kt": "Kotlin",
        ".kts": "Kotlin",
        ".groovy": "Groovy",
        ".scala": "Scala",
        # Go
        ".go": "Go",
        # Python
        ".py": "Python",
        # JavaScript / TypeScript
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".mjs": "JavaScript",
        ".cjs": "JavaScript",
        # Infrastructure as Code
        ".tf": "Terraform",
        ".hcl": "HCL",
        # Configuration
        ".yml": "YAML",
        ".yaml": "YAML",
        ".json": "JSON",
        ".xml": "XML",
        ".toml": "TOML",
        ".properties": "Properties",
        # Shell
        ".sh": "Shell",
        ".bash": "Shell",
        # Web
        ".html": "HTML",
        ".css": "CSS",
        ".scss": "SCSS",
        ".less": "LESS",
        # Other
        ".rs": "Rust",
        ".rb": "Ruby",
        ".php": "PHP",
        ".cs": "C#",
        ".sql": "SQL",
        ".proto": "Protobuf",
        ".avsc": "Avro",
        ".graphql": "GraphQL",
        ".gql": "GraphQL",
    }

    # Directories to skip during scanning
    SKIP_DIRS = {
        ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
        ".tox", ".nox", ".mypy_cache", ".pytest_cache", ".cache",
        "build", "dist", "target", ".gradle", ".mvn", ".idea", ".vscode",
        ".terraform", ".terragrunt-cache", "vendor", "bin", "obj",
        ".eggs", "*.egg-info", "coverage", "htmlcov", ".next", ".nuxt",
    }

    # Key files that indicate specific technologies in the stack
    TECH_STACK_INDICATORS = {
        # Build tools / Package managers
        "pom.xml": "Maven",
        "build.gradle": "Gradle",
        "build.gradle.kts": "Gradle (Kotlin DSL)",
        "settings.gradle": "Gradle",
        "settings.gradle.kts": "Gradle (Kotlin DSL)",
        "package.json": "Node.js",
        "go.mod": "Go Modules",
        "Cargo.toml": "Cargo (Rust)",
        "Gemfile": "Bundler (Ruby)",
        "requirements.txt": "pip",
        "pyproject.toml": "Python (pyproject)",
        "Pipfile": "Pipenv",
        "setup.py": "setuptools",
        "composer.json": "Composer (PHP)",
        # Frameworks (detected from dependency files later, but filenames help)
        "Jenkinsfile": "Jenkins",
        "Makefile": "Make",
        "Rakefile": "Rake",
        # Containers & orchestration
        "Dockerfile": "Docker",
        "docker-compose.yml": "Docker Compose",
        "docker-compose.yaml": "Docker Compose",
        "Chart.yaml": "Helm",
        "values.yaml": "Helm",
        "skaffold.yaml": "Skaffold",
        "kustomization.yaml": "Kustomize",
        # IaC
        "main.tf": "Terraform",
        "terraform.tfvars": "Terraform",
        "terragrunt.hcl": "Terragrunt",
        "cloudformation.yaml": "CloudFormation",
        "cloudformation.yml": "CloudFormation",
        "template.yaml": "AWS SAM",
        # Ansible
        "ansible.cfg": "Ansible",
        "playbook.yml": "Ansible",
        "playbook.yaml": "Ansible",
        "site.yml": "Ansible",
        "site.yaml": "Ansible",
        # CI/CD
        ".gitlab-ci.yml": "GitLab CI",
        "Procfile": "Heroku",
        "app.yaml": "Google App Engine",
        "serverless.yml": "Serverless Framework",
        "serverless.yaml": "Serverless Framework",
        # API specs
        "openapi.yaml": "OpenAPI",
        "openapi.yml": "OpenAPI",
        "openapi.json": "OpenAPI",
        "swagger.yaml": "Swagger",
        "swagger.yml": "Swagger",
        "swagger.json": "Swagger",
    }

    # GitHub Actions directory indicator
    GH_ACTIONS_DIR = ".github/workflows"

    def __init__(self, logger=None):
        self.logger = logger

    def detect(self, repo_path: str) -> dict:
        """
        Scan a repository and detect languages, LOC counts, and tech stack.

        Args:
            repo_path: Absolute path to the repository root.

        Returns:
            {
                "languages": {
                    "Java": {"files": 45, "loc": 12300, "blank": 1200, "comment": 800},
                    "Python": {"files": 12, "loc": 3400, "blank": 400, "comment": 200},
                    ...
                },
                "primary_language": "Java",
                "tech_stack": ["Maven", "Docker", "Helm", "Terraform", "Jenkins"],
                "total_files": 120,
                "total_loc": 25000,
            }
        """
        repo = Path(repo_path)
        if not repo.is_dir():
            return self._empty_result()

        languages: Dict[str, Dict[str, int]] = {}
        tech_stack: List[str] = []
        total_files = 0

        for root, dirs, files in os.walk(repo):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]

            rel_root = os.path.relpath(root, repo)

            # Check for GitHub Actions
            if rel_root == self.GH_ACTIONS_DIR or rel_root.startswith(self.GH_ACTIONS_DIR + os.sep):
                if "GitHub Actions" not in tech_stack:
                    tech_stack.append("GitHub Actions")

            for filename in files:
                filepath = Path(root) / filename
                total_files += 1

                # Check tech stack indicators
                if filename in self.TECH_STACK_INDICATORS:
                    tech = self.TECH_STACK_INDICATORS[filename]
                    if tech not in tech_stack:
                        tech_stack.append(tech)

                # Detect language from extension
                ext = filepath.suffix.lower()
                lang = self.EXTENSION_MAP.get(ext)
                if lang is None:
                    continue

                # Count lines
                loc, blank, comment = self._count_lines(filepath, lang)

                if lang not in languages:
                    languages[lang] = {"files": 0, "loc": 0, "blank": 0, "comment": 0}
                languages[lang]["files"] += 1
                languages[lang]["loc"] += loc
                languages[lang]["blank"] += blank
                languages[lang]["comment"] += comment

        # Determine primary language (by LOC, excluding config formats)
        primary = self._determine_primary_language(languages)

        # Sort tech stack alphabetically for consistency
        tech_stack.sort()

        total_loc = sum(lang_data["loc"] for lang_data in languages.values())

        return {
            "languages": dict(sorted(
                languages.items(),
                key=lambda x: x[1]["loc"],
                reverse=True,
            )),
            "primary_language": primary,
            "tech_stack": tech_stack,
            "total_files": total_files,
            "total_loc": total_loc,
        }

    def _count_lines(self, filepath: Path, language: str) -> Tuple[int, int, int]:
        """
        Count lines of code, blank lines, and comment lines in a file.

        Returns:
            (loc, blank, comment) tuple
        """
        loc = 0
        blank = 0
        comment = 0

        comment_prefixes = self._get_comment_prefixes(language)
        in_block_comment = False
        block_start, block_end = self._get_block_comment_markers(language)

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    stripped = line.strip()

                    if not stripped:
                        blank += 1
                        continue

                    # Handle block comments
                    if block_start and block_end:
                        if in_block_comment:
                            comment += 1
                            if block_end in stripped:
                                in_block_comment = False
                            continue
                        if block_start in stripped:
                            comment += 1
                            if block_end not in stripped or stripped.index(block_end) <= stripped.index(block_start):
                                in_block_comment = True
                            continue

                    # Single-line comments
                    if any(stripped.startswith(prefix) for prefix in comment_prefixes):
                        comment += 1
                        continue

                    loc += 1
        except (OSError, UnicodeDecodeError):
            # Binary file or unreadable -- skip
            pass

        return loc, blank, comment

    def _get_comment_prefixes(self, language: str) -> List[str]:
        """Return single-line comment prefixes for a language."""
        c_style = ["//"]
        hash_style = ["#"]
        xml_style = ["<!--"]

        comment_map = {
            "Java": c_style,
            "Kotlin": c_style,
            "Groovy": c_style,
            "Scala": c_style,
            "Go": c_style,
            "JavaScript": c_style,
            "TypeScript": c_style,
            "Rust": c_style,
            "C#": c_style,
            "Protobuf": c_style,
            "GraphQL": c_style,
            "Python": hash_style,
            "Shell": hash_style,
            "Ruby": hash_style,
            "Terraform": hash_style,
            "HCL": hash_style,
            "YAML": hash_style,
            "TOML": hash_style,
            "Properties": hash_style,
            "PHP": c_style + hash_style,
            "HTML": xml_style,
            "XML": xml_style,
            "SQL": ["--"],
            "CSS": [],
            "SCSS": c_style,
            "LESS": c_style,
        }
        return comment_map.get(language, [])

    def _get_block_comment_markers(self, language: str) -> Tuple[Optional[str], Optional[str]]:
        """Return (start, end) markers for block comments."""
        c_style = ("/*", "*/")
        xml_style = ("<!--", "-->")

        block_map = {
            "Java": c_style,
            "Kotlin": c_style,
            "Groovy": c_style,
            "Scala": c_style,
            "Go": c_style,
            "JavaScript": c_style,
            "TypeScript": c_style,
            "Rust": c_style,
            "C#": c_style,
            "CSS": c_style,
            "SCSS": c_style,
            "LESS": c_style,
            "PHP": c_style,
            "SQL": c_style,
            "HTML": xml_style,
            "XML": xml_style,
        }
        return block_map.get(language, (None, None))

    def _determine_primary_language(self, languages: Dict[str, Dict[str, int]]) -> str:
        """Determine the primary programming language (excluding config formats)."""
        config_formats = {
            "YAML", "JSON", "XML", "TOML", "Properties", "HTML", "CSS",
            "SCSS", "LESS", "SQL", "Shell",
        }

        code_languages = {
            lang: data for lang, data in languages.items()
            if lang not in config_formats
        }

        if not code_languages:
            # Fall back to all languages
            code_languages = languages

        if not code_languages:
            return "Unknown"

        return max(code_languages.items(), key=lambda x: x[1]["loc"])[0]

    def _empty_result(self) -> dict:
        """Return an empty detection result."""
        return {
            "languages": {},
            "primary_language": "Unknown",
            "tech_stack": [],
            "total_files": 0,
            "total_loc": 0,
        }

    def format_as_markdown(self, result: dict) -> str:
        """
        Format detection results as a markdown section.

        Args:
            result: Output from detect()

        Returns:
            Markdown string with language table, tech stack list, and summary stats.
        """
        lines = []

        # Summary
        lines.append(f"**Primary Language:** {result['primary_language']}")
        lines.append(f"**Total Files:** {result['total_files']:,}")
        lines.append(f"**Total Lines of Code:** {result['total_loc']:,}")
        lines.append("")

        # Tech stack
        if result["tech_stack"]:
            lines.append("**Technology Stack:**")
            for tech in result["tech_stack"]:
                lines.append(f"- {tech}")
            lines.append("")

        # Language breakdown table
        if result["languages"]:
            lines.append("**Language Breakdown:**")
            lines.append("")
            lines.append("| Language | Files | Lines of Code | Blank | Comment |")
            lines.append("|----------|------:|-------------:|------:|--------:|")
            for lang, data in result["languages"].items():
                lines.append(
                    f"| {lang} | {data['files']:,} | {data['loc']:,} "
                    f"| {data['blank']:,} | {data['comment']:,} |"
                )
            lines.append("")

        return "\n".join(lines)
