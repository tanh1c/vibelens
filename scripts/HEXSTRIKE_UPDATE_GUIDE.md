# 🔄 HexStrike Integration Update Guide

> **For:** Developers & AI Agents maintaining VibeLens + HexStrike integration  
> **Script:** `vibelens/scripts/extract_hexstrike_endpoints.py`

---

## Khi nào cần chạy?

Chạy script khi:
- ✅ Vừa `git pull` cập nhật HexStrike repo
- ✅ Muốn kiểm tra xem VibeLens đã cover hết chưa
- ✅ HexStrike release version mới
- ✅ Đang debug một tool không hoạt động

---

## Quick Start

### 1. Kiểm tra coverage hiện tại

```bash
cd vibelens
python scripts/extract_hexstrike_endpoints.py --compare
```

Output mong đợi:
```
✅ Tool coverage: 100.0% (90/90)
```

### 2. Nếu HexStrike có tool mới

```bash
# Cập nhật HexStrike
cd ../hexstrike-ai
git pull origin main

# Quay lại VibeLens và kiểm tra
cd ../vibelens
python scripts/extract_hexstrike_endpoints.py --compare
```

Nếu output hiện:
```
⚠️ Tool coverage: 95.7% (90/94)

❌ Missing tools (4):
  • new_tool_1
  • new_tool_2
  • new_tool_3
  • new_tool_4
```

→ Cần cập nhật VibeLens bridge.

### 3. Generate code cho tools mới

```bash
python scripts/extract_hexstrike_endpoints.py --codegen
```

Script sẽ in ra Python code sẵn sàng paste vào `vibeengine/security/__init__.py`.

### 4. Xem report chi tiết

```bash
python scripts/extract_hexstrike_endpoints.py --output report.json
```

File `report.json` chứa toàn bộ endpoints, params, docstrings.

---

## Cách cập nhật VibeLens khi HexStrike có tool mới

### Bước 1: Chạy script extract

```bash
python scripts/extract_hexstrike_endpoints.py --compare --codegen
```

### Bước 2: Cập nhật `KNOWN_TOOLS` trong bridge

Mở file `vibelens/vibeengine/security/__init__.py`, tìm `KNOWN_TOOLS = {` và thêm tools mới:

```python
KNOWN_TOOLS = {
    # ... existing tools ...
    # NEW (added from extract script)
    "new_tool_1", "new_tool_2",
}
```

### Bước 3: Nếu có API group mới

Script sẽ hiển thị group mới dạng:
```
/api/new-group: 5 endpoints
```

Thêm dict mới trong bridge:
```python
# ── New Group (5) ──
NEW_GROUP = {
    "action1": "/api/new-group/action1",
    "action2": "/api/new-group/action2",
}
```

Và thêm method gọi:
```python
async def new_group(self, action: str, data: dict = None) -> dict:
    return await self._call_group(self.NEW_GROUP, action, data, "new-group")
```

### Bước 4: Cập nhật `_ALL_GROUPS`

```python
_ALL_GROUPS = {
    # ... existing ...
    "new_group": ("NEW_GROUP", "dict"),
}
```

### Bước 5: Verify

```bash
python scripts/extract_hexstrike_endpoints.py --compare
# Expected: ✅ Tool coverage: 100.0%
```

---

## Script Options

| Flag | Mô tả |
|------|--------|
| `--compare` | So sánh VibeLens bridge vs HexStrike thật |
| `--codegen` | In Python code sẵn sàng paste |
| `--hexstrike-dir PATH` | Chỉ định thư mục hexstrike-ai |
| `--output FILE` | Lưu JSON report tại đường dẫn chỉ định |

---

## Kiến trúc tích hợp

```
┌─────────────────────────────────────────────────┐
│                   VibeLens                       │
│  ┌───────────────┐    ┌──────────────────────┐  │
│  │  MCP Server   │    │   HexStrikeBridge    │  │
│  │  (mcp_server  │───▶│   (security/         │  │
│  │   .py)        │    │    __init__.py)       │  │
│  └───────────────┘    └──────────┬───────────┘  │
│                                  │ HTTP          │
└──────────────────────────────────┼───────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────┐
│              HexStrike AI Server                  │
│  ┌──────────────────────────────────────────────┐│
│  │ hexstrike_server.py (156 API endpoints)      ││
│  │  /api/tools/*        (90 tools)              ││
│  │  /api/intelligence/* (6 endpoints)           ││
│  │  /api/bugbounty/*    (6 workflows)           ││
│  │  /api/ctf/*          (7 endpoints)           ││
│  │  /api/vuln-intel/*   (5 endpoints)           ││
│  │  /api/ai/*           (3 endpoints)           ││
│  │  /api/error-handling/*(7 endpoints)          ││
│  │  /api/process/*      (11 endpoints)          ││
│  │  /api/processes/*    (6 endpoints)           ││
│  │  /api/files/*        (4 endpoints)           ││
│  │  /api/visual/*       (3 endpoints)           ││
│  │  /api/python/*       (2 endpoints)           ││
│  │  /api/cache/*        (2 endpoints)           ││
│  │  /api/payloads/*     (1 endpoint)            ││
│  │  /api/command        (1 endpoint)            ││
│  │  /api/telemetry      (1 endpoint)            ││
│  │  /health             (1 endpoint)            ││
│  └──────────────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────┐│
│  │ hexstrike_mcp.py (148 MCP tools)             ││
│  │  = Client wrapper, gọi server API            ││
│  │  + 90 composite tools (phối hợp nhiều API)   ││
│  └──────────────────────────────────────────────┘│
└──────────────────────────────────────────────────┘
```

---

## Về `hexstrike_mcp.py`

File này là **MCP client** của HexStrike — nó wrap các server API thành MCP tools.

- **148 tools** trong đó ~58 tool map 1:1 tới `/api/tools/*`
- **~90 composite tools** = tổ hợp gọi nhiều API (e.g., `comprehensive_api_audit` gọi `api_fuzzer` + `api_schema_analyzer` + `jwt_analyzer` + `graphql_scanner`)
- VibeLens **KHÔNG cần** duplicate composite tools vì:
  - VibeLens bridge đã có `call_tool()` để gọi bất kỳ tool nào
  - VibeLens bridge đã có `run_command()` để chạy bất kỳ lệnh nào
  - AI agent có thể tự phối hợp nhiều tool calls

**Khi nào cần xem `hexstrike_mcp.py`?**
- Khi muốn biết chính xác **params** nào mỗi tool nhận
- Khi muốn copy logic **composite workflow** sang VibeLens

---

## Windows Compatibility

HexStrike tools chạy trên Linux. Trên Windows:

| Option | Compatibility | Command |
|--------|--------------|---------|
| **WSL** (khuyến nghị) | ~90% | `wsl -d Ubuntu && python hexstrike_server.py` |
| **Docker** (tốt nhất) | 100% | `docker run -p 8888:8888 hexstrike-ai` |
| **Native** | ~15% | Chỉ nuclei.exe + Python tools |

VibeLens chỉ gửi HTTP request → HexStrike server có thể ở bất kỳ đâu.
