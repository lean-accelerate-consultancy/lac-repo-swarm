"""
Unit tests for PromptSecurityScanner -- LLM SDK detection, prompt injection
surface scanning, and prompt template identification.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from investigator.core.static_analyzers.prompt_security_scanner import PromptSecurityScanner


class TestPromptSecurityScannerLLMSDKs(unittest.TestCase):
    """Tests for LLM SDK import detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_openai_python_detected(self):
        """OpenAI Python SDK import is detected."""
        self._write_file("llm.py", "import openai\nclient = openai.OpenAI()\n")
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        sdks = {s["sdk"] for s in data["llm_sdks"]}
        self.assertIn("OpenAI", sdks)

    def test_anthropic_python_detected(self):
        """Anthropic Python SDK import is detected."""
        self._write_file("claude.py", "from anthropic import Anthropic\nclient = Anthropic()\n")
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        sdks = {s["sdk"] for s in data["llm_sdks"]}
        self.assertIn("Anthropic (Claude)", sdks)

    def test_langchain_detected(self):
        """LangChain import is detected."""
        self._write_file("chain.py", "from langchain.chat_models import ChatOpenAI\n")
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        sdks = {s["sdk"] for s in data["llm_sdks"]}
        self.assertIn("LangChain", sdks)

    def test_bedrock_detected(self):
        """AWS Bedrock client is detected."""
        self._write_file("ai.py", """\
import boto3
client = boto3.client('bedrock-runtime')
""")
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        sdks = {s["sdk"] for s in data["llm_sdks"]}
        self.assertIn("AWS Bedrock", sdks)

    def test_openai_js_detected(self):
        """OpenAI JS/TS SDK import is detected."""
        self._write_file("ai.ts", 'import OpenAI from "openai";\nconst client = new OpenAI();\n')
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        sdks = {s["sdk"] for s in data["llm_sdks"]}
        self.assertIn("OpenAI", sdks)

    def test_huggingface_detected(self):
        """Hugging Face transformers import is detected."""
        self._write_file("model.py", "from transformers import AutoModelForCausalLM\n")
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        sdks = {s["sdk"] for s in data["llm_sdks"]}
        self.assertIn("Hugging Face", sdks)

    def test_llamaindex_detected(self):
        """LlamaIndex import is detected."""
        self._write_file("index.py", "from llama_index.core import VectorStoreIndex\n")
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        sdks = {s["sdk"] for s in data["llm_sdks"]}
        self.assertIn("LlamaIndex", sdks)

    def test_google_ai_detected(self):
        """Google Generative AI import is detected."""
        self._write_file("gemini.py", "import google.generativeai as genai\n")
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        sdks = {s["sdk"] for s in data["llm_sdks"]}
        self.assertIn("Google AI (Gemini/PaLM)", sdks)

    def test_cohere_detected(self):
        """Cohere SDK import is detected."""
        self._write_file("co.py", "import cohere\nco = cohere.Client('xxx')\n")
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        sdks = {s["sdk"] for s in data["llm_sdks"]}
        self.assertIn("Cohere", sdks)

    def test_multiple_sdks_detected(self):
        """Multiple LLM SDKs in the same repo are all detected."""
        self._write_file("openai_client.py", "import openai\n")
        self._write_file("claude_client.py", "from anthropic import Anthropic\n")
        self._write_file("chain.py", "from langchain.llms import OpenAI\n")
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        sdks = {s["sdk"] for s in data["llm_sdks"]}
        self.assertIn("OpenAI", sdks)
        self.assertIn("Anthropic (Claude)", sdks)
        self.assertIn("LangChain", sdks)

    def test_test_dir_skipped(self):
        """LLM SDK imports in test directories are skipped."""
        self._write_file("tests/test_llm.py", "import openai\n")
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        self.assertEqual(data["llm_sdks"], [])


class TestPromptSecurityScannerInjection(unittest.TestCase):
    """Tests for prompt injection surface detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_fstring_user_input_detected(self):
        """f-string with user input in prompt is flagged."""
        self._write_file("chat.py", """\
def ask(user_input):
    prompt = f"Answer the following question: {user_input}"
    return client.chat(prompt)
""")
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        types = {i["type"] for i in data["injection_surfaces"]}
        self.assertIn("User input in f-string prompt", types)

    def test_format_user_input_detected(self):
        """String .format() with user input is flagged."""
        self._write_file("query.py", """\
def query(user_query):
    prompt = "Translate: {}".format(user_query)
""")
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        types = {i["type"] for i in data["injection_surfaces"]}
        self.assertIn("User input in .format() prompt", types)

    def test_system_prompt_definition_detected(self):
        """System prompt variable definition is flagged."""
        self._write_file("ai.py", 'system_prompt = "You are a helpful assistant"\n')
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        types = {i["type"] for i in data["injection_surfaces"]}
        self.assertIn("System prompt definition", types)


class TestPromptSecurityScannerTemplates(unittest.TestCase):
    """Tests for prompt template usage detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_prompt_template_class_detected(self):
        """LangChain PromptTemplate usage is detected."""
        self._write_file("chain.py", """\
from langchain.prompts import PromptTemplate
template = PromptTemplate(input_variables=["query"], template="Answer: {query}")
""")
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        types = {t["type"] for t in data["prompt_templates"]}
        self.assertIn("PromptTemplate class usage", types)

    def test_system_message_detected(self):
        """LangChain SystemMessage construction is detected."""
        self._write_file("chat.py", """\
from langchain.schema import SystemMessage
msg = SystemMessage(content="You are a helpful bot")
""")
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        types = {t["type"] for t in data["prompt_templates"]}
        self.assertIn("SystemMessage construction", types)


class TestPromptSecurityScannerPromptFiles(unittest.TestCase):
    """Tests for prompt file detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content=""):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_prompt_dir_files_detected(self):
        """Files in prompts/ directory are detected."""
        self._write_file("prompts/system.txt", "You are a helpful assistant.")
        self._write_file("prompts/query.txt", "Answer the question: {query}")
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        self.assertTrue(len(data["prompt_files"]) >= 2)

    def test_prompt_named_files_detected(self):
        """Files with 'prompt' in the name are detected."""
        self._write_file("system_prompt.md", "You are an AI assistant.")
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        files = {pf["file"] for pf in data["prompt_files"]}
        self.assertIn("system_prompt.md", files)

    def test_binary_files_skipped(self):
        """Binary files (images, etc.) are not reported."""
        self._write_file("prompt_image.png", "\x89PNG\r\n")
        scanner = PromptSecurityScanner(self.tmpdir)
        data = scanner.scan()
        files = {pf["file"] for pf in data["prompt_files"]}
        self.assertNotIn("prompt_image.png", files)


class TestPromptSecurityScannerEdgeCases(unittest.TestCase):
    """Tests for edge cases."""

    def test_nonexistent_path(self):
        scanner = PromptSecurityScanner("/nonexistent/path/12345")
        data = scanner.scan()
        for key in data:
            self.assertEqual(data[key], [])

    def test_empty_repo(self):
        tmpdir = tempfile.mkdtemp()
        try:
            scanner = PromptSecurityScanner(tmpdir)
            data = scanner.scan()
            for key in data:
                self.assertEqual(data[key], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestPromptSecurityScannerMarkdown(unittest.TestCase):
    """Tests for format_as_markdown() output."""

    def setUp(self):
        self.scanner = PromptSecurityScanner("/tmp/dummy")

    def test_empty_data(self):
        data = {"llm_sdks": [], "injection_surfaces": [],
                "prompt_templates": [], "prompt_files": []}
        md = self.scanner.format_as_markdown(data)
        self.assertIn("No LLM/AI API usage", md)
        self.assertIn("ENABLE_AI=false", md)

    def test_sdks_table(self):
        data = {
            "llm_sdks": [{"sdk": "OpenAI", "file": "llm.py"}],
            "injection_surfaces": [],
            "prompt_templates": [],
            "prompt_files": [],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("LLM/AI SDKs Detected", md)
        self.assertIn("OpenAI", md)

    def test_injection_surfaces_table(self):
        data = {
            "llm_sdks": [],
            "injection_surfaces": [{"type": "User input in f-string prompt", "file": "chat.py"}],
            "prompt_templates": [],
            "prompt_files": [],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("Prompt Injection Surfaces", md)
        self.assertIn("chat.py", md)

    def test_prompt_files_listed(self):
        data = {
            "llm_sdks": [],
            "injection_surfaces": [],
            "prompt_templates": [],
            "prompt_files": [{"file": "prompts/system.txt"}],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("Prompt/Template Files", md)
        self.assertIn("prompts/system.txt", md)


if __name__ == "__main__":
    unittest.main()
