"""
Unit tests for APIScanner -- OpenAPI specs, route annotations, and API Gateway detection.
"""

import os
import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from investigator.core.static_analyzers.api_scanner import APIScanner


class TestAPIScannerOASSpecs(unittest.TestCase):
    """Tests for OpenAPI/Swagger spec detection and parsing."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_detect_openapi_yaml(self):
        """YAML OpenAPI spec is detected and parsed."""
        self._write_file("api/openapi.yaml", """\
openapi: "3.0.0"
info:
  title: "Pet Store"
  version: "1.0.0"
paths:
  /pets:
    get:
      summary: "List all pets"
    post:
      summary: "Create a pet"
  /pets/{petId}:
    get:
      summary: "Get a pet by ID"
""")
        scanner = APIScanner(self.tmpdir)
        data = scanner.scan()
        self.assertEqual(len(data["oas_specs"]), 1)
        spec = data["oas_specs"][0]
        self.assertEqual(spec["title"], "Pet Store")
        self.assertEqual(spec["version"], "3.0.0")
        self.assertEqual(spec["endpoint_count"], 3)

    def test_detect_swagger_json(self):
        """JSON Swagger spec is detected and parsed."""
        spec_data = {
            "swagger": "2.0",
            "info": {"title": "Legacy API", "version": "1.0"},
            "paths": {
                "/users": {
                    "get": {"summary": "List users"},
                },
            },
        }
        self._write_file("swagger.json", json.dumps(spec_data))
        scanner = APIScanner(self.tmpdir)
        data = scanner.scan()
        self.assertEqual(len(data["oas_specs"]), 1)
        spec = data["oas_specs"][0]
        self.assertEqual(spec["title"], "Legacy API")
        self.assertEqual(spec["endpoint_count"], 1)

    def test_non_oas_yaml_ignored(self):
        """A regular YAML file without openapi/swagger keys is ignored."""
        self._write_file("config.yaml", "database:\n  host: localhost\n  port: 5432")
        scanner = APIScanner(self.tmpdir)
        data = scanner.scan()
        self.assertEqual(data["oas_specs"], [])


class TestAPIScannerRouteAnnotations(unittest.TestCase):
    """Tests for route annotation scanning."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_java_spring_routes(self):
        """Java Spring @GetMapping etc. annotations are detected."""
        self._write_file("src/Controller.java", """\
package com.example;

@RestController
public class UserController {
    @GetMapping("/users")
    public List<User> list() { return null; }

    @PostMapping("/users")
    public User create() { return null; }

    @DeleteMapping("/users/{id}")
    public void delete() {}
}
""")
        scanner = APIScanner(self.tmpdir)
        data = scanner.scan()
        routes = data["route_endpoints"]
        self.assertTrue(len(routes) >= 3)
        methods = {r["method"] for r in routes}
        self.assertIn("GET", methods)
        self.assertIn("POST", methods)
        self.assertIn("DELETE", methods)
        paths = {r["path"] for r in routes}
        self.assertIn("/users", paths)
        self.assertIn("/users/{id}", paths)

    def test_go_router_routes(self):
        """Go HTTP handler registrations are detected."""
        self._write_file("main.go", """\
package main

func main() {
    r := chi.NewRouter()
    r.Get("/health", healthHandler)
    r.Post("/api/data", dataHandler)
}
""")
        scanner = APIScanner(self.tmpdir)
        data = scanner.scan()
        routes = data["route_endpoints"]
        self.assertTrue(len(routes) >= 2)
        paths = {r["path"] for r in routes}
        self.assertIn("/health", paths)
        self.assertIn("/api/data", paths)

    def test_python_flask_routes(self):
        """Python Flask/FastAPI decorators are detected."""
        self._write_file("app.py", """\
from flask import Flask
app = Flask(__name__)

@app.get("/items")
def list_items():
    return []

@app.post("/items")
def create_item():
    return {}
""")
        scanner = APIScanner(self.tmpdir)
        data = scanner.scan()
        routes = data["route_endpoints"]
        self.assertTrue(len(routes) >= 2)
        methods = {r["method"] for r in routes}
        self.assertIn("GET", methods)
        self.assertIn("POST", methods)

    def test_express_routes(self):
        """Express.js route registrations are detected."""
        self._write_file("server.js", """\
const express = require('express');
const app = express();

app.get('/api/users', (req, res) => { res.json([]); });
app.post('/api/users', (req, res) => { res.json({}); });
""")
        scanner = APIScanner(self.tmpdir)
        data = scanner.scan()
        routes = data["route_endpoints"]
        self.assertTrue(len(routes) >= 2)


class TestAPIScannerTerraformAPIGW(unittest.TestCase):
    """Tests for Terraform API Gateway resource detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_api_gateway_resources_detected(self):
        """API Gateway resources in .tf files are detected."""
        self._write_file("api.tf", '''\
resource "aws_api_gateway_rest_api" "my_api" {
  name = "my-api"
}

resource "aws_api_gateway_resource" "users" {
  rest_api_id = aws_api_gateway_rest_api.my_api.id
  path_part   = "users"
}

resource "aws_api_gateway_method" "get_users" {
  rest_api_id   = aws_api_gateway_rest_api.my_api.id
  http_method   = "GET"
  authorization = "NONE"
}
''')
        scanner = APIScanner(self.tmpdir)
        data = scanner.scan()
        self.assertEqual(len(data["api_gateway_resources"]), 3)
        types = {r["type"] for r in data["api_gateway_resources"]}
        self.assertIn("aws_api_gateway_rest_api", types)
        self.assertIn("aws_api_gateway_resource", types)
        self.assertIn("aws_api_gateway_method", types)


class TestAPIScannerEdgeCases(unittest.TestCase):
    """Tests for edge cases."""

    def test_nonexistent_path(self):
        scanner = APIScanner("/nonexistent/path/12345")
        data = scanner.scan()
        self.assertEqual(data["oas_specs"], [])
        self.assertEqual(data["route_endpoints"], [])
        self.assertEqual(data["api_gateway_resources"], [])

    def test_empty_repo(self):
        tmpdir = tempfile.mkdtemp()
        try:
            scanner = APIScanner(tmpdir)
            data = scanner.scan()
            self.assertEqual(data["oas_specs"], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_skip_dirs(self):
        tmpdir = tempfile.mkdtemp()
        try:
            filepath = Path(tmpdir) / "node_modules" / "pkg" / "openapi.yaml"
            filepath.parent.mkdir(parents=True)
            filepath.write_text('openapi: "3.0.0"\ninfo:\n  title: test\n  version: "1.0"\npaths: {}')
            scanner = APIScanner(tmpdir)
            data = scanner.scan()
            self.assertEqual(data["oas_specs"], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestAPIScannerMarkdown(unittest.TestCase):
    """Tests for format_as_markdown() output."""

    def setUp(self):
        self.scanner = APIScanner("/tmp/dummy")

    def test_empty_data(self):
        data = {"oas_specs": [], "route_endpoints": [], "api_gateway_resources": []}
        md = self.scanner.format_as_markdown(data)
        self.assertIn("No API definitions", md)
        self.assertIn("ENABLE_AI=false", md)

    def test_oas_spec_formatted(self):
        data = {
            "oas_specs": [{
                "file": "api/openapi.yaml",
                "title": "My API",
                "version": "3.0.0",
                "api_version": "1.0",
                "endpoint_count": 2,
                "endpoints": [
                    {"method": "GET", "path": "/items", "summary": "List items"},
                    {"method": "POST", "path": "/items", "summary": "Create item"},
                ],
            }],
            "route_endpoints": [],
            "api_gateway_resources": [],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("OpenAPI Spec: My API", md)
        self.assertIn("GET", md)
        self.assertIn("/items", md)

    def test_route_endpoints_formatted(self):
        data = {
            "oas_specs": [],
            "route_endpoints": [
                {"method": "GET", "path": "/health", "file": "main.go", "framework": "go_router"},
            ],
            "api_gateway_resources": [],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("Route Endpoints", md)
        self.assertIn("/health", md)


if __name__ == "__main__":
    unittest.main()
