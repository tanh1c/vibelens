# VibeLens Security Integration Guide

> Bug Bounty Hunting & Security Research with VibeLens + HexStrike AI

---

## Overview

VibeLens now includes built-in security testing tools and integration with HexStrike AI for advanced penetration testing.

### Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  VibeLens       │───▶│  Built-in       │───▶│  HexStrike AI   │
│  (Capture)      │    │  Security Tools │    │  (Advanced)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                      │                      │
         ▼                      ▼                      ▼
   API Endpoints          IDOR, XSS, SQLi       nmap, nuclei
   Cookies/Tokens         Auth Bypass           sqlmap, ffuf
   Request Patterns       Security Headers      hydra, john
```

---

## Built-in Security Tools

### 1. IDOR Testing

Insecure Direct Object Reference - tự động detect và test ID parameters.

**CLI:**
```bash
# Test IDOR trên tất cả captured requests
vibelens security scan --tests idor

# Test IDOR trên request cụ thể
vibelens security idor 1
```

**MCP Tool:**
```
test_idor(request_index=1)
```

**Ví dụ Use Case:**
1. Capture request `/api/users/123/profile`
2. IDOR tester sẽ:
   - Detect `123` là ID parameter
   - Test với các giá trị: `124`, `122`, `1`, `0`, `999999`
   - Báo cáo nếu access được data của user khác

### 2. Parameter Fuzzing

Fuzz parameters với SQLi, XSS, Path Traversal, SSRF payloads.

**CLI:**
```bash
# Fuzz tất cả parameters
vibelens security scan --tests fuzz

# Fuzz request cụ thể với SQLi payloads
vibelens security fuzz 1 --type sqli
```

**MCP Tool:**
```
fuzz_parameters(request_index=1, fuzz_type="sqli")
```

**Payload Types:**
| Type | Payloads | Description |
|------|----------|-------------|
| `sqli` | 6 | SQL Injection |
| `xss` | 5 | Cross-Site Scripting |
| `traversal` | 4 | Path Traversal |
| `ssrf` | 4 | Server-Side Request Forgery |
| `all` | 19 | All payloads |

### 3. Auth Bypass Testing

Test các kỹ thuật bypass authentication.

**CLI:**
```bash
vibelens security auth-bypass 1
```

**MCP Tool:**
```
test_auth_bypass(request_index=1)
```

**Techniques Tested:**
- Header manipulation (X-Forwarded-For, X-Real-IP, X-Original-URL)
- Method override (PUT, PATCH, OPTIONS, HEAD)
- Path tricks (?.json, /..;/admin, /%2e%2e%2f)
- Parameter injection (admin=true, isAdmin=true)

### 4. Security Headers Analysis

Kiểm tra missing security headers.

**CLI:**
```bash
# Check URL
vibelens security headers https://example.com

# Check captured requests
vibelens security headers
```

**MCP Tool:**
```
check_security_headers(url="https://example.com")
```

**Headers Checked:**
- Strict-Transport-Security (HSTS)
- Content-Security-Policy (CSP)
- X-Frame-Options
- X-Content-Type-Options
- X-XSS-Protection
- Referrer-Policy
- Permissions-Policy

---

## HexStrike AI Integration

### Setup HexStrike

```bash
# 1. Navigate to hexstrike-ai
cd hexstrike-ai

# 2. Create venv
python -m venv hexstrike-env
hexstrike-env\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start server
python hexstrike_server.py
```

### Check Connection

```bash
vibelens security hexstrike
```

### Advanced Scans

```bash
# Quick vulnerability scan
vibelens security hexstrike-scan https://example.com --type quick

# Full reconnaissance
vibelens security hexstrike-scan https://example.com --type full
```

### Available HexStrike Tools

| Category | Tools |
|----------|-------|
| Network | nmap, rustscan, masscan, autorecon |
| Web | nuclei, sqlmap, ffuf, gobuster, nikto |
| Auth | hydra, john, hashcat |
| Cloud | prowler, scout-suite, trivy |
| CTF | volatility, binwalk, steghide |

---

## Use Cases

### Use Case 1: Bug Bounty - API Security Testing

**Scenario:** Bạn muốn test API của một bug bounty target.

**Workflow:**
```bash
# 1. Capture traffic với Chrome Extension
#    - Browse target website
#    - Perform various actions
#    - Stop recording

# 2. Quick security scan
vibelens security scan

# 3. Review findings
#    - IDOR vulnerabilities
#    - Missing security headers
#    - Potential injection points

# 4. Deep dive vào specific endpoints
vibelens security idor 5
vibelens security fuzz 5 --type sqli

# 5. Advanced scan với HexStrike
vibelens security hexstrike-scan https://target.com/api --type full
```

**MCP Workflow:**
```
1. "List my captured requests"
   → get_filtered_requests()

2. "Scan for IDOR vulnerabilities"
   → security_scan(tests="idor")

3. "Test request #5 for SQL injection"
   → fuzz_parameters(request_index=5, fuzz_type="sqli")

4. "Check if HexStrike is available"
   → hexstrike_status()

5. "Run advanced scan"
   → hexstrike_scan(target="https://target.com", scan_type="vuln")
```

### Use Case 2: IDOR Hunting

**Scenario:** Tìm IDOR trong ứng dụng web.

**Workflow:**
```bash
# 1. Capture requests có ID parameters
#    Ví dụ: /api/orders/123, /api/users/456

# 2. Analyze IDOR parameters
vibelens security idor 1

# Output:
# Found IDOR parameters:
#   • id: 123
#     Test with: ['124', '122', '1', '0', '999999']

# 3. Run full IDOR scan
vibelens security scan --tests idor

# 4. Manual verification với execute_http_request
# (qua MCP tool)
```

### Use Case 3: Finding Hidden Endpoints

**Scenario:** Tìm hidden API endpoints.

**Workflow:**
```bash
# 1. Browse website để capture baseline traffic

# 2. Analyze patterns
vibelens requests list --pattern "api"

# 3. Use HexStrike for directory brute force
vibelens security hexstrike-scan https://target.com --type full

# HexStrike sẽ chạy:
# - ffuf: Directory fuzzing
# - nuclei: Vulnerability scanning
# - katana: Endpoint discovery
```

### Use Case 4: Testing Auth Bypass

**Scenario:** Test authentication mechanism.

**Workflow:**
```bash
# 1. Capture authenticated request
#    Ví dụ: /admin/dashboard (403 Forbidden)

# 2. Test bypass techniques
vibelens security auth-bypass 1

# 3. Nếu bypass thành công:
#    - Note technique used
#    - Report to bug bounty program
```

### Use Case 5: Security Headers Audit

**Scenario:** Audit security headers của target.

**Workflow:**
```bash
# Quick check
vibelens security headers https://target.com

# Output:
# ❌ Missing Strict-Transport-Security header
# ❌ Missing Content-Security-Policy header
# ⚠️ Information Disclosure via Server header
```

---

## CLI Reference

### Security Commands

```bash
vibelens security scan              # Full security scan
vibelens security scan --tests idor # IDOR only
vibelens security scan --tests fuzz # Fuzzing only
vibelens security scan --tests headers # Headers only

vibelens security idor <index>      # Test IDOR on request
vibelens security fuzz <index>      # Fuzz parameters
vibelens security fuzz <index> --type sqli  # SQLi fuzzing

vibelens security headers [url]     # Check security headers
vibelens security auth-bypass <index>  # Test auth bypass

vibelens security hexstrike         # Check HexStrike status
vibelens security hexstrike-scan <target>  # Advanced scan
```

---

## MCP Tools Reference

### Built-in Security Tools

| Tool | Description |
|------|-------------|
| `security_scan(tests, limit)` | Scan captured endpoints |
| `test_idor(request_index)` | IDOR testing |
| `fuzz_parameters(request_index, fuzz_type)` | Parameter fuzzing |
| `test_auth_bypass(request_index)` | Auth bypass testing |
| `check_security_headers(url)` | Headers analysis |

### HexStrike Bridge Tools

| Tool | Description |
|------|-------------|
| `hexstrike_status()` | Check HexStrike connection |
| `hexstrike_scan(target, scan_type)` | Advanced vulnerability scan |

---

## Tips & Best Practices

### 1. Workflow cho Bug Bounty

```
Capture → Filter → Analyze → Test → Report
   ↓         ↓         ↓        ↓        ↓
Chrome    Smart    Auth    Security  Findings
Extension  Filter  Info    Tools
```

### 2. Prioritize Testing

1. **IDOR** - High impact, easy to test
2. **Auth Bypass** - Critical vulnerabilities
3. **SQL Injection** - Critical vulnerabilities
4. **Security Headers** - Quick wins
5. **XSS** - Common in web apps

### 3. Combine Tools

```bash
# Full workflow
vibelens security scan              # Built-in quick scan
vibelens security hexstrike-scan    # HexStrike advanced scan
```

### 4. Document Findings

Khi tìm thấy vulnerability:
1. Screenshot evidence
2. Record request/response
3. Note reproduction steps
4. Check for false positives
5. Report responsibly

---

## Troubleshooting

### "HexStrike server not available"

```bash
# Check if HexStrike is running
cd hexstrike-ai
python hexstrike_server.py

# Verify connection
vibelens security hexstrike
```

### "No requests to scan"

```bash
# Start bridge server
vibelens server start

# Use Chrome Extension to capture
# Or import HAR file
vibelens har /path/to/file.har
```

### Scan Timeout

```bash
# Reduce limit
vibelens security scan --limit 10

# Test specific requests
vibelens security idor 1
```

---

## Legal & Ethical Use

⚠️ **Important:**

- ✅ **Authorized Penetration Testing** - With written permission
- ✅ **Bug Bounty Programs** - Within program scope
- ✅ **CTF Competitions** - Educational environments
- ✅ **Security Research** - On owned systems

- ❌ **Unauthorized Testing** - Never test without permission
- ❌ **Malicious Activities** - No illegal activities
- ❌ **Data Theft** - No unauthorized data access

---

## License

MIT License - VibeLens & HexStrike AI