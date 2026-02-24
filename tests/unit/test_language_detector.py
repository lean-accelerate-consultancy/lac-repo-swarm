"""
Unit tests for LanguageDetector -- language detection, LOC counting, and tech stack identification.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from investigator.core.static_analyzers.language_detector import LanguageDetector


# Path to the sample_repo fixture
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SAMPLE_REPO = FIXTURES_DIR / "sample_repo"


class TestLanguageDetectorWithFixture(unittest.TestCase):
    """Tests using the sample_repo fixture directory."""

    @classmethod
    def setUpClass(cls):
        cls.detector = LanguageDetector()
        cls.result = cls.detector.detect(str(SAMPLE_REPO))

    def test_returns_dict_with_expected_keys(self):
        """detect() returns a dict with all expected top-level keys."""
        for key in ("languages", "primary_language", "tech_stack", "total_files", "total_loc"):
            self.assertIn(key, self.result, f"Missing key: {key}")

    def test_detects_java(self):
        """Java files are detected from .java extension."""
        self.assertIn("Java", self.result["languages"])
        java = self.result["languages"]["Java"]
        self.assertEqual(java["files"], 2)  # Application.java + UserController.java
        self.assertGreater(java["loc"], 0)

    def test_detects_go(self):
        """Go files are detected from .go extension."""
        self.assertIn("Go", self.result["languages"])
        go = self.result["languages"]["Go"]
        self.assertEqual(go["files"], 1)  # main.go
        self.assertGreater(go["loc"], 0)

    def test_detects_shell(self):
        """Shell scripts are detected from .sh extension."""
        self.assertIn("Shell", self.result["languages"])

    def test_detects_yaml(self):
        """YAML files are detected from .yml extension."""
        self.assertIn("YAML", self.result["languages"])

    def test_primary_language_excludes_config_formats(self):
        """Primary language should be a real programming language, not YAML/JSON/etc."""
        # sample_repo has Java and Go -- one of them should be primary
        self.assertIn(self.result["primary_language"], ("Java", "Go"))

    def test_tech_stack_includes_maven(self):
        """pom.xml should trigger Maven in tech stack."""
        self.assertIn("Maven", self.result["tech_stack"])

    def test_tech_stack_includes_docker(self):
        """Dockerfile should trigger Docker in tech stack."""
        self.assertIn("Docker", self.result["tech_stack"])

    def test_tech_stack_includes_go_modules(self):
        """go.mod should trigger Go Modules in tech stack."""
        self.assertIn("Go Modules", self.result["tech_stack"])

    def test_tech_stack_includes_github_actions(self):
        """Files under .github/workflows/ should trigger GitHub Actions."""
        self.assertIn("GitHub Actions", self.result["tech_stack"])

    def test_total_files_positive(self):
        """Total file count should be positive."""
        self.assertGreater(self.result["total_files"], 0)

    def test_total_loc_positive(self):
        """Total LOC should be positive."""
        self.assertGreater(self.result["total_loc"], 0)

    def test_tech_stack_sorted_alphabetically(self):
        """Tech stack list should be sorted."""
        self.assertEqual(self.result["tech_stack"], sorted(self.result["tech_stack"]))


class TestLanguageDetectorLOCCounting(unittest.TestCase):
    """Tests for line counting accuracy."""

    def setUp(self):
        self.detector = LanguageDetector()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def test_java_comment_counting(self):
        """Java single-line and block comments are counted separately from LOC."""
        self._write_file("Test.java", """\
package com.example;

// This is a single-line comment
/* This is a
   block comment */
public class Test {
    public void run() {
        System.out.println("hello");
    }
}
""")
        result = self.detector.detect(self.tmpdir)
        java = result["languages"]["Java"]
        self.assertEqual(java["files"], 1)
        # 6 code lines: package, public class, public void, println, }, }
        self.assertEqual(java["loc"], 6)
        # 1 blank line
        self.assertEqual(java["blank"], 1)
        # 3 comment lines: single-line, block start, block end
        self.assertEqual(java["comment"], 3)

    def test_python_comment_counting(self):
        """Python hash comments are detected."""
        self._write_file("app.py", """\
# Main module
import os

def main():
    # do stuff
    print("hello")
""")
        result = self.detector.detect(self.tmpdir)
        py = result["languages"]["Python"]
        self.assertEqual(py["files"], 1)
        self.assertEqual(py["loc"], 3)  # import, def, print
        self.assertEqual(py["blank"], 1)
        self.assertEqual(py["comment"], 2)  # two hash comments

    def test_empty_file_produces_zero_counts(self):
        """An empty file has no LOC, no blank, no comment."""
        self._write_file("empty.py", "")
        result = self.detector.detect(self.tmpdir)
        py = result["languages"]["Python"]
        self.assertEqual(py["loc"], 0)
        self.assertEqual(py["blank"], 0)
        self.assertEqual(py["comment"], 0)

    def test_blank_lines_only(self):
        """A file with only blank lines has blank count but no LOC."""
        self._write_file("blank.py", "\n\n\n\n")
        result = self.detector.detect(self.tmpdir)
        py = result["languages"]["Python"]
        self.assertEqual(py["loc"], 0)
        self.assertEqual(py["blank"], 4)

    def test_go_block_comments(self):
        """Go block comments /* */ are detected."""
        self._write_file("main.go", """\
package main

/* This is a
   multi-line block comment */

func main() {
}
""")
        result = self.detector.detect(self.tmpdir)
        go = result["languages"]["Go"]
        self.assertEqual(go["comment"], 2)  # two lines inside block comment
        self.assertEqual(go["loc"], 3)  # package, func, closing brace


class TestLanguageDetectorSkipDirs(unittest.TestCase):
    """Tests for directory skipping behavior."""

    def setUp(self):
        self.detector = LanguageDetector()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content="# placeholder"):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        return filepath

    def test_node_modules_skipped(self):
        """Files inside node_modules/ should not be counted."""
        self._write_file("app.js", "console.log('main');")
        self._write_file("node_modules/dep/index.js", "module.exports = {};")
        result = self.detector.detect(self.tmpdir)
        js = result["languages"]["JavaScript"]
        self.assertEqual(js["files"], 1)  # only app.js

    def test_git_dir_skipped(self):
        """Files inside .git/ should not be counted."""
        self._write_file("main.py", "print('hello')")
        self._write_file(".git/config", "[core]")
        result = self.detector.detect(self.tmpdir)
        # .git files shouldn't appear; only main.py
        self.assertIn("Python", result["languages"])
        # Properties language would come from .git/config if not skipped
        self.assertNotIn("Properties", result["languages"])

    def test_venv_skipped(self):
        """Files inside venv/ should not be counted."""
        self._write_file("app.py", "print('hello')")
        self._write_file("venv/lib/python3.12/site-packages/pkg/init.py", "x=1")
        result = self.detector.detect(self.tmpdir)
        py = result["languages"]["Python"]
        self.assertEqual(py["files"], 1)  # only app.py


class TestLanguageDetectorEmptyRepo(unittest.TestCase):
    """Tests for edge cases with empty or non-existent repos."""

    def setUp(self):
        self.detector = LanguageDetector()

    def test_nonexistent_path_returns_empty_result(self):
        """A non-existent directory returns the empty result."""
        result = self.detector.detect("/nonexistent/path/12345")
        self.assertEqual(result["languages"], {})
        self.assertEqual(result["primary_language"], "Unknown")
        self.assertEqual(result["tech_stack"], [])
        self.assertEqual(result["total_files"], 0)
        self.assertEqual(result["total_loc"], 0)

    def test_empty_directory_returns_empty_result(self):
        """An empty directory returns zero counts."""
        tmpdir = tempfile.mkdtemp()
        try:
            result = self.detector.detect(tmpdir)
            self.assertEqual(result["total_files"], 0)
            self.assertEqual(result["total_loc"], 0)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestLanguageDetectorPrimaryLanguage(unittest.TestCase):
    """Tests for primary language determination."""

    def setUp(self):
        self.detector = LanguageDetector()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_primary_is_language_with_most_loc(self):
        """Primary language is the one with the most lines of code."""
        # Write more Java than Python
        self._write_file("Big.java", "\n".join(
            [f"int x{i} = {i};" for i in range(100)]
        ))
        self._write_file("small.py", "x = 1\ny = 2")
        result = self.detector.detect(self.tmpdir)
        self.assertEqual(result["primary_language"], "Java")

    def test_yaml_not_primary_even_if_most_loc(self):
        """YAML should not be primary even if it has the most LOC."""
        self._write_file("config.yaml", "\n".join(
            [f"key{i}: value{i}" for i in range(200)]
        ))
        self._write_file("main.py", "print('hello')")
        result = self.detector.detect(self.tmpdir)
        self.assertEqual(result["primary_language"], "Python")


class TestLanguageDetectorFormatMarkdown(unittest.TestCase):
    """Tests for the markdown formatting method."""

    def setUp(self):
        self.detector = LanguageDetector()

    def test_format_contains_language_table(self):
        """Markdown output should contain a language breakdown table."""
        result = {
            "languages": {
                "Java": {"files": 10, "loc": 500, "blank": 50, "comment": 30},
                "Go": {"files": 3, "loc": 200, "blank": 20, "comment": 10},
            },
            "primary_language": "Java",
            "tech_stack": ["Maven", "Docker"],
            "total_files": 20,
            "total_loc": 700,
        }
        md = self.detector.format_as_markdown(result)
        self.assertIn("**Primary Language:** Java", md)
        self.assertIn("**Total Files:** 20", md)
        self.assertIn("**Total Lines of Code:** 700", md)
        self.assertIn("| Java |", md)
        self.assertIn("| Go |", md)
        self.assertIn("- Maven", md)
        self.assertIn("- Docker", md)

    def test_format_empty_result(self):
        """Markdown output for an empty result should not crash."""
        result = {
            "languages": {},
            "primary_language": "Unknown",
            "tech_stack": [],
            "total_files": 0,
            "total_loc": 0,
        }
        md = self.detector.format_as_markdown(result)
        self.assertIn("**Primary Language:** Unknown", md)
        self.assertIn("**Total Files:** 0", md)


if __name__ == "__main__":
    unittest.main()
