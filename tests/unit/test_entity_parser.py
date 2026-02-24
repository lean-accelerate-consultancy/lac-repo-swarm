"""
Unit tests for EntityParser -- core entity extraction from Java, Go, Python, and Terraform.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from investigator.core.static_analyzers.entity_parser import EntityParser


class TestEntityParserJava(unittest.TestCase):
    """Tests for Java entity extraction."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_class_detected(self):
        """Public class with package is detected."""
        self._write_file("src/User.java", """\
package com.example.model;

public class User {
    private String name;
}
""")
        parser = EntityParser(self.tmpdir)
        data = parser.parse()
        java = data["java_entities"]
        self.assertEqual(len(java), 1)
        self.assertEqual(java[0]["name"], "User")
        self.assertEqual(java[0]["type"], "class")
        self.assertEqual(java[0]["package"], "com.example.model")

    def test_extends_and_implements(self):
        """Extends and implements are captured."""
        self._write_file("src/Admin.java", """\
package com.example;

public class Admin extends User implements Serializable, Auditable {
}
""")
        parser = EntityParser(self.tmpdir)
        data = parser.parse()
        admin = data["java_entities"][0]
        self.assertEqual(admin["extends"], "User")
        self.assertIn("Serializable", admin["implements"])
        self.assertIn("Auditable", admin["implements"])

    def test_interface_detected(self):
        """Interface declarations are detected."""
        self._write_file("src/Repository.java", """\
package com.example;

public interface Repository {
    void save();
}
""")
        parser = EntityParser(self.tmpdir)
        data = parser.parse()
        self.assertEqual(data["java_entities"][0]["type"], "interface")

    def test_enum_detected(self):
        """Enum declarations are detected."""
        self._write_file("src/Status.java", """\
package com.example;

public enum Status {
    ACTIVE, INACTIVE
}
""")
        parser = EntityParser(self.tmpdir)
        data = parser.parse()
        self.assertEqual(data["java_entities"][0]["type"], "enum")
        self.assertEqual(data["java_entities"][0]["name"], "Status")

    def test_record_detected(self):
        """Java record declarations are detected."""
        self._write_file("src/Point.java", """\
package com.example;

public record Point(int x, int y) {
}
""")
        parser = EntityParser(self.tmpdir)
        data = parser.parse()
        self.assertEqual(data["java_entities"][0]["type"], "record")
        self.assertEqual(data["java_entities"][0]["name"], "Point")


class TestEntityParserGo(unittest.TestCase):
    """Tests for Go entity extraction."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_struct_detected(self):
        """Go struct declarations are detected."""
        self._write_file("models.go", """\
package models

type User struct {
    Name  string
    Email string
}

type Config struct {
    Port int
}
""")
        parser = EntityParser(self.tmpdir)
        data = parser.parse()
        go = data["go_entities"]
        self.assertEqual(len(go), 2)
        names = {e["name"] for e in go}
        self.assertEqual(names, {"User", "Config"})
        self.assertTrue(all(e["type"] == "struct" for e in go))
        self.assertTrue(all(e["package"] == "models" for e in go))

    def test_interface_detected(self):
        """Go interface declarations are detected."""
        self._write_file("repo.go", """\
package repo

type Repository interface {
    Save(entity interface{}) error
    FindByID(id string) (interface{}, error)
}
""")
        parser = EntityParser(self.tmpdir)
        data = parser.parse()
        go = data["go_entities"]
        self.assertEqual(len(go), 1)
        self.assertEqual(go[0]["type"], "interface")
        self.assertEqual(go[0]["name"], "Repository")


class TestEntityParserPython(unittest.TestCase):
    """Tests for Python entity extraction."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_class_detected(self):
        """Python class declarations are detected."""
        self._write_file("models.py", """\
class User:
    def __init__(self, name):
        self.name = name
""")
        parser = EntityParser(self.tmpdir)
        data = parser.parse()
        py = data["python_entities"]
        self.assertEqual(len(py), 1)
        self.assertEqual(py[0]["name"], "User")
        self.assertEqual(py[0]["bases"], [])

    def test_class_with_bases(self):
        """Python class with base classes are detected."""
        self._write_file("models.py", """\
class User(BaseModel, Serializable):
    name: str
""")
        parser = EntityParser(self.tmpdir)
        data = parser.parse()
        py = data["python_entities"]
        self.assertEqual(py[0]["bases"], ["BaseModel", "Serializable"])

    def test_multiple_classes(self):
        """Multiple Python classes in one file are detected."""
        self._write_file("entities.py", """\
class Foo:
    pass

class Bar(Foo):
    pass

class Baz:
    pass
""")
        parser = EntityParser(self.tmpdir)
        data = parser.parse()
        py = data["python_entities"]
        self.assertEqual(len(py), 3)
        names = {e["name"] for e in py}
        self.assertEqual(names, {"Foo", "Bar", "Baz"})


class TestEntityParserTerraform(unittest.TestCase):
    """Tests for Terraform resource group extraction."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_resources_grouped_by_service(self):
        """Terraform resources are grouped by service prefix."""
        self._write_file("vpc.tf", '''\
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "public" {
  vpc_id = aws_vpc.main.id
}
''')
        parser = EntityParser(self.tmpdir)
        data = parser.parse()
        tf = data["terraform_entities"]
        self.assertTrue(len(tf) >= 1)
        # Both aws_vpc and aws_subnet have prefix "vpc" and "subnet"
        names = {e["name"] for e in tf}
        self.assertTrue(len(names) >= 1)

    def test_skip_dot_terraform(self):
        """Resources in .terraform/ are skipped."""
        self._write_file("main.tf", 'resource "aws_vpc" "main" { cidr_block = "10.0.0.0/16" }')
        self._write_file(".terraform/modules/mod/main.tf", 'resource "null_resource" "x" {}')
        parser = EntityParser(self.tmpdir)
        data = parser.parse()
        # Should only find the main.tf resource
        all_resources = []
        for group in data["terraform_entities"]:
            all_resources.extend(group["resources"])
        types = {r["type"] for r in all_resources}
        self.assertIn("aws_vpc", types)
        self.assertNotIn("null_resource", types)


class TestEntityParserEdgeCases(unittest.TestCase):
    """Tests for edge cases."""

    def test_nonexistent_path(self):
        parser = EntityParser("/nonexistent/path/12345")
        data = parser.parse()
        self.assertEqual(data["java_entities"], [])
        self.assertEqual(data["go_entities"], [])
        self.assertEqual(data["python_entities"], [])
        self.assertEqual(data["terraform_entities"], [])

    def test_empty_repo(self):
        tmpdir = tempfile.mkdtemp()
        try:
            parser = EntityParser(tmpdir)
            data = parser.parse()
            for key in data:
                self.assertEqual(data[key], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_skip_test_dirs(self):
        """Entity parser skips test/ and tests/ directories."""
        tmpdir = tempfile.mkdtemp()
        try:
            filepath = Path(tmpdir) / "tests" / "TestHelper.java"
            filepath.parent.mkdir(parents=True)
            filepath.write_text("package test;\npublic class TestHelper {}\n")
            filepath2 = Path(tmpdir) / "src" / "Model.java"
            filepath2.parent.mkdir(parents=True)
            filepath2.write_text("package src;\npublic class Model {}\n")
            parser = EntityParser(tmpdir)
            data = parser.parse()
            names = {e["name"] for e in data["java_entities"]}
            self.assertIn("Model", names)
            self.assertNotIn("TestHelper", names)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestEntityParserMarkdown(unittest.TestCase):
    """Tests for format_as_markdown() output."""

    def setUp(self):
        self.parser = EntityParser("/tmp/dummy")

    def test_empty_data(self):
        data = {"java_entities": [], "go_entities": [], "python_entities": [], "terraform_entities": []}
        md = self.parser.format_as_markdown(data)
        self.assertIn("No entity definitions detected", md)
        self.assertIn("ENABLE_AI=false", md)

    def test_java_table(self):
        data = {
            "java_entities": [
                {"name": "User", "type": "class", "package": "com.example", "extends": "BaseEntity",
                 "implements": ["Serializable"], "file": "User.java"},
            ],
            "go_entities": [],
            "python_entities": [],
            "terraform_entities": [],
        }
        md = self.parser.format_as_markdown(data)
        self.assertIn("Java Entities", md)
        self.assertIn("User", md)
        self.assertIn("class", md)
        self.assertIn("com.example", md)

    def test_go_table(self):
        data = {
            "java_entities": [],
            "go_entities": [
                {"name": "Config", "type": "struct", "package": "main", "file": "config.go"},
            ],
            "python_entities": [],
            "terraform_entities": [],
        }
        md = self.parser.format_as_markdown(data)
        self.assertIn("Go Entities", md)
        self.assertIn("Config", md)

    def test_python_table(self):
        data = {
            "java_entities": [],
            "go_entities": [],
            "python_entities": [
                {"name": "MyModel", "type": "class", "bases": ["BaseModel"], "file": "models.py"},
            ],
            "terraform_entities": [],
        }
        md = self.parser.format_as_markdown(data)
        self.assertIn("Python Entities", md)
        self.assertIn("MyModel", md)
        self.assertIn("BaseModel", md)


if __name__ == "__main__":
    unittest.main()
