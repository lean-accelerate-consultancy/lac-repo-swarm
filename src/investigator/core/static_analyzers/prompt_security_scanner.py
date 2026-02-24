"""
PromptSecurityScanner -- detects LLM/AI API usage, prompt patterns,
and potential prompt injection surfaces in code.

Covers section: prompt_security_check
"""

import re
from pathlib import Path


# LLM SDK imports / usage patterns per language
LLM_SDK_PATTERNS = {
    "OpenAI": {
        "glob": ["**/*.py", "**/*.js", "**/*.ts", "**/*.java", "**/*.go"],
        "patterns": [
            "import openai",
            "from openai",
            "openai.ChatCompletion",
            "openai.Completion",
            "OpenAI(",
            "require('openai')",
            'require("openai")',
            "from 'openai'",
            'from "openai"',
            "com.theokanning.openai",
            "sashabaranov/go-openai",
        ],
    },
    "Anthropic (Claude)": {
        "glob": ["**/*.py", "**/*.js", "**/*.ts"],
        "patterns": [
            "import anthropic",
            "from anthropic",
            "Anthropic(",
            "@anthropic-ai/sdk",
            "anthropic.Anthropic",
            "anthropic.messages",
        ],
    },
    "AWS Bedrock": {
        "glob": ["**/*.py", "**/*.java", "**/*.go", "**/*.js", "**/*.ts"],
        "patterns": [
            "bedrock-runtime",
            "BedrockRuntimeClient",
            "invoke_model",
            "InvokeModel",
            "boto3.client('bedrock",
        ],
    },
    "LangChain": {
        "glob": ["**/*.py", "**/*.js", "**/*.ts"],
        "patterns": [
            "from langchain",
            "import langchain",
            "langchain.llms",
            "langchain.chat_models",
            "langchain.chains",
            "@langchain/",
            "langchain/llms",
        ],
    },
    "LlamaIndex": {
        "glob": ["**/*.py"],
        "patterns": [
            "from llama_index",
            "import llama_index",
            "from llama_index.core",
        ],
    },
    "Hugging Face": {
        "glob": ["**/*.py"],
        "patterns": [
            "from transformers import",
            "import transformers",
            "AutoModelForCausalLM",
            "pipeline(",
            "huggingface_hub",
        ],
    },
    "Google AI (Gemini/PaLM)": {
        "glob": ["**/*.py", "**/*.js", "**/*.ts"],
        "patterns": [
            "google.generativeai",
            "import google.generativeai",
            "@google/generative-ai",
            "GenerativeModel(",
        ],
    },
    "Azure OpenAI": {
        "glob": ["**/*.py", "**/*.js", "**/*.ts", "**/*.java", "**/*.cs"],
        "patterns": [
            "AzureOpenAI(",
            "azure.ai.openai",
            "azure-openai",
            "openai.api_type.*azure",
        ],
    },
    "Cohere": {
        "glob": ["**/*.py", "**/*.js", "**/*.ts"],
        "patterns": [
            "import cohere",
            "cohere.Client",
            "require('cohere-ai')",
        ],
    },
}

# Prompt injection surface patterns
PROMPT_INJECTION_PATTERNS = [
    (re.compile(r'f["\'].*\{.*user.*\}.*["\']', re.IGNORECASE),
     "User input in f-string prompt"),
    (re.compile(r'\.format\s*\(.*user', re.IGNORECASE),
     "User input in .format() prompt"),
    (re.compile(r'prompt\s*[+=]\s*.*(?:input|request|query|user)', re.IGNORECASE),
     "Dynamic prompt construction with user input"),
    (re.compile(r'(?:system_prompt|system_message)\s*[=:]', re.IGNORECASE),
     "System prompt definition"),
    (re.compile(r'(?:role|messages)\s*[=:]\s*\[', re.IGNORECASE),
     "Chat message array construction"),
]

# Prompt template file patterns
PROMPT_FILE_PATTERNS = [
    "**/*prompt*",
    "**/*template*",
    "**/prompts/**",
]

# Prompt template patterns in code
PROMPT_TEMPLATE_PATTERNS = [
    (re.compile(r'(?:system|user|assistant)\s*(?:prompt|message|template)\s*[=:]',
                re.IGNORECASE),
     "Prompt template variable"),
    (re.compile(r'PromptTemplate\s*\(', re.IGNORECASE),
     "PromptTemplate class usage"),
    (re.compile(r'ChatPromptTemplate', re.IGNORECASE),
     "ChatPromptTemplate usage"),
    (re.compile(r'SystemMessage\s*\(', re.IGNORECASE),
     "SystemMessage construction"),
    (re.compile(r'HumanMessage\s*\(', re.IGNORECASE),
     "HumanMessage construction"),
]


class PromptSecurityScanner:
    """Scans a repository for LLM API usage and prompt security patterns."""

    SKIP_DIRS = {".terraform", "node_modules", ".venv", "venv", "vendor",
                 ".git", "__pycache__", "dist", "build", "target",
                 "test", "tests", "__tests__", "spec"}

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def scan(self) -> dict:
        """Scan the repo for LLM usage and prompt security patterns."""
        result = {
            "llm_sdks": [],
            "injection_surfaces": [],
            "prompt_templates": [],
            "prompt_files": [],
        }

        if not self.repo_path.exists():
            return result

        self._scan_llm_sdks(result)
        self._scan_injection_surfaces(result)
        self._scan_prompt_templates(result)
        self._scan_prompt_files(result)

        return result

    def _should_skip(self, path: Path) -> bool:
        return any(d in path.parts for d in self.SKIP_DIRS)

    def _scan_llm_sdks(self, result: dict):
        """Scan for LLM SDK imports and usage."""
        found = set()

        for sdk_name, config in LLM_SDK_PATTERNS.items():
            if sdk_name in found:
                continue

            for glob_pattern in config["glob"]:
                if sdk_name in found:
                    break

                for f in self.repo_path.rglob(glob_pattern):
                    if self._should_skip(f):
                        continue
                    if f.stat().st_size > 500_000:
                        continue

                    try:
                        content = f.read_text(encoding="utf-8", errors="replace")
                    except (OSError, IOError):
                        continue

                    for pattern_str in config["patterns"]:
                        if pattern_str in content:
                            found.add(sdk_name)
                            rel_path = str(f.relative_to(self.repo_path))
                            result["llm_sdks"].append({
                                "sdk": sdk_name,
                                "file": rel_path,
                            })
                            break

                    if sdk_name in found:
                        break

    def _scan_injection_surfaces(self, result: dict):
        """Scan for potential prompt injection surfaces."""
        found_files = set()

        for ext_pattern in ["**/*.py", "**/*.js", "**/*.ts", "**/*.java", "**/*.go"]:
            for f in self.repo_path.rglob(ext_pattern):
                if self._should_skip(f):
                    continue
                if f.stat().st_size > 500_000:
                    continue

                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except (OSError, IOError):
                    continue

                rel_path = str(f.relative_to(self.repo_path))
                if rel_path in found_files:
                    continue

                for pattern, desc in PROMPT_INJECTION_PATTERNS:
                    if pattern.search(content):
                        found_files.add(rel_path)
                        result["injection_surfaces"].append({
                            "type": desc,
                            "file": rel_path,
                        })
                        break  # One per file

    def _scan_prompt_templates(self, result: dict):
        """Scan for prompt template usage in code."""
        found_files = set()

        for ext_pattern in ["**/*.py", "**/*.js", "**/*.ts"]:
            for f in self.repo_path.rglob(ext_pattern):
                if self._should_skip(f):
                    continue

                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except (OSError, IOError):
                    continue

                rel_path = str(f.relative_to(self.repo_path))
                if rel_path in found_files:
                    continue

                for pattern, desc in PROMPT_TEMPLATE_PATTERNS:
                    if pattern.search(content):
                        found_files.add(rel_path)
                        result["prompt_templates"].append({
                            "type": desc,
                            "file": rel_path,
                        })
                        break

    def _scan_prompt_files(self, result: dict):
        """Scan for prompt/template files."""
        found_files = set()
        binary_exts = {".png", ".jpg", ".gif", ".ico", ".svg",
                      ".woff", ".ttf", ".eot", ".pyc", ".class"}

        # Files with "prompt" or "template" in the name
        for pattern in PROMPT_FILE_PATTERNS:
            for f in self.repo_path.rglob(pattern):
                if not f.is_file():
                    continue
                if self._should_skip(f):
                    continue
                if f.suffix in binary_exts:
                    continue

                rel_path = str(f.relative_to(self.repo_path))
                if rel_path not in found_files:
                    found_files.add(rel_path)
                    result["prompt_files"].append({"file": rel_path})

        # Files inside directories named "prompts" or "prompt_templates"
        for d in self.repo_path.rglob("prompts"):
            if not d.is_dir():
                continue
            if self._should_skip(d):
                continue
            for f in d.rglob("*"):
                if not f.is_file():
                    continue
                if f.suffix in binary_exts:
                    continue
                rel_path = str(f.relative_to(self.repo_path))
                if rel_path not in found_files:
                    found_files.add(rel_path)
                    result["prompt_files"].append({"file": rel_path})

    def format_as_markdown(self, data: dict) -> str:
        """Format prompt security scan results as markdown."""
        sdks = data.get("llm_sdks", [])
        injections = data.get("injection_surfaces", [])
        templates = data.get("prompt_templates", [])
        prompt_files = data.get("prompt_files", [])

        if not sdks and not injections and not templates and not prompt_files:
            return ("*No LLM/AI API usage or prompt patterns detected.*\n\n"
                    "---\n*Generated by static analysis (ENABLE_AI=false)*")

        lines = []

        if sdks:
            lines.append("**LLM/AI SDKs Detected:**\n")
            lines.append("| SDK/Provider | Detected In |")
            lines.append("|-------------|------------|")
            for s in sorted(sdks, key=lambda x: x["sdk"]):
                lines.append(f"| {s['sdk']} | `{s['file']}` |")
            lines.append("")

        if injections:
            lines.append("**Potential Prompt Injection Surfaces:**\n")
            lines.append("| Risk Pattern | File |")
            lines.append("|-------------|------|")
            for i in sorted(injections, key=lambda x: x["file"]):
                lines.append(f"| {i['type']} | `{i['file']}` |")
            lines.append("")
            lines.append("*Warning: Review these files to ensure user input is properly "
                        "sanitized before inclusion in LLM prompts.*")
            lines.append("")

        if templates:
            lines.append("**Prompt Template Usage:**\n")
            lines.append("| Pattern | File |")
            lines.append("|---------|------|")
            for t in sorted(templates, key=lambda x: x["file"]):
                lines.append(f"| {t['type']} | `{t['file']}` |")
            lines.append("")

        if prompt_files:
            lines.append("**Prompt/Template Files:**\n")
            for pf in sorted(prompt_files, key=lambda x: x["file"]):
                lines.append(f"- `{pf['file']}`")

        lines.append("\n---")
        lines.append("*Generated by static analysis (ENABLE_AI=false)*")
        return "\n".join(lines)
