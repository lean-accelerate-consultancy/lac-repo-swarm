"""
DataMappingScanner -- detects personal data fields and PII indicators in
entity definitions, database schemas, and configuration files.

Covers section: data_mapping
"""

import re
from pathlib import Path


# PII field name patterns (case-insensitive)
PII_FIELD_PATTERNS = {
    re.compile(r'\b(email|e_mail|email_address)\b', re.IGNORECASE): "Email",
    re.compile(r'\b(phone|phone_number|mobile|telephone)\b', re.IGNORECASE): "Phone",
    re.compile(r'\b(ssn|social_security|national_id|national_insurance)\b', re.IGNORECASE): "National ID",
    re.compile(r'\b(passport|passport_number)\b', re.IGNORECASE): "Passport",
    re.compile(r'\b(date_of_birth|dob|birth_date|birthday)\b', re.IGNORECASE): "Date of Birth",
    re.compile(r'\b(address|street_address|postal_address|home_address)\b', re.IGNORECASE): "Address",
    re.compile(r'\b(zip_code|postcode|postal_code)\b', re.IGNORECASE): "Postal Code",
    re.compile(r'\b(first_name|last_name|full_name|surname|given_name)\b', re.IGNORECASE): "Name",
    re.compile(r'\b(credit_card|card_number|cc_number)\b', re.IGNORECASE): "Credit Card",
    re.compile(r'\b(bank_account|iban|routing_number|account_number)\b', re.IGNORECASE): "Financial",
    re.compile(r'\b(ip_address|ip_addr)\b', re.IGNORECASE): "IP Address",
    re.compile(r'\b(password|passwd|secret|api_key|access_token)\b', re.IGNORECASE): "Credential",
    re.compile(r'\b(gender|sex|ethnicity|race)\b', re.IGNORECASE): "Demographics",
    re.compile(r'\b(salary|income|wage)\b', re.IGNORECASE): "Financial",
    re.compile(r'\b(medical|diagnosis|health|prescription)\b', re.IGNORECASE): "Health",
    re.compile(r'\b(drivers_license|license_number)\b', re.IGNORECASE): "License",
    re.compile(r'\b(geolocation|latitude|longitude|geo_location)\b', re.IGNORECASE): "Location",
    re.compile(r'\b(user_agent|device_id|device_fingerprint)\b', re.IGNORECASE): "Device",
}

# Entity-definition file patterns to scan
ENTITY_FILE_PATTERNS = [
    "**/*.java",
    "**/*.py",
    "**/*.go",
    "**/*.ts",
    "**/*.js",
    "**/*.proto",
    "**/*.avsc",
    "**/*.graphql",
    "**/*.gql",
    "**/*.prisma",
]

# Schema/migration file patterns
SCHEMA_FILE_PATTERNS = [
    "**/migrations/**/*.sql",
    "**/migration/**/*.sql",
    "**/schema*.sql",
    "**/create_*.sql",
    "**/*.sql",
    "**/schema.prisma",
    "**/models.py",
    "**/entities.py",
    "**/entity.py",
]


class DataMappingScanner:
    """Scans a repository for PII fields and data sensitivity indicators."""

    SKIP_DIRS = {".terraform", "node_modules", ".venv", "venv", "vendor",
                 ".git", "__pycache__", "dist", "build", "target",
                 "test", "tests", "__tests__", "spec", "fixtures"}

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def scan(self) -> dict:
        """Scan the repo for PII fields and data mapping info."""
        result = {
            "pii_fields": [],
            "sensitive_files": [],
        }

        if not self.repo_path.exists():
            return result

        self._scan_entity_files(result)
        self._scan_schema_files(result)

        # Deduplicate by (pii_type, field, file)
        seen = set()
        deduped = []
        for item in result["pii_fields"]:
            key = (item["pii_type"], item["field"], item["file"])
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        result["pii_fields"] = deduped

        return result

    def _should_skip(self, path: Path) -> bool:
        return any(d in path.parts for d in self.SKIP_DIRS)

    def _scan_entity_files(self, result: dict):
        """Scan entity/model files for PII field names."""
        for pattern in ENTITY_FILE_PATTERNS:
            for f in self.repo_path.rglob(pattern):
                if self._should_skip(f):
                    continue
                if f.stat().st_size > 200_000:  # Skip very large files
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except (OSError, IOError):
                    continue

                rel_path = str(f.relative_to(self.repo_path))
                found_types = set()

                for pii_pattern, pii_type in PII_FIELD_PATTERNS.items():
                    matches = pii_pattern.findall(content)
                    for field_name in matches:
                        if pii_type not in found_types:
                            found_types.add(pii_type)
                            result["pii_fields"].append({
                                "pii_type": pii_type,
                                "field": field_name if isinstance(field_name, str) else field_name[0],
                                "file": rel_path,
                            })

                if found_types:
                    result["sensitive_files"].append({
                        "file": rel_path,
                        "pii_types": sorted(found_types),
                        "count": len(found_types),
                    })

    def _scan_schema_files(self, result: dict):
        """Scan SQL/schema files for PII column names."""
        for pattern in SCHEMA_FILE_PATTERNS:
            for f in self.repo_path.rglob(pattern):
                if self._should_skip(f):
                    continue
                if f.stat().st_size > 200_000:
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except (OSError, IOError):
                    continue

                rel_path = str(f.relative_to(self.repo_path))
                found_types = set()

                for pii_pattern, pii_type in PII_FIELD_PATTERNS.items():
                    matches = pii_pattern.findall(content)
                    for field_name in matches:
                        if pii_type not in found_types:
                            found_types.add(pii_type)
                            result["pii_fields"].append({
                                "pii_type": pii_type,
                                "field": field_name if isinstance(field_name, str) else field_name[0],
                                "file": rel_path,
                            })

                if found_types and not any(
                    sf["file"] == rel_path for sf in result["sensitive_files"]
                ):
                    result["sensitive_files"].append({
                        "file": rel_path,
                        "pii_types": sorted(found_types),
                        "count": len(found_types),
                    })

    def format_as_markdown(self, data: dict) -> str:
        """Format data mapping results as markdown."""
        pii_fields = data.get("pii_fields", [])
        sensitive_files = data.get("sensitive_files", [])

        if not pii_fields and not sensitive_files:
            return ("*No PII fields or sensitive data patterns detected.*\n\n"
                    "---\n*Generated by static analysis (ENABLE_AI=false)*")

        lines = []

        if sensitive_files:
            lines.append("**Files with Sensitive Data Fields:**\n")
            lines.append("| File | PII Types Found | Count |")
            lines.append("|------|----------------|------:|")
            for sf in sorted(sensitive_files, key=lambda x: -x["count"]):
                types_str = ", ".join(sf["pii_types"])
                lines.append(f"| `{sf['file']}` | {types_str} | {sf['count']} |")
            lines.append("")

        if pii_fields:
            # Group by PII type
            by_type: dict[str, list] = {}
            for pf in pii_fields:
                by_type.setdefault(pf["pii_type"], []).append(pf)

            lines.append("**PII Field Detections:**\n")
            lines.append("| PII Type | Field Name | File |")
            lines.append("|----------|-----------|------|")
            for pii_type in sorted(by_type.keys()):
                for pf in sorted(by_type[pii_type], key=lambda x: x["file"])[:10]:
                    lines.append(f"| {pf['pii_type']} | `{pf['field']}` | {pf['file']} |")
                if len(by_type[pii_type]) > 10:
                    lines.append(f"| {pii_type} | ... | *{len(by_type[pii_type]) - 10} more* |")

            lines.append(f"\n**Total PII Fields Detected:** {len(pii_fields)}")

        lines.append("\n---")
        lines.append("*Generated by static analysis (ENABLE_AI=false)*")
        return "\n".join(lines)
