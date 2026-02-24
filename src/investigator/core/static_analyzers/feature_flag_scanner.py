"""
FeatureFlagScanner -- detects feature flag frameworks, configuration, and usage patterns.

Covers section: feature_flags
"""

import re
from pathlib import Path


# Feature flag SDK imports per language
FF_IMPORTS = {
    "java": {
        "glob": "**/*.java",
        "patterns": {
            "io.getunleash": "Unleash",
            "com.launchdarkly": "LaunchDarkly",
            "dev.openfeature": "OpenFeature",
            "org.togglz": "Togglz",
            "io.split": "Split",
            "com.flagsmith": "Flagsmith",
        },
    },
    "python": {
        "glob": "**/*.py",
        "patterns": {
            "import ldclient": "LaunchDarkly",
            "from ldclient": "LaunchDarkly",
            "import unleash_client": "Unleash",
            "from unleash_client": "Unleash",
            "import openfeature": "OpenFeature",
            "from openfeature": "OpenFeature",
            "import flagsmith": "Flagsmith",
            "from flagsmith": "Flagsmith",
            "import flipper": "Flipper",
            "import split": "Split",
        },
    },
    "go": {
        "glob": "**/*.go",
        "patterns": {
            '"github.com/launchdarkly/go-server-sdk': "LaunchDarkly",
            '"github.com/Unleash/unleash-client-go': "Unleash",
            '"github.com/open-feature/go-sdk': "OpenFeature",
            '"github.com/thomaspoignant/go-feature-flag': "go-feature-flag",
        },
    },
    "javascript": {
        "glob": "**/*.{js,ts}",
        "patterns": {
            "launchdarkly": "LaunchDarkly",
            "@unleash/proxy-client": "Unleash",
            "unleash-client": "Unleash",
            "@openfeature/": "OpenFeature",
            "@flagsmith/": "Flagsmith",
            "@splitio/": "Split",
        },
    },
}

# Known feature flag config files
FF_CONFIG_FILES = {
    "unleash.yml": "Unleash",
    "unleash.yaml": "Unleash",
    ".launchdarkly.yaml": "LaunchDarkly",
    "flagsmith.yml": "Flagsmith",
    "feature-flags.yml": "Custom",
    "feature-flags.yaml": "Custom",
    "feature_flags.yml": "Custom",
    "feature_flags.yaml": "Custom",
    "features.yml": "Custom",
    "features.yaml": "Custom",
    "flags.json": "Custom",
    "flags.yml": "Custom",
    "flags.yaml": "Custom",
    ".featureflags.json": "Custom",
}

# Code patterns for feature flag usage
FF_CODE_PATTERNS = [
    (re.compile(r'feature[_-]?flag', re.IGNORECASE), "Feature flag reference"),
    (re.compile(r'is[_-]?enabled\s*\(\s*["\']([^"\']+)["\']'), "Feature check"),
    (re.compile(r'is[_-]?feature[_-]?enabled', re.IGNORECASE), "Feature check"),
    (re.compile(r'toggle\s*\(\s*["\']([^"\']+)["\']'), "Toggle call"),
    (re.compile(r'FEATURE_\w+\s*='), "Feature constant"),
]


class FeatureFlagScanner:
    """Scans a repository for feature flag frameworks and usage."""

    SKIP_DIRS = {".terraform", "node_modules", ".venv", "venv", "vendor",
                 ".git", "__pycache__", "dist", "build", "target"}

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def scan(self) -> dict:
        """Scan the repo for feature flag usage."""
        result = {
            "frameworks": [],
            "config_files": [],
            "usage_patterns": [],
        }

        if not self.repo_path.exists():
            return result

        self._scan_imports(result)
        self._scan_config_files(result)
        self._scan_usage_patterns(result)

        return result

    def _should_skip(self, path: Path) -> bool:
        return any(d in path.parts for d in self.SKIP_DIRS)

    def _scan_imports(self, result: dict):
        """Scan source files for feature flag SDK imports."""
        found = set()

        for lang, config in FF_IMPORTS.items():
            glob_pattern = config["glob"]

            if "{" in glob_pattern:
                base, ext_part = glob_pattern.rsplit(".", 1)
                exts = ext_part.strip("{}").split(",")
                files = []
                for ext in exts:
                    files.extend(self.repo_path.rglob(f"{base}.{ext}"))
            else:
                files = list(self.repo_path.rglob(glob_pattern))

            files = [f for f in files if not self._should_skip(f)]

            for filepath in files:
                try:
                    content = filepath.read_text(encoding="utf-8", errors="replace")
                except (OSError, IOError):
                    continue

                rel_path = str(filepath.relative_to(self.repo_path))

                for import_str, framework in config["patterns"].items():
                    if import_str in content:
                        key = (framework, lang)
                        if key not in found:
                            found.add(key)
                            result["frameworks"].append({
                                "framework": framework,
                                "language": lang,
                                "file": rel_path,
                            })

    def _scan_config_files(self, result: dict):
        """Scan for known feature flag configuration files."""
        for filename, tool in FF_CONFIG_FILES.items():
            for match in self.repo_path.rglob(filename):
                if self._should_skip(match):
                    continue
                rel_path = str(match.relative_to(self.repo_path))
                result["config_files"].append({
                    "tool": tool,
                    "file": rel_path,
                })

    def _scan_usage_patterns(self, result: dict):
        """Scan code for feature flag usage patterns."""
        found_files = set()

        for ext_pattern in ["**/*.java", "**/*.go", "**/*.py", "**/*.js", "**/*.ts"]:
            for f in self.repo_path.rglob(ext_pattern):
                if self._should_skip(f):
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except (OSError, IOError):
                    continue

                rel_path = str(f.relative_to(self.repo_path))

                for pattern, desc in FF_CODE_PATTERNS:
                    if pattern.search(content) and rel_path not in found_files:
                        found_files.add(rel_path)
                        result["usage_patterns"].append({
                            "type": desc,
                            "file": rel_path,
                        })
                        break  # One match per file

    def format_as_markdown(self, data: dict) -> str:
        """Format feature flag data as markdown."""
        frameworks = data.get("frameworks", [])
        configs = data.get("config_files", [])
        usage = data.get("usage_patterns", [])

        if not frameworks and not configs and not usage:
            return ("*No feature flag frameworks, configuration files, or usage patterns detected.*\n\n"
                    "---\n*Generated by static analysis (ENABLE_AI=false)*")

        lines = []

        if frameworks:
            lines.append("**Feature Flag Frameworks:**\n")
            lines.append("| Framework | Language | File |")
            lines.append("|-----------|----------|------|")
            for f in sorted(frameworks, key=lambda x: x["framework"]):
                lines.append(f"| {f['framework']} | {f['language']} | `{f['file']}` |")
            lines.append("")

        if configs:
            lines.append("**Configuration Files:**\n")
            lines.append("| Tool | File |")
            lines.append("|------|------|")
            for c in sorted(configs, key=lambda x: x["tool"]):
                lines.append(f"| {c['tool']} | `{c['file']}` |")
            lines.append("")

        if usage:
            lines.append("**Feature Flag Usage Patterns:**\n")
            lines.append("| Pattern | File |")
            lines.append("|---------|------|")
            for u in sorted(usage, key=lambda x: x["file"]):
                lines.append(f"| {u['type']} | `{u['file']}` |")

        lines.append("\n---")
        lines.append("*Generated by static analysis (ENABLE_AI=false)*")
        return "\n".join(lines)
