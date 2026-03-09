"""
VibeLens Security Module - Bug Bounty & Security Research Tools

Provides:
1. Built-in security tools (no external dependencies)
2. HexStrike AI bridge for advanced tools
"""

import asyncio
import json
import re
import hashlib
import random
import string
from typing import Any, Optional
from urllib.parse import urlparse, urljoin, parse_qs, urlencode
from dataclasses import dataclass, field
from enum import Enum
import logging

import httpx

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────

class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class VulnerabilityFinding:
    """Represents a security finding"""
    title: str
    severity: Severity
    endpoint: str
    method: str
    description: str
    evidence: str = ""
    remediation: str = ""
    request_data: dict = field(default_factory=dict)
    response_data: dict = field(default_factory=dict)


@dataclass
class SecurityScanResult:
    """Result of a security scan"""
    target: str
    findings: list[VulnerabilityFinding] = field(default_factory=list)
    endpoints_tested: int = 0
    scan_duration: float = 0.0

    def add_finding(self, finding: VulnerabilityFinding):
        self.findings.append(finding)

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "findings_count": len(self.findings),
            "endpoints_tested": self.endpoints_tested,
            "scan_duration": self.scan_duration,
            "findings": [
                {
                    "title": f.title,
                    "severity": f.severity.value,
                    "endpoint": f.endpoint,
                    "method": f.method,
                    "description": f.description,
                    "evidence": f.evidence,
                    "remediation": f.remediation,
                }
                for f in self.findings
            ],
        }


# ──────────────────────────────────────────────
# Built-in Security Tools
# ──────────────────────────────────────────────

class IDORTester:
    """Test for Insecure Direct Object Reference vulnerabilities"""

    @staticmethod
    def extract_ids_from_url(url: str) -> list[tuple[str, str]]:
        """Extract potential IDOR parameters from URL"""
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        idor_params = []
        id_patterns = [
            (r'_id$', 'ID parameter'),
            (r'id$', 'ID parameter'),
            (r'_ID$', 'ID parameter'),
            (r'ID$', 'ID parameter'),
            (r'userId', 'User ID'),
            (r'user_id', 'User ID'),
            (r'accountId', 'Account ID'),
            (r'account_id', 'Account ID'),
            (r'docId', 'Document ID'),
            (r'doc_id', 'Document ID'),
            (r'fileId', 'File ID'),
            (r'file_id', 'File ID'),
            (r'orderId', 'Order ID'),
            (r'order_id', 'Order ID'),
            (r'\d+', 'Numeric ID in path'),
        ]

        # Check query parameters
        for param, values in params.items():
            for pattern, desc in id_patterns:
                if re.search(pattern, param, re.IGNORECASE):
                    idor_params.append((param, values[0] if values else ""))
                    break

        # Check path for numeric IDs
        path_parts = parsed.path.split('/')
        for part in path_parts:
            if part.isdigit():
                idor_params.append(('path_id', part))

        return idor_params

    @staticmethod
    def generate_idor_variants(original_id: str) -> list[str]:
        """Generate variations of ID to test"""
        variants = []

        # Numeric variations
        if original_id.isdigit():
            num = int(original_id)
            variants.extend([
                str(num + 1),
                str(num - 1) if num > 1 else "1",
                str(num + 100),
                str(num + 1000),
                "1",
                "0",
                "999999",
            ])

        # UUID variations
        if '-' in original_id and len(original_id) > 30:
            # Try common UUID patterns
            variants.extend([
                "00000000-0000-0000-0000-000000000000",
                "11111111-1111-1111-1111-111111111111",
                original_id[:-1] + "0",  # Change last char
            ])

        # Common test values
        variants.extend([
            "admin",
            "test",
            "user",
            "me",
        ])

        return list(set(variants))

    @staticmethod
    async def test_idor(
        client: httpx.AsyncClient,
        url: str,
        method: str,
        headers: dict,
        body: str | None = None,
    ) -> list[VulnerabilityFinding]:
        """Test endpoint for IDOR vulnerabilities"""
        findings = []

        idor_params = IDORTester.extract_ids_from_url(url)

        for param_name, original_value in idor_params:
            if not original_value:
                continue

            variants = IDORTester.generate_idor_variants(original_value)

            for variant in variants[:5]:  # Limit tests
                # Modify URL or body with variant
                test_url = url.replace(original_value, variant)

                try:
                    if method.upper() == "GET":
                        response = await client.get(test_url, headers=headers)
                    else:
                        response = await client.request(
                            method, test_url, headers=headers, content=body
                        )

                    # Check for successful response with different data
                    if response.status_code == 200:
                        # Compare response lengths
                        orig_response = await client.request(
                            method, url, headers=headers, content=body
                        )

                        if len(response.content) != len(orig_response.content):
                            findings.append(VulnerabilityFinding(
                                title=f"Potential IDOR in {param_name}",
                                severity=Severity.HIGH,
                                endpoint=test_url,
                                method=method,
                                description=f"Changing {param_name} from {original_value} to {variant} returned different data",
                                evidence=f"Original response: {len(orig_response.content)} bytes, Modified: {len(response.content)} bytes",
                                remediation="Implement proper authorization checks for resource access",
                                request_data={"param": param_name, "original": original_value, "tested": variant},
                            ))

                except Exception as e:
                    logger.debug(f"IDOR test error: {e}")

        return findings


class ParameterFuzzer:
    """Fuzz parameters to find hidden endpoints and vulnerabilities"""

    FUZZ_PAYLOADS = {
        "sqli": [
            "' OR '1'='1",
            "' OR '1'='1'--",
            "1' OR '1'='1",
            "admin'--",
            "' UNION SELECT NULL--",
            "1; DROP TABLE users--",
        ],
        "xss": [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "javascript:alert('XSS')",
            "<svg onload=alert('XSS')>",
            "'\"><script>alert('XSS')</script>",
        ],
        "traversal": [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "....//....//....//etc/passwd",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc/passwd",
        ],
        "ssrf": [
            "http://localhost",
            "http://127.0.0.1",
            "http://169.254.169.254/latest/meta-data/",
            "file:///etc/passwd",
            "dict://localhost:11211/stat",
        ],
    }

    @staticmethod
    def extract_parameters(request_data: dict) -> dict[str, list[str]]:
        """Extract parameters from request"""
        params = {}

        # URL parameters
        url = request_data.get("url", "")
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        params.update({k: v for k, v in query_params.items()})

        # Body parameters
        body = request_data.get("body", "")
        if body:
            try:
                body_json = json.loads(body)
                if isinstance(body_json, dict):
                    params.update({k: [str(v)] for k, v in body_json.items()})
            except:
                # Try form data
                form_params = parse_qs(body)
                params.update(form_params)

        return params

    @staticmethod
    async def fuzz_parameter(
        client: httpx.AsyncClient,
        url: str,
        method: str,
        headers: dict,
        param_name: str,
        original_value: str,
        fuzz_type: str = "all",
    ) -> list[VulnerabilityFinding]:
        """Fuzz a single parameter with various payloads"""
        findings = []

        payloads_to_test = []
        if fuzz_type == "all":
            for payloads in ParameterFuzzer.FUZZ_PAYLOADS.values():
                payloads_to_test.extend(payloads)
        else:
            payloads_to_test = ParameterFuzzer.FUZZ_PAYLOADS.get(fuzz_type, [])

        for payload in payloads_to_test:
            # Build test request
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)

            if param_name in query_params:
                query_params[param_name] = [payload]
                test_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{urlencode(query_params, doseq=True)}"
            else:
                # Try body parameter
                test_url = url

            try:
                if method.upper() == "GET":
                    response = await client.get(test_url, headers=headers)
                else:
                    body = json.dumps({param_name: payload}) if fuzz_type != "form" else urlencode({param_name: payload})
                    response = await client.request(method, test_url, headers=headers, content=body)

                # Check for vulnerability indicators
                response_text = response.text

                # SQL Injection indicators
                if fuzz_type in ["sqli", "all"]:
                    sqli_indicators = [
                        "sql syntax", "mysql_fetch", "ORA-", "PLS-",
                        "Unclosed quotation", "quoted string not properly terminated",
                        "syntax error", "invalid query", "ODBC", "JET Database",
                    ]
                    for indicator in sqli_indicators:
                        if indicator.lower() in response_text.lower():
                            findings.append(VulnerabilityFinding(
                                title=f"Potential SQL Injection in {param_name}",
                                severity=Severity.CRITICAL,
                                endpoint=url,
                                method=method,
                                description=f"SQL error indicator found when fuzzing {param_name}",
                                evidence=f"Payload: {payload}\nIndicator: {indicator}",
                                remediation="Use parameterized queries and input validation",
                                request_data={"param": param_name, "payload": payload},
                            ))
                            break

                # XSS indicators
                if fuzz_type in ["xss", "all"]:
                    if payload in response_text and ("<script>" in response_text.lower() or "onerror=" in response_text.lower()):
                        findings.append(VulnerabilityFinding(
                            title=f"Potential XSS in {param_name}",
                            severity=Severity.HIGH,
                            endpoint=url,
                            method=method,
                            description=f"Payload reflected in response without sanitization",
                            evidence=f"Payload: {payload}",
                            remediation="Sanitize and encode all user input",
                            request_data={"param": param_name, "payload": payload},
                        ))

                # Path traversal indicators
                if fuzz_type in ["traversal", "all"]:
                    traversal_indicators = ["root:", "[extensions]", "passwd:", "boot loader"]
                    for indicator in traversal_indicators:
                        if indicator.lower() in response_text.lower():
                            findings.append(VulnerabilityFinding(
                                title=f"Potential Path Traversal in {param_name}",
                                severity=Severity.HIGH,
                                endpoint=url,
                                method=method,
                                description=f"File system content exposed when fuzzing {param_name}",
                                evidence=f"Payload: {payload}\nIndicator: {indicator}",
                                remediation="Validate and sanitize file path inputs",
                                request_data={"param": param_name, "payload": payload},
                            ))
                            break

            except Exception as e:
                logger.debug(f"Fuzz test error: {e}")

        return findings


class AuthBypassTester:
    """Test for authentication bypass vulnerabilities"""

    BYPASS_TECHNIQUES = [
        # Header-based bypasses
        {"headers": {"X-Original-URL": "/admin"}},
        {"headers": {"X-Rewrite-URL": "/admin"}},
        {"headers": {"X-Custom-IP-Authorization": "127.0.0.1"}},
        {"headers": {"X-Forwarded-For": "127.0.0.1"}},
        {"headers": {"X-Real-IP": "127.0.0.1"}},
        {"headers": {"X-Client-IP": "127.0.0.1"}},
        {"headers": {"X-Host": "localhost"}},
        {"headers": {"X-Forwarded-Host": "localhost"}},
        {"headers": {"X-Forwarded-Server": "localhost"}},
        {"headers": {"Forwarded": "for=localhost"}},
        # Method override
        {"method": "PUT"},
        {"method": "PATCH"},
        {"method": "DELETE"},
        {"method": "OPTIONS"},
        {"method": "HEAD"},
        # Path-based bypasses
        {"path_suffix": "?.json"},
        {"path_suffix": "/..;/admin"},
        {"path_suffix": "/%2e%2e%2f"},
        {"path_suffix": "/..%00/"},
        {"path_suffix": "/..%0d/"},
        {"path_suffix": "/..%5c"},
        # Parameter-based
        {"params": {"admin": "true"}},
        {"params": {"isAdmin": "true"}},
        {"params": {"role": "admin"}},
        {"params": {"debug": "true"}},
    ]

    @staticmethod
    async def test_auth_bypass(
        client: httpx.AsyncClient,
        url: str,
        original_headers: dict,
        forbidden_status: int = 403,
    ) -> list[VulnerabilityFinding]:
        """Test various authentication bypass techniques"""
        findings = []

        for technique in AuthBypassTester.BYPASS_TECHNIQUES:
            test_headers = original_headers.copy()
            test_url = url
            test_method = "GET"

            # Apply technique
            if "headers" in technique:
                test_headers.update(technique["headers"])

            if "method" in technique:
                test_method = technique["method"]

            if "path_suffix" in technique:
                test_url = url + technique["path_suffix"]

            if "params" in technique:
                parsed = urlparse(url)
                test_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{urlencode(technique['params'])}"

            try:
                response = await client.request(
                    test_method, test_url, headers=test_headers
                )

                # Check if bypass was successful
                if response.status_code not in [forbidden_status, 401, 404]:
                    if response.status_code < 400:
                        findings.append(VulnerabilityFinding(
                            title="Potential Auth Bypass",
                            severity=Severity.HIGH,
                            endpoint=test_url,
                            method=test_method,
                            description=f"Access granted using bypass technique",
                            evidence=f"Status: {response.status_code}, Technique: {technique}",
                            remediation="Implement proper authentication checks that cannot be bypassed by header manipulation",
                            request_data={"technique": str(technique)},
                        ))

            except Exception as e:
                logger.debug(f"Auth bypass test error: {e}")

        return findings


class SecurityHeaderAnalyzer:
    """Analyze security headers"""

    SECURITY_HEADERS = {
        "Strict-Transport-Security": {
            "severity": Severity.MEDIUM,
            "description": "Missing HSTS header - site may be vulnerable to downgrade attacks",
            "remediation": "Add Strict-Transport-Security header with appropriate max-age",
        },
        "Content-Security-Policy": {
            "severity": Severity.MEDIUM,
            "description": "Missing CSP header - increased XSS risk",
            "remediation": "Implement Content-Security-Policy header",
        },
        "X-Frame-Options": {
            "severity": Severity.LOW,
            "description": "Missing X-Frame-Options - site may be vulnerable to clickjacking",
            "remediation": "Add X-Frame-Options: DENY or SAMEORIGIN",
        },
        "X-Content-Type-Options": {
            "severity": Severity.LOW,
            "description": "Missing X-Content-Type-Options - browser may MIME-sniff content",
            "remediation": "Add X-Content-Type-Options: nosniff",
        },
        "X-XSS-Protection": {
            "severity": Severity.INFO,
            "description": "Missing X-XSS-Protection header",
            "remediation": "Consider adding X-XSS-Protection: 1; mode=block",
        },
        "Referrer-Policy": {
            "severity": Severity.INFO,
            "description": "Missing Referrer-Policy header",
            "remediation": "Add Referrer-Policy header to control referrer information",
        },
        "Permissions-Policy": {
            "severity": Severity.INFO,
            "description": "Missing Permissions-Policy header",
            "remediation": "Add Permissions-Policy to restrict browser features",
        },
    }

    @staticmethod
    def analyze_headers(headers: dict) -> list[VulnerabilityFinding]:
        """Analyze response headers for security issues"""
        findings = []

        for header, info in SecurityHeaderAnalyzer.SECURITY_HEADERS.items():
            if header.lower() not in [h.lower() for h in headers.keys()]:
                findings.append(VulnerabilityFinding(
                    title=f"Missing {header} header",
                    severity=info["severity"],
                    endpoint="Response Headers",
                    method="-",
                    description=info["description"],
                    remediation=info["remediation"],
                ))

        # Check for information disclosure headers
        sensitive_headers = ["Server", "X-Powered-By", "X-AspNet-Version", "X-Generator"]
        for header in sensitive_headers:
            if header.lower() in [h.lower() for h in headers.keys()]:
                findings.append(VulnerabilityFinding(
                    title=f"Information Disclosure via {header} header",
                    severity=Severity.INFO,
                    endpoint="Response Headers",
                    method="-",
                    description=f"{header} header reveals technology stack information",
                    evidence=f"{header}: {headers.get(header, headers.get(header.title(), ''))}",
                    remediation=f"Remove or obfuscate the {header} header",
                ))

        return findings


# ──────────────────────────────────────────────
# HexStrike Bridge
# ──────────────────────────────────────────────

class HexStrikeBridge:
    """
    Universal bridge to HexStrike AI server.
    Supports ALL HexStrike APIs dynamically — no hardcoding per tool.
    
    Architecture:
    - VibeLens (Windows) → HTTP → HexStrike Server (can run in WSL/Docker/Linux VM)
    - HexStrike has 90 dedicated /api/tools/* endpoints + 65 other API endpoints
    - This bridge routes to the right endpoint automatically
    """

    # ── All 90 dedicated tool endpoints (from hexstrike_server.py) ──
    KNOWN_TOOLS = {
        # Network scanning (7)
        "nmap", "nmap-advanced", "rustscan", "masscan", "autorecon",
        "arp-scan", "nbtscan",
        # Web scanning & fuzzing (16)
        "nuclei", "gobuster", "dirb", "dirsearch", "nikto", "ffuf", "wfuzz",
        "wpscan", "sqlmap", "feroxbuster", "katana", "httpx", "dalfox",
        "jaeles", "xsser", "zap",
        # API security (4)
        "api_fuzzer", "api_schema_analyzer", "graphql_scanner", "arjun",
        # Exploitation & Auth (7)
        "metasploit", "msfvenom", "hydra", "john", "hashcat",
        "netexec", "responder",
        # Recon / OSINT (12)
        "amass", "subfinder", "enum4linux", "enum4linux-ng",
        "smbmap", "rpcclient", "dnsenum", "fierce",
        "waybackurls", "gau", "hakrawler", "paramspider",
        # Cloud & Container security (12)
        "prowler", "trivy", "scout-suite", "cloudmapper", "pacu",
        "kube-hunter", "kube-bench", "docker-bench-security",
        "clair", "falco", "checkov", "terrascan",
        # Binary / Reversing / CTF (18)
        "volatility", "volatility3", "binwalk", "ropgadget", "ropper",
        "checksec", "xxd", "strings", "objdump", "ghidra", "pwntools",
        "gdb", "gdb-peda", "radare2", "angr",
        "one-gadget", "pwninit", "libc-database",
        # Forensics & Steganography (3)
        "exiftool", "foremost", "steghide",
        # Utility & Discovery (8)
        "wafw00f", "anew", "uro", "qsreplace", "x8",
        "dotdotpwn", "hashpump", "jwt_analyzer",
        # Browser & Framework (2)
        "browser-agent", "http-framework",
        # Burp alternative (1)
        "burpsuite-alternative",
    }

    # ── Bug Bounty Workflows (6) ──
    WORKFLOWS = {
        "recon": "/api/bugbounty/reconnaissance-workflow",
        "vuln-hunt": "/api/bugbounty/vulnerability-hunting-workflow",
        "business-logic": "/api/bugbounty/business-logic-workflow",
        "osint": "/api/bugbounty/osint-workflow",
        "file-upload": "/api/bugbounty/file-upload-testing",
        "comprehensive": "/api/bugbounty/comprehensive-assessment",
    }

    # ── Intelligence Engine (6) ──
    INTELLIGENCE = {
        "analyze-target": "/api/intelligence/analyze-target",
        "select-tools": "/api/intelligence/select-tools",
        "optimize-params": "/api/intelligence/optimize-parameters",
        "attack-chain": "/api/intelligence/create-attack-chain",
        "smart-scan": "/api/intelligence/smart-scan",
        "tech-detect": "/api/intelligence/technology-detection",
    }

    # ── CTF Suite (7) ──
    CTF_ENDPOINTS = {
        "auto-solve": "/api/ctf/auto-solve-challenge",
        "binary-analyzer": "/api/ctf/binary-analyzer",
        "create-workflow": "/api/ctf/create-challenge-workflow",
        "crypto-solver": "/api/ctf/cryptography-solver",
        "forensics": "/api/ctf/forensics-analyzer",
        "suggest-tools": "/api/ctf/suggest-tools",
        "team-strategy": "/api/ctf/team-strategy",
    }

    # ── Vulnerability Intelligence (5) ──
    VULN_INTEL = {
        "attack-chains": "/api/vuln-intel/attack-chains",
        "cve-monitor": "/api/vuln-intel/cve-monitor",
        "exploit-generate": "/api/vuln-intel/exploit-generate",
        "threat-feeds": "/api/vuln-intel/threat-feeds",
        "zero-day-research": "/api/vuln-intel/zero-day-research",
    }

    # ── AI Payload Generation (3) ──
    AI_PAYLOADS = {
        "advanced-generate": "/api/ai/advanced-payload-generation",
        "generate": "/api/ai/generate_payload",
        "test": "/api/ai/test_payload",
    }

    # ── Error Handling & Recovery (7) ──
    ERROR_HANDLING = {
        "statistics": "/api/error-handling/statistics",
        "test-recovery": "/api/error-handling/test-recovery",
        "fallback-chains": "/api/error-handling/fallback-chains",
        "execute-with-recovery": "/api/error-handling/execute-with-recovery",
        "classify-error": "/api/error-handling/classify-error",
        "parameter-adjustments": "/api/error-handling/parameter-adjustments",
        "alternative-tools": "/api/error-handling/alternative-tools",
    }

    # ── Advanced Process Management (11) ──
    PROCESS_MGMT = {
        "execute-async": "/api/process/execute-async",
        "get-task-result": "/api/process/get-task-result",
        "pool-stats": "/api/process/pool-stats",
        "cache-stats": "/api/process/cache-stats",
        "clear-cache": "/api/process/clear-cache",
        "resource-usage": "/api/process/resource-usage",
        "performance-dashboard": "/api/process/performance-dashboard",
        "terminate-gracefully": "/api/process/terminate-gracefully",
        "auto-scaling": "/api/process/auto-scaling",
        "scale-pool": "/api/process/scale-pool",
        "health-check": "/api/process/health-check",
    }

    # ── File Operations (4) ──
    FILES = {
        "create": "/api/files/create",
        "modify": "/api/files/modify",
        "delete": "/api/files/delete",
        "list": "/api/files/list",
    }

    # ── Visual Reporting (3) ──
    VISUAL = {
        "vulnerability-card": "/api/visual/vulnerability-card",
        "summary-report": "/api/visual/summary-report",
        "tool-output": "/api/visual/tool-output",
    }

    # ── Cache (2) ──
    CACHE = {
        "stats": "/api/cache/stats",
        "clear": "/api/cache/clear",
    }

    # ── Classic Payloads (1) ──
    PAYLOADS = {
        "generate": "/api/payloads/generate",
    }

    def __init__(self, server_url: str = "http://localhost:8888"):
        self.server_url = server_url
        self.client = httpx.AsyncClient(timeout=600.0)

    async def is_available(self) -> bool:
        """Check if HexStrike server is running."""
        try:
            response = await self.client.get(f"{self.server_url}/health", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False

    # ── Core Execution Methods ──

    async def call_tool(self, tool: str, params: dict) -> dict:
        """Call a specific HexStrike tool via its dedicated API endpoint.
        
        Routes to /api/tools/<tool> automatically. Falls back to /api/command
        if the dedicated endpoint doesn't exist.
        
        Args:
            tool: Tool name (e.g. "nmap", "sqlmap", "nuclei", "dalfox", "arjun")
            params: Tool parameters as dict (each tool has its own schema)
        """
        tool_lower = tool.lower().strip()
        
        # Try dedicated endpoint first
        try:
            response = await self.client.post(
                f"{self.server_url}/api/tools/{tool_lower}",
                json=params,
                timeout=600.0,
            )
            if response.status_code != 404:
                return response.json()
        except Exception:
            pass
        
        # Fallback: build command string for generic endpoint
        target = params.get("target", params.get("url", ""))
        command = f"{tool_lower} {target}"
        if params.get("additional_args"):
            command += f" {params['additional_args']}"
        
        return await self.run_command(command)

    async def run_command(self, command: str, use_cache: bool = True) -> dict:
        """Execute any raw bash command via HexStrike generic endpoint.
        
        This is the "Terminal Proxy" — AI can run ANY security tool command.
        
        Args:
            command: Full bash command (e.g. "nmap -sV -p 80,443 target.com")
            use_cache: Use HexStrike's result caching
        """
        response = await self.client.post(
            f"{self.server_url}/api/command",
            json={"command": command, "use_cache": use_cache},
            timeout=600.0,
        )
        return response.json()

    # ── Generic Group Caller ──

    async def _call_group(self, group_map: dict, action: str, data: dict = None,
                          group_name: str = "group", timeout: float = 600.0) -> dict:
        """Universal caller for any API group endpoint."""
        endpoint = group_map.get(action)
        if not endpoint:
            return {"error": f"Unknown {group_name} action: {action}. Available: {list(group_map.keys())}"}
        response = await self.client.post(
            f"{self.server_url}{endpoint}",
            json=data or {},
            timeout=timeout,
        )
        return response.json()

    # ── Intelligence Engine (6) ──

    async def smart_scan(self, target: str, objective: str = "comprehensive", max_tools: int = 5) -> dict:
        """AI-driven smart scan — HexStrike auto-selects optimal tools."""
        return await self._call_group(
            self.INTELLIGENCE, "smart-scan",
            {"target": target, "objective": objective, "max_tools": max_tools},
            "intelligence",
        )

    async def analyze_target(self, target: str) -> dict:
        """AI target profiling — detect technologies, attack surface, risk level."""
        return await self._call_group(
            self.INTELLIGENCE, "analyze-target", {"target": target}, "intelligence", 30.0,
        )

    async def create_attack_chain(self, target: str, objective: str = "comprehensive") -> dict:
        """Create an AI-optimized multi-step attack chain."""
        return await self._call_group(
            self.INTELLIGENCE, "attack-chain",
            {"target": target, "objective": objective}, "intelligence", 30.0,
        )

    async def intelligence(self, action: str, data: dict) -> dict:
        """Call any intelligence endpoint."""
        return await self._call_group(self.INTELLIGENCE, action, data, "intelligence")

    # ── Bug Bounty Workflows (6) ──

    async def run_workflow(self, workflow: str, target: str, **kwargs) -> dict:
        """Run a HexStrike bug bounty workflow."""
        return await self._call_group(
            self.WORKFLOWS, workflow, {"target": target, **kwargs}, "workflow",
        )

    # ── CTF Suite (7) ──

    async def run_ctf(self, action: str, data: dict) -> dict:
        """Run a CTF action (auto-solve, binary analysis, crypto, forensics)."""
        return await self._call_group(self.CTF_ENDPOINTS, action, data, "CTF")

    # ── Vulnerability Intelligence (5) ──

    async def vuln_intel(self, action: str, data: dict) -> dict:
        """Vulnerability intelligence (CVE monitoring, exploit generation, threat feeds)."""
        return await self._call_group(self.VULN_INTEL, action, data, "vuln-intel")

    # ── AI Payload Generation (3) ──

    async def ai_payload(self, action: str = "generate", data: dict = None) -> dict:
        """AI-powered payload generation and testing."""
        return await self._call_group(self.AI_PAYLOADS, action, data, "ai-payload", 60.0)

    # ── Error Handling & Recovery (7) ──

    async def error_handling(self, action: str, data: dict = None) -> dict:
        """Error recovery, fallback chains, parameter adjustments."""
        return await self._call_group(self.ERROR_HANDLING, action, data, "error-handling")

    async def run_command_with_recovery(self, tool: str, command: str, params: dict = None) -> dict:
        """Execute command with HexStrike's intelligent error recovery."""
        return await self.error_handling("execute-with-recovery", {
            "tool": tool, "command": command, "parameters": params or {},
        })

    # ── Advanced Process Management (11) ──

    async def process_mgmt(self, action: str, data: dict = None) -> dict:
        """Advanced process management (async exec, pool, scaling, dashboard)."""
        return await self._call_group(self.PROCESS_MGMT, action, data, "process")

    # ── File Operations (4) ──

    async def file_ops(self, action: str, data: dict = None) -> dict:
        """File operations on HexStrike server (create, modify, delete, list)."""
        endpoint = self.FILES.get(action)
        if not endpoint:
            return {"error": f"Unknown file action: {action}. Available: {list(self.FILES.keys())}"}
        method = "DELETE" if action == "delete" else ("GET" if action == "list" else "POST")
        if method == "GET":
            response = await self.client.get(f"{self.server_url}{endpoint}")
        elif method == "DELETE":
            response = await self.client.request("DELETE", f"{self.server_url}{endpoint}", json=data or {})
        else:
            response = await self.client.post(f"{self.server_url}{endpoint}", json=data or {})
        return response.json()

    # ── Visual Reporting (3) ──

    async def visual_report(self, action: str, data: dict = None) -> dict:
        """Generate visual reports (vulnerability cards, summary, tool output)."""
        return await self._call_group(self.VISUAL, action, data, "visual", 30.0)

    # ── Cache Management (2) ──

    async def cache(self, action: str = "stats") -> dict:
        """Cache management (stats, clear)."""
        endpoint = self.CACHE.get(action)
        if not endpoint:
            return {"error": f"Unknown cache action: {action}. Available: {list(self.CACHE.keys())}"}
        if action == "stats":
            response = await self.client.get(f"{self.server_url}{endpoint}")
        else:
            response = await self.client.post(f"{self.server_url}{endpoint}")
        return response.json()

    # ── Classic Payloads (1) ──

    async def generate_payload(self, attack_type: str, target: str = "", options: dict = None) -> dict:
        """Generate attack payloads via HexStrike."""
        response = await self.client.post(
            f"{self.server_url}/api/payloads/generate",
            json={"attack_type": attack_type, "target": target, **(options or {})},
            timeout=30.0,
        )
        return response.json()

    # ── Python Execution (2) ──

    async def python_exec(self, code: str) -> dict:
        """Execute Python code on HexStrike server."""
        response = await self.client.post(
            f"{self.server_url}/api/python/execute",
            json={"code": code},
            timeout=60.0,
        )
        return response.json()

    async def python_install(self, package: str) -> dict:
        """Install Python package on HexStrike server."""
        response = await self.client.post(
            f"{self.server_url}/api/python/install",
            json={"package": package},
            timeout=60.0,
        )
        return response.json()

    # ── Simple Process Management (6) ──

    async def list_processes(self) -> dict:
        """List all running HexStrike tool processes."""
        response = await self.client.get(f"{self.server_url}/api/processes/list")
        return response.json()

    async def get_process_status(self, pid: int) -> dict:
        """Get status of a specific running process."""
        response = await self.client.get(f"{self.server_url}/api/processes/status/{pid}")
        return response.json()

    async def terminate_process(self, pid: int) -> dict:
        """Terminate a running process."""
        response = await self.client.post(f"{self.server_url}/api/processes/terminate/{pid}")
        return response.json()

    async def pause_process(self, pid: int) -> dict:
        """Pause a running process."""
        response = await self.client.post(f"{self.server_url}/api/processes/pause/{pid}")
        return response.json()

    async def resume_process(self, pid: int) -> dict:
        """Resume a paused process."""
        response = await self.client.post(f"{self.server_url}/api/processes/resume/{pid}")
        return response.json()

    async def processes_dashboard(self) -> dict:
        """Get process dashboard with all active processes."""
        response = await self.client.get(f"{self.server_url}/api/processes/dashboard")
        return response.json()

    async def get_telemetry(self) -> dict:
        """Get server telemetry (CPU, memory, active processes)."""
        response = await self.client.get(f"{self.server_url}/api/telemetry")
        return response.json()

    # ── Discovery / Listing ──

    def list_tools(self) -> list[str]:
        """List all 90 known HexStrike tools."""
        return sorted(self.KNOWN_TOOLS)

    def list_workflows(self) -> dict:
        return dict(self.WORKFLOWS)

    def list_intelligence(self) -> dict:
        return dict(self.INTELLIGENCE)

    def list_ctf(self) -> dict:
        return dict(self.CTF_ENDPOINTS)

    def list_vuln_intel(self) -> dict:
        return dict(self.VULN_INTEL)

    # All API group mappings for dynamic listing
    _ALL_GROUPS = {
        "tools": ("KNOWN_TOOLS", "set"),
        "workflows": ("WORKFLOWS", "dict"),
        "intelligence": ("INTELLIGENCE", "dict"),
        "ctf": ("CTF_ENDPOINTS", "dict"),
        "vuln_intel": ("VULN_INTEL", "dict"),
        "ai_payloads": ("AI_PAYLOADS", "dict"),
        "error_handling": ("ERROR_HANDLING", "dict"),
        "process_mgmt": ("PROCESS_MGMT", "dict"),
        "files": ("FILES", "dict"),
        "visual": ("VISUAL", "dict"),
        "cache": ("CACHE", "dict"),
        "payloads": ("PAYLOADS", "dict"),
    }

    def get_all_capabilities(self) -> dict:
        """Get a complete summary of ALL 156 HexStrike capabilities."""
        result = {}
        total = 0
        for key, (attr_name, attr_type) in self._ALL_GROUPS.items():
            data = getattr(self, attr_name)
            count = len(data)
            result[key] = count
            total += count
        # Add fixed endpoints: /health, /api/command, /api/telemetry, 
        # /api/processes/* (6), /api/python/* (2)
        fixed = 1 + 1 + 1 + 6 + 2  # health, command, telemetry, processes, python
        result["fixed_endpoints"] = fixed
        total += fixed
        result["total_capabilities"] = total
        return result

    async def close(self):
        await self.client.aclose()


# ──────────────────────────────────────────────
# Main Security Scanner
# ──────────────────────────────────────────────

class SecurityScanner:
    """Main security scanner that combines all tools"""

    def __init__(self, hexstrike_url: str = "http://localhost:8888"):
        self.hexstrike = HexStrikeBridge(hexstrike_url)
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    async def scan_captured_endpoints(
        self,
        requests: list[dict],
        tests: list[str] = ["idor", "headers", "fuzz"],
    ) -> SecurityScanResult:
        """
        Scan captured API endpoints for vulnerabilities.

        Args:
            requests: List of captured requests from VibeLens
            tests: Types of tests to run
        """
        import time
        start_time = time.time()

        result = SecurityScanResult(target="captured_endpoints")

        for req in requests:
            url = req.get("url", "")
            method = req.get("method", "GET")
            headers = req.get("headers", {})
            body = req.get("body") or req.get("postData")

            result.endpoints_tested += 1

            # IDOR testing
            if "idor" in tests:
                findings = await IDORTester.test_idor(
                    self.client, url, method, headers, body
                )
                result.findings.extend(findings)

            # Security headers analysis
            if "headers" in tests:
                try:
                    response = await self.client.get(url, headers=headers)
                    findings = SecurityHeaderAnalyzer.analyze_headers(dict(response.headers))
                    result.findings.extend(findings)
                except Exception as e:
                    logger.debug(f"Header analysis error: {e}")

            # Parameter fuzzing
            if "fuzz" in tests:
                params = ParameterFuzzer.extract_parameters(req)
                for param_name, values in params.items():
                    if values:
                        findings = await ParameterFuzzer.fuzz_parameter(
                            self.client, url, method, headers, param_name, values[0]
                        )
                        result.findings.extend(findings)

        result.scan_duration = time.time() - start_time
        return result

    async def quick_vuln_scan(self, url: str) -> SecurityScanResult:
        """Quick vulnerability scan of a single endpoint"""
        import time
        start_time = time.time()

        result = SecurityScanResult(target=url)
        result.endpoints_tested = 1

        try:
            # Get response for header analysis
            response = await self.client.get(url)
            headers = dict(response.headers)

            # Security headers
            findings = SecurityHeaderAnalyzer.analyze_headers(headers)
            result.findings.extend(findings)

            # IDOR test
            idor_findings = await IDORTester.test_idor(self.client, url, "GET", {})
            result.findings.extend(idor_findings)

        except Exception as e:
            logger.error(f"Scan error: {e}")

        result.scan_duration = time.time() - start_time
        return result

    async def auth_bypass_scan(self, url: str, headers: dict = None) -> SecurityScanResult:
        """Test authentication bypass techniques"""
        import time
        start_time = time.time()

        result = SecurityScanResult(target=url)
        result.endpoints_tested = 1

        findings = await AuthBypassTester.test_auth_bypass(
            self.client, url, headers or {}
        )
        result.findings.extend(findings)

        result.scan_duration = time.time() - start_time
        return result

    async def close(self):
        await self.client.aclose()
        await self.hexstrike.close()