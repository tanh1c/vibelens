"""
HexStrike Endpoint Extractor v2.0
==================================
Script tự động parse hexstrike_server.py VÀ hexstrike_mcp.py để trích xuất:
1. Tất cả /api/* endpoints từ server (URL, method, params, docstring)
2. Tất cả MCP tools từ mcp client (function name, params, docstring)
3. So sánh VibeLens bridge hiện tại vs HexStrike thật → tìm thiếu sót
4. Generate Python code sẵn sàng paste vào HexStrikeBridge

Usage:
    python scripts/extract_hexstrike_endpoints.py
    python scripts/extract_hexstrike_endpoints.py --hexstrike-dir /path/to/hexstrike-ai
    python scripts/extract_hexstrike_endpoints.py --compare  # So sánh với VibeLens bridge
"""
import re
import json
import os
import sys
import argparse
from pathlib import Path

# ═══════════════════════════════════════════
# Config
# ═══════════════════════════════════════════
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent  # vibelens/
VIBELENS_ROOT = PROJECT_ROOT.parent  # VibeLens/

DEFAULT_HEXSTRIKE_DIR = VIBELENS_ROOT / "hexstrike-ai"
BRIDGE_FILE = PROJECT_ROOT / "vibeengine" / "security" / "__init__.py"


def find_hexstrike_dir(custom_dir=None):
    """Find hexstrike-ai directory."""
    if custom_dir:
        p = Path(custom_dir)
        if p.exists():
            return p
    if DEFAULT_HEXSTRIKE_DIR.exists():
        return DEFAULT_HEXSTRIKE_DIR
    # Search common locations
    for candidate in [
        VIBELENS_ROOT / "hexstrike-ai",
        Path.home() / "hexstrike-ai",
    ]:
        if candidate.exists():
            return candidate
    return None


def extract_server_endpoints(server_py: Path) -> dict:
    """Extract ALL @app.route endpoints from hexstrike_server.py."""
    content = server_py.read_text(encoding="utf-8")
    lines = content.split("\n")

    route_re = re.compile(r'@app\.route\("([^"]+)"(?:,\s*methods=\[([^\]]+)\])?\)')
    endpoints = []

    for i, line in enumerate(lines):
        m = route_re.search(line)
        if not m:
            continue

        url = m.group(1)
        methods_raw = m.group(2) or '"GET"'
        methods = [x.strip().strip('"').strip("'") for x in methods_raw.split(",")]

        # Find function name
        func_name = "unknown"
        docstring = ""
        for j in range(i + 1, min(i + 5, len(lines))):
            fn_match = re.search(r"def\s+(\w+)", lines[j])
            if fn_match:
                func_name = fn_match.group(1)
                for k in range(j + 1, min(j + 4, len(lines))):
                    if '"""' in lines[k]:
                        docstring = lines[k].strip().strip('"""').strip()
                        if not docstring and k + 1 < len(lines):
                            docstring = lines[k + 1].strip().strip('"""').strip()
                        break
                break

        # Find params
        params = set()
        for j in range(i + 1, min(i + 50, len(lines))):
            for pm in re.finditer(r'(?:params|data|request\.json)\.get\("([^"]+)"', lines[j]):
                params.add(pm.group(1))
            if j > i + 3 and lines[j].strip().startswith("@app.route"):
                break

        endpoints.append({
            "url": url,
            "methods": methods,
            "function": func_name,
            "docstring": docstring,
            "params": sorted(params),
            "line": i + 1,
        })

    return {
        "total": len(endpoints),
        "endpoints": endpoints,
    }


def extract_mcp_tools(mcp_py: Path) -> dict:
    """Extract ALL @mcp.tool() functions from hexstrike_mcp.py."""
    content = mcp_py.read_text(encoding="utf-8")
    lines = content.split("\n")

    tools = []
    tool_marker_re = re.compile(r"@mcp\.tool\(\)")

    for i, line in enumerate(lines):
        if not tool_marker_re.search(line):
            continue

        # Find the def line
        func_name = "unknown"
        params = []
        docstring = ""
        for j in range(i + 1, min(i + 5, len(lines))):
            fn_match = re.match(r"\s*def\s+(\w+)\((.+?)(?:\)|$)", lines[j])
            if fn_match:
                func_name = fn_match.group(1)
                raw_params = fn_match.group(2)
                # Continue to next lines if params span multiple lines
                full_sig = lines[j]
                k = j
                while ")" not in full_sig and k < min(j + 5, len(lines)):
                    k += 1
                    full_sig += " " + lines[k].strip()
                # Parse params
                sig_match = re.search(r"def\s+\w+\((.+?)\)", full_sig)
                if sig_match:
                    raw = sig_match.group(1)
                    for p in raw.split(","):
                        p = p.strip().split(":")[0].strip().split("=")[0].strip()
                        if p and p != "self":
                            params.append(p)

                # Get docstring
                for m in range(k + 1, min(k + 4, len(lines))):
                    if '"""' in lines[m]:
                        ds_start = m
                        if lines[m].count('"""') >= 2:
                            docstring = lines[m].strip().strip('"""').strip()
                        else:
                            ds_lines = []
                            for n in range(m + 1, min(m + 10, len(lines))):
                                if '"""' in lines[n]:
                                    break
                                ds_lines.append(lines[n].strip())
                            docstring = " ".join(ds_lines)[:200]
                        break
                break

        if func_name != "unknown":
            tools.append({
                "name": func_name,
                "params": params,
                "docstring": docstring,
                "line": i + 1,
            })

    return {
        "total": len(tools),
        "tools": tools,
    }


def categorize_endpoints(endpoints: list) -> dict:
    """Group endpoints by API category."""
    categories = {}
    tools = []

    for ep in endpoints:
        url = ep["url"]
        parts = url.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "api":
            category = parts[1]
            if category == "tools" and len(parts) >= 3:
                tool_name = parts[2].split("<")[0].rstrip("/")
                if tool_name:
                    tools.append(tool_name)
        else:
            category = "root"

        categories.setdefault(category, []).append(ep)

    return {
        "categories": {k: len(v) for k, v in sorted(categories.items())},
        "categories_detail": categories,
        "tools": sorted(set(tools)),
        "tool_count": len(set(tools)),
    }


def compare_with_bridge(bridge_file: Path, server_data: dict) -> dict:
    """Compare VibeLens bridge against actual HexStrike endpoints."""
    if not bridge_file.exists():
        return {"error": f"Bridge file not found: {bridge_file}"}

    content = bridge_file.read_text(encoding="utf-8")

    # Extract KNOWN_TOOLS set
    bridge_tools = set()
    in_tools = False
    for line in content.split("\n"):
        if "KNOWN_TOOLS" in line and "{" in line:
            in_tools = True
        if in_tools:
            for m in re.finditer(r'"([^"]+)"', line):
                bridge_tools.add(m.group(1))
            if "}" in line and in_tools:
                in_tools = False

    # Extract all endpoint dicts
    bridge_endpoints = set()
    for m in re.finditer(r'"/api/([^"]+)"', content):
        bridge_endpoints.add("/api/" + m.group(1))

    server_tools = set(server_data["tools"])
    server_urls = set(ep["url"] for ep in server_data["endpoints"])

    missing_tools = server_tools - bridge_tools
    extra_tools = bridge_tools - server_tools
    missing_urls = server_urls - bridge_endpoints
    # Filter out parameterized URLs from missing
    missing_urls = {u for u in missing_urls if "<" not in u}

    return {
        "bridge_tools": len(bridge_tools),
        "server_tools": len(server_tools),
        "missing_tools": sorted(missing_tools),
        "extra_tools": sorted(extra_tools),
        "missing_endpoints": sorted(missing_urls),
        "coverage_pct": round(len(bridge_tools & server_tools) / max(len(server_tools), 1) * 100, 1),
    }


def generate_bridge_code(server_data: dict) -> str:
    """Generate Python code for HexStrikeBridge KNOWN_TOOLS and endpoint dicts."""
    lines = []

    # Tool set
    tools = server_data["tools"]
    lines.append(f"    # ── All {len(tools)} dedicated tool endpoints ──")
    lines.append(f"    KNOWN_TOOLS = {{")
    for name in tools:
        lines.append(f'        "{name}",')
    lines.append(f"    }}")
    lines.append("")

    # Non-tool groups
    cats = server_data["categories_detail"]
    for cat, eps in sorted(cats.items()):
        if cat in ("tools", "root"):
            continue
        var = cat.upper().replace("-", "_")
        lines.append(f"    # ── {cat.title()} ({len(eps)}) ──")
        lines.append(f"    {var} = {{")
        for ep in eps:
            action = ep["url"].replace(f"/api/{cat}/", "").split("/")[0].split("<")[0].rstrip("/")
            lines.append(f'        "{action}": "{ep["url"]}",')
        lines.append(f"    }}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Extract HexStrike endpoints")
    parser.add_argument("--hexstrike-dir", help="Path to hexstrike-ai directory")
    parser.add_argument("--compare", action="store_true", help="Compare with VibeLens bridge")
    parser.add_argument("--output", default=None, help="Output JSON file path")
    parser.add_argument("--codegen", action="store_true", help="Print generated Python code")
    args = parser.parse_args()

    hexstrike_dir = find_hexstrike_dir(args.hexstrike_dir)
    if not hexstrike_dir:
        print("❌ Cannot find hexstrike-ai directory")
        print(f"   Tried: {DEFAULT_HEXSTRIKE_DIR}")
        print("   Use --hexstrike-dir to specify location")
        sys.exit(1)

    server_py = hexstrike_dir / "hexstrike_server.py"
    mcp_py = hexstrike_dir / "hexstrike_mcp.py"

    print(f"📂 HexStrike dir: {hexstrike_dir}")
    print(f"{'=' * 60}")

    # ── Server endpoints ──
    if server_py.exists():
        print(f"\n🔍 Parsing hexstrike_server.py ({server_py.stat().st_size // 1024}KB)...")
        server_data = extract_server_endpoints(server_py)
        cat_data = categorize_endpoints(server_data["endpoints"])

        print(f"   ✅ Found {server_data['total']} API endpoints")
        print(f"   ✅ Found {cat_data['tool_count']} tools in /api/tools/*")
        print(f"\n   API Groups:")
        for cat, count in cat_data["categories"].items():
            print(f"     /api/{cat}: {count}")
    else:
        print(f"   ⚠️ hexstrike_server.py not found")
        server_data = {"total": 0, "endpoints": []}
        cat_data = {"categories": {}, "tools": [], "tool_count": 0, "categories_detail": {}}

    # ── MCP tools ──
    if mcp_py.exists():
        print(f"\n🔍 Parsing hexstrike_mcp.py ({mcp_py.stat().st_size // 1024}KB)...")
        mcp_data = extract_mcp_tools(mcp_py)
        print(f"   ✅ Found {mcp_data['total']} MCP tools")

        # Find composite (MCP-only) tools
        server_funcs = {ep["function"] for ep in server_data["endpoints"]}
        tool_names_from_server = set(cat_data["tools"])
        mcp_names = {t["name"] for t in mcp_data["tools"]}

        # MCP tools that map to /api/tools/* (most of them)
        mapped = set()
        unmapped = set()
        for t in mcp_data["tools"]:
            name = t["name"]
            # Normalize: nmap_scan → nmap, nuclei_scan → nuclei
            normalized = name.replace("_scan", "").replace("_analyze", "").replace("_attack", "")
            if normalized in tool_names_from_server or name in server_funcs:
                mapped.add(name)
            else:
                unmapped.add(name)

        print(f"   ├─ Mapped to server APIs: {len(mapped)}")
        print(f"   └─ Composite/MCP-only: {len(unmapped)}")
        if unmapped:
            print(f"       {', '.join(sorted(unmapped)[:15])}...")
    else:
        mcp_data = {"total": 0, "tools": []}

    # ── Compare with bridge ──
    if args.compare and BRIDGE_FILE.exists():
        print(f"\n{'=' * 60}")
        print(f"📊 Comparing with VibeLens bridge...")
        merged = {**cat_data, "endpoints": server_data["endpoints"]}
        comparison = compare_with_bridge(BRIDGE_FILE, merged)

        pct = comparison["coverage_pct"]
        icon = "✅" if pct >= 95 else "⚠️" if pct >= 80 else "❌"
        print(f"   {icon} Tool coverage: {pct}% ({comparison['bridge_tools']}/{comparison['server_tools']})")

        if comparison["missing_tools"]:
            print(f"\n   ❌ Missing tools ({len(comparison['missing_tools'])}):")
            for t in comparison["missing_tools"]:
                print(f"     • {t}")

        if comparison["extra_tools"]:
            print(f"\n   ⚡ Extra tools in bridge (not in server):")
            for t in comparison["extra_tools"]:
                print(f"     • {t}")

        if comparison["missing_endpoints"]:
            print(f"\n   ❌ Missing API endpoints ({len(comparison['missing_endpoints'])}):")
            for u in comparison["missing_endpoints"][:20]:
                print(f"     • {u}")

    # ── Code generation ──
    if args.codegen:
        print(f"\n{'=' * 60}")
        print("📝 GENERATED PYTHON CODE:")
        print(generate_bridge_code({**cat_data, "categories_detail": cat_data.get("categories_detail", {})}))

    # ── Save report ──
    output_path = args.output or str(SCRIPT_DIR / "hexstrike_endpoints.json")
    report = {
        "extracted_at": __import__("datetime").datetime.now().isoformat(),
        "hexstrike_dir": str(hexstrike_dir),
        "server": {
            "total_endpoints": server_data["total"],
            "tool_count": cat_data["tool_count"],
            "tool_names": cat_data["tools"],
            "categories": cat_data["categories"],
        },
        "mcp": {
            "total_tools": mcp_data["total"],
            "tool_names": [t["name"] for t in mcp_data["tools"]],
        },
        "all_endpoints": server_data["endpoints"],
    }

    Path(output_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n📄 Report saved: {output_path}")

    # ── Summary ──
    print(f"\n{'=' * 60}")
    print(f"🎯 SUMMARY:")
    print(f"   Server API endpoints: {server_data['total']}")
    print(f"   Server tools:         {cat_data['tool_count']}")
    print(f"   MCP tools:            {mcp_data['total']}")
    print(f"   Report:               {output_path}")


if __name__ == "__main__":
    main()
