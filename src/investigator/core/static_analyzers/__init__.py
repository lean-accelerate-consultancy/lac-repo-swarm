"""
Static analysis sub-modules for no-AI mode.

These modules replace Claude API calls with automated code scanning,
dependency parsing, and infrastructure analysis.
"""

from .language_detector import LanguageDetector
from .terraform_parser import TerraformParser
from .deployment_scanner import DeploymentScanner
from .api_scanner import APIScanner
from .entity_parser import EntityParser
from .database_scanner import DatabaseScanner
from .monitoring_scanner import MonitoringScanner
from .feature_flag_scanner import FeatureFlagScanner
from .data_mapping_scanner import DataMappingScanner
from .security_scanner import SecurityScanner
from .event_detector import EventDetector
from .prompt_security_scanner import PromptSecurityScanner

__all__ = [
    "LanguageDetector",
    "TerraformParser",
    "DeploymentScanner",
    "APIScanner",
    "EntityParser",
    "DatabaseScanner",
    "MonitoringScanner",
    "FeatureFlagScanner",
    "DataMappingScanner",
    "SecurityScanner",
    "EventDetector",
    "PromptSecurityScanner",
]
