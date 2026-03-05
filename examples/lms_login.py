"""
VibeLens Demo: Auto Login vào LMS HCMUT (Moodle) qua CAS SSO
=============================================================
Script này tự động:
1. Truy cập trang LMS → redirect tới SSO
2. Lấy form login CAS (bao gồm hidden fields: lt, execution)
3. POST username/password lên SSO
4. Follow redirect chain: SSO → LMS (với CAS ticket) → Dashboard
5. Trả về session đã login (MoodleSession cookie + sesskey)

Tạo ra từ VibeLens Network Capture — 57 requests analyzed! 🔍
"""

import re
import getpass
import httpx
from urllib.parse import urlencode

# ─── Config ───
LMS_BASE = "https://lms.hcmut.edu.vn"
SSO_BASE = "https://sso.hcmut.edu.vn"
CAS_SERVICE = f"{LMS_BASE}/login/index.php?authCAS=CAS"
CAS_LOGIN_URL = f"{SSO_BASE}/cas/login?service={CAS_SERVICE}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def login_lms(username: str, password: str) -> dict:
    """
    Login vào LMS HCMUT qua CAS SSO.
    
    Returns:
        dict với keys:
        - success: bool
        - moodle_session: str (cookie MoodleSession)
        - sesskey: str (Moodle session key cho API calls)
        - cookies: dict (tất cả cookies)
        - user_info: dict (thông tin user nếu có)
        - error: str (nếu lỗi)
    """
    
    # Dùng httpx client với follow_redirects
    client = httpx.Client(
        headers=HEADERS,
        follow_redirects=True,
        timeout=30.0,
        verify=True,
    )
    
    result = {
        "success": False,
        "moodle_session": None,
        "sesskey": None,
        "cookies": {},
        "user_info": {},
        "error": None,
    }
    
    try:
        # ─── Step 1: Truy cập LMS → Redirect tới CAS SSO login page ───
        print("🔑 [1/4] Truy cập CAS SSO login page...")
        
        # Đầu tiên vào LMS để lấy redirect chain
        r1 = client.get(f"{LMS_BASE}/login/index.php?authCAS=CAS")
        
        # Tìm CAS login page (có thể đã redirect)
        cas_page = None
        if "sso.hcmut.edu.vn" in str(r1.url):
            cas_page = r1
        else:
            # Thử truy cập CAS trực tiếp
            cas_page = client.get(CAS_LOGIN_URL)
        
        if cas_page.status_code != 200:
            result["error"] = f"Cannot access CAS login page: HTTP {cas_page.status_code}"
            return result
        
        print(f"   ✅ CAS login page loaded: {cas_page.url}")
        
        # ─── Step 2: Parse form → Lấy hidden fields (lt, execution) ───
        print("📝 [2/4] Parsing login form...")
        html = cas_page.text
        
        # Extract hidden fields
        lt_match = re.search(r'name="lt"\s+value="([^"]+)"', html)
        execution_match = re.search(r'name="execution"\s+value="([^"]+)"', html)
        
        if not lt_match:
            result["error"] = "Cannot find 'lt' (login ticket) in CAS form. Page may have changed."
            return result
        
        lt = lt_match.group(1)
        execution = execution_match.group(1) if execution_match else "e1s1"
        
        print(f"   ✅ Login Ticket: {lt[:20]}...")
        print(f"   ✅ Execution: {execution}")
        
        # ─── Step 3: POST login credentials ───
        print("🔐 [3/4] Submitting login...")
        
        # Form action URL (từ captured request)
        form_action = re.search(r'form[^>]+action="([^"]+)"', html)
        login_url = SSO_BASE + form_action.group(1) if form_action else str(cas_page.url)
        
        login_data = {
            "username": username,
            "password": password,
            "lt": lt,
            "execution": execution,
            "_eventId": "submit",
            "submit": "Login",
        }
        
        r2 = client.post(
            login_url,
            data=login_data,
            headers={
                **HEADERS,
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": SSO_BASE,
                "Referer": str(cas_page.url),
            },
        )
        
        # Check nếu login thất bại
        # Cách đúng: kiểm tra URL — nếu vẫn ở SSO login page thì sai credentials
        final_url = str(r2.url)
        
        if "sso.hcmut.edu.vn/cas/login" in final_url:
            # Vẫn ở trang CAS login → sai credentials
            if "class=\"errors\"" in r2.text or "class=\"error\"" in r2.text:
                error_match = re.search(r'class="errors?"[^>]*>(.*?)</div>', r2.text, re.S)
                error_msg = error_match.group(1).strip() if error_match else "Login failed"
                result["error"] = f"❌ {error_msg}"
            else:
                result["error"] = "❌ Sai tên đăng nhập hoặc mật khẩu!"
            return result
        
        print(f"   ✅ Redirected to: {r2.url}")
        
        # ─── Step 4: Extract session info ───
        print("🎉 [4/4] Extracting session...")
        
        # Lấy MoodleSession cookie
        all_cookies = dict(client.cookies)
        moodle_session = all_cookies.get("MoodleSession")
        
        if not moodle_session:
            # Thử lấy từ redirect history
            for resp in r2.history:
                for name, value in resp.cookies.items():
                    if name == "MoodleSession":
                        moodle_session = value
                        break
        
        # Lấy sesskey từ page HTML
        sesskey = None
        page_html = r2.text
        sesskey_match = re.search(r'"sesskey"\s*:\s*"([^"]+)"', page_html)
        if not sesskey_match:
            sesskey_match = re.search(r'sesskey=([a-zA-Z0-9]+)', page_html)
        if sesskey_match:
            sesskey = sesskey_match.group(1)
        
        # Lấy user info
        user_info = {}
        name_match = re.search(r'<span class="usertext[^"]*">([^<]+)</span>', page_html)
        if name_match:
            user_info["name"] = name_match.group(1).strip()
        
        userid_match = re.search(r'/user/profile\.php\?id=(\d+)', page_html)
        if userid_match:
            user_info["user_id"] = userid_match.group(1)
        
        result["success"] = True
        result["moodle_session"] = moodle_session
        result["sesskey"] = sesskey
        result["cookies"] = all_cookies
        result["user_info"] = user_info
        
        return result
        
    except httpx.ConnectError as e:
        result["error"] = f"Không thể kết nối tới server: {e}"
        return result
    except Exception as e:
        result["error"] = f"Lỗi: {str(e)}"
        return result
    finally:
        client.close()


def demo_api_call(session_cookie: str, sesskey: str):
    """Demo: Gọi Moodle API với session đã login"""
    print("\n📡 Demo: Gọi Moodle API...")
    
    client = httpx.Client(
        headers=HEADERS,
        cookies={"MoodleSession": session_cookie},
        timeout=15.0,
    )
    
    try:
        # Lấy danh sách khóa học
        r = client.post(
            f"{LMS_BASE}/lib/ajax/service.php?sesskey={sesskey}&info=core_course_get_enrolled_courses_by_timeline_classification",
            json=[{
                "index": 0,
                "methodname": "core_course_get_enrolled_courses_by_timeline_classification",
                "args": {
                    "offset": 0,
                    "limit": 10,
                    "classification": "all",
                    "sort": "fullname",
                }
            }],
        )
        
        if r.status_code == 200:
            data = r.json()
            if data and not data[0].get("error"):
                courses = data[0].get("data", {}).get("courses", [])
                print(f"\n📚 Danh sách khóa học ({len(courses)} môn):")
                for i, course in enumerate(courses[:10], 1):
                    print(f"   {i}. {course.get('fullname', 'N/A')}")
                return courses
            else:
                print(f"   ⚠️ API error: {data}")
        else:
            print(f"   ⚠️ HTTP {r.status_code}")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    finally:
        client.close()
    
    return None


# ─── Main ───
if __name__ == "__main__":
    print("=" * 60)
    print("  🔍 VibeLens Demo: LMS HCMUT Auto Login")
    print("  📡 Generated from 57 captured network requests!")
    print("=" * 60)
    print()
    
    username = input("👤 Username (MSSV): ").strip()
    password = getpass.getpass("🔑 Password: ").strip()
    
    if not username or not password:
        print("❌ Username và password không được để trống!")
        exit(1)
    
    print()
    result = login_lms(username, password)
    
    if result["success"]:
        print()
        print("=" * 60)
        print("  ✅ LOGIN THÀNH CÔNG!")
        print("=" * 60)
        print(f"  👤 User: {result['user_info'].get('name', 'N/A')}")
        print(f"  🆔 User ID: {result['user_info'].get('user_id', 'N/A')}")
        print(f"  🍪 MoodleSession: {result['moodle_session'][:30]}...")
        print(f"  🔑 Sesskey: {result['sesskey']}")
        print(f"  🌐 Total cookies: {len(result['cookies'])}")
        print()
        
        # Demo API call
        choice = input("📡 Thử gọi API lấy danh sách khóa học? (y/n): ").strip().lower()
        if choice == 'y':
            demo_api_call(result["moodle_session"], result["sesskey"])
    else:
        print()
        print(f"  ❌ LOGIN THẤT BẠI: {result['error']}")
    
    print()
