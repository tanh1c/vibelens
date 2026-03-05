"""Network analyzer - AI-powered API analysis"""

import json
import logging
from typing import Any

from vibeengine.llm import BaseLLM, ChatOpenAI
from vibeengine.network.interceptor import NetworkEntry

logger = logging.getLogger(__name__)


class NetworkAnalyzer:
    """
    AI-powered network traffic analyzer.

    Analyzes captured API requests/responses and provides insights.
    """

    def __init__(self, llm: BaseLLM | None = None):
        self.llm = llm or ChatOpenAI()

    async def analyze_api(
        self,
        entries: list[NetworkEntry],
        prompt: str | None = None,
    ) -> str:
        """
        Analyze API requests and responses.

        Args:
            entries: List of captured network entries
            prompt: Custom analysis prompt

        Returns:
            AI analysis results
        """
        # Build context from entries
        context = self._build_context(entries)

        # Build prompt
        analysis_prompt = prompt or """Analyze these API requests and responses. Identify:
1. API structure and patterns
2. Authentication methods used
3. Potential issues or improvements
4. Request/response schemas

Provide a detailed analysis."""

        messages = [
            {
                "role": "system",
                "content": "You are an API expert. Analyze network traffic and provide insights.",
            },
            {
                "role": "user",
                "content": f"{analysis_prompt}\n\nAPI Traffic:\n{context}",
            },
        ]

        result = await self.llm.chat(messages)
        return result

    async def suggest_optimizations(
        self,
        entries: list[NetworkEntry],
    ) -> str:
        """Suggest API optimizations"""
        context = self._build_context(entries)

        messages = [
            {
                "role": "system",
                "content": "You are a performance expert. Suggest API optimizations.",
            },
            {
                "role": "user",
                "content": f"""Analyze these API calls and suggest optimizations:
- Request batching opportunities
- Caching strategies
- Payload optimizations
- Pagination improvements

API Traffic:
{context}""",
            },
        ]

        return await self.llm.chat(messages)

    async def generate_postman_collection(
        self,
        entries: list[NetworkEntry],
        collection_name: str = "VibeLens Collection",
    ) -> dict[str, Any]:
        """Generate Postman collection from captured requests"""
        requests = [e for e in entries if e.request.method in ["GET", "POST", "PUT", "DELETE", "PATCH"]]

        collection = {
            "info": {
                "name": collection_name,
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [],
        }

        for entry in requests:
            # Group by domain
            from urllib.parse import urlparse
            parsed = urlparse(entry.request.url)
            domain = parsed.netloc

            request_item = {
                "name": f"{entry.request.method} {parsed.path or '/'}",
                "request": {
                    "method": entry.request.method,
                    "url": {
                        "raw": entry.request.url,
                        "protocol": parsed.scheme,
                        "host": parsed.netloc.split("."),
                        "path": parsed.path.lstrip("/").split("/") if parsed.path else [],
                        "query": [
                            {"key": k, "value": v}
                            for k, v in [q.split("=") for q in parsed.query.split("&") if q]
                        ] if parsed.query else [],
                    },
                    "header": [
                        {"key": k, "value": v}
                        for k, v in entry.request.headers.items()
                    ],
                },
            }

            # Add body if present
            if entry.request.post_data:
                try:
                    json_data = json.loads(entry.request.post_data)
                    request_item["request"]["body"] = {
                        "mode": "raw",
                        "raw": json.dumps(json_data, indent=2),
                        "options": {"raw": {"language": "json"}},
                    }
                except Exception:
                    request_item["request"]["body"] = {
                        "mode": "raw",
                        "raw": entry.request.post_data,
                    }

            # Find or create folder for this domain
            folder = None
            for item in collection["item"]:
                if isinstance(item, dict) and item.get("name") == domain:
                    folder = item
                    break

            if folder is None:
                folder = {"name": domain, "item": []}
                collection["item"].append(folder)

            folder["item"].append(request_item)

        return collection

    async def generate_jest_tests(
        self,
        entries: list[NetworkEntry],
    ) -> str:
        """Generate Jest tests from captured requests"""
        requests = [e for e in entries if e.request.method in ["GET", "POST", "PUT", "DELETE", "PATCH"]]

        test_code = """// Generated by VibeLens
import axios from 'axios';

"""

        for entry in requests:
            from urllib.parse import urlparse
            parsed = urlparse(entry.request.url)
            test_name = f"{entry.request.method.lower()}_{parsed.path.replace('/', '_').strip('_') or 'root'}"

            test_code += f"""describe('{parsed.path or '/'}', () => {{
    it('should {entry.request.method} {parsed.path or "/"}', async () => {{
"""

            if entry.request.post_data:
                test_code += f"""        const response = await axios.{entry.request.method.lower()}(
            '{entry.request.url}',
            {entry.request.post_data},
            {{ headers: {{ 'Content-Type': 'application/json' }} }}
        );
"""
            else:
                test_code += f"""        const response = await axios.{entry.request.method.lower()}('{entry.request.url}');
"""

            if entry.response:
                test_code += f"""        expect(response.status).toBe({entry.response.status});
"""
            else:
                test_code += """        expect(response.status).toBeDefined();
"""

            test_code += """    });
});
"""

        return test_code

    def _build_context(self, entries: list[NetworkEntry]) -> str:
        """Build context string from entries"""
        lines = []

        for i, entry in enumerate(entries[:20]):  # Limit to 20 entries
            lines.append(f"\n--- Request {i + 1} ---")
            lines.append(f"Method: {entry.request.method}")
            lines.append(f"URL: {entry.request.url}")
            lines.append(f"Headers: {json.dumps(dict(entry.request.headers), indent=2)}")

            if entry.request.post_data:
                lines.append(f"Body: {entry.request.post_data[:500]}")

            if entry.response:
                lines.append(f"Status: {entry.response.status} {entry.response.status_text}")
                lines.append(f"Response Headers: {json.dumps(dict(entry.response.headers), indent=2)}")
                if entry.response.body:
                    lines.append(f"Response Body: {entry.response.body[:500]}")

            if entry.duration:
                lines.append(f"Duration: {entry.duration:.2f}ms")

        return "\n".join(lines)
