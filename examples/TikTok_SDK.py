from scrapling import Fetcher
import json
import urllib.parse
from typing import Optional, Dict, Any

class TikTok_SDK:
    """
    TikTok SDK được sinh ra tự động từ VibeLens (Browser Traffic)
    Sử dụng Scrapling để kế thừa TLS fingerprint và bypass Cloudflare.
    """

    def __init__(self):
        # Giả mạo Chrome 128 (khớp với fingerprint lúc capture)
        self.fetcher = Fetcher(impersonate='chrome128')
        
        # Base headers - Trích xuất từ traffic
        self.base_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Referer": "https://www.tiktok.com/foryou?lang=vi-VN",
            "sec-ch-ua": "\"Chromium\";v=\"128\", \"Not;A=Brand\";v=\"24\", \"Google Chrome\";v=\"128\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\""
        }
        
        # Quan trọng: Những thông số định danh/thiết bị cần có trong Query Parameters
        self.base_params = {
            "aid": "1988",
            "app_language": "vi-VN",
            "app_name": "tiktok_web",
            "browser_language": "en-US",
            "browser_name": "Mozilla",
            "browser_online": "true",
            "browser_platform": "Win32",
            "browser_version": "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "channel": "tiktok_web",
            "cookie_enabled": "true",
            "device_platform": "web_pc",
            "os": "windows",
            "priority_region": "VN",
            "region": "VN",
            # Các thông số tracking bên dưới nên được update thường xuyên nếu có thể
            "device_id": "7445293558799992328", 
            "odinId": "7470178129845552134",
        }
        
        # ⚠️ Auth Headers & Cookies
        # Cookie _ttp, sessionid, msToken và csrf-token là linh hồn để bypass
        # Bạn có thể trích xuất động các token này nếu VibeLens cung cấp chức năng auto-export cookie.
        self.cookies = {
            "sessionid": "ba141b01406cd7b6deaeb9abf03f2824", # Bắt buộc phải có để thao tác Auth (Like, Follow)
            "msToken": "Av_I5MeoM4Xr1RaiC-DNb8xwTmQLpXJt-pyJ9sMeTEE_azFE5_Hh1zBmfhkGMnWLc5EvrTSB3VrQuo7QbbhPVL6DfY2dQSfCeLvQ318YwfORt7YZhKHyViMeGdovdY_ieEDO2-ZiKwvQkWBc3whjEuBHww==",
            "tt-csrf-token": "rNxvjvuT-wYsETGohF4DfeBct55xRmeEp-qo",
            "_ttp": "2dDGxlrsIGp7SuNxe9wTMle5D4I",
        }

    def _build_url(self, endpoint: str, extra_params: Dict[str, str] = None) -> str:
        """Xây dựng URL hoàn chỉnh kèm các base query params"""
        url = f"https://www.tiktok.com{endpoint}"
        params = self.base_params.copy()
        if extra_params:
            params.update(extra_params)
        query_string = urllib.parse.urlencode(params)
        return f"{url}?{query_string}"

    def like_post(self, aweme_id: str) -> bool:
        """Thả tim một Video TikTok"""
        print(f"❤️ Đang thả tim video ID: {aweme_id}")
        endpoint = "/api/commit/item/digg/"
        params = {
            "aweme_id": aweme_id,
            "type": "1" # 1 là like, 0 là unlike
        }
        url = self._build_url(endpoint, params)
        
        headers = self.base_headers.copy()
        headers["content-type"] = "application/x-www-form-urlencoded"
        # Bắt buộc phải có token chống CSRF
        headers["tt-csrf-token"] = "rNxvjvuT-wYsETGohF4DfeBct55xRmeEp-qo"
        
        res = self.fetcher.post(url, headers=headers, cookies=self.cookies)
        
        if res.status == 200:
            if not res.text.strip():
                print(f"⚠️ Trả về content rỗng từ {url}")
                return False
            try:
                data = res.json()
                if data.get("status_code") == 0:
                    print("✅ Thả tim thành công!")
                    return True
            except Exception as e:
                print(f"❌ Lỗi parse JSON: {e}")
                print(f"📝 Raw Content: {res.text[:200]}")
        print(f"❌ Thả tim thất bại (Status: {res.status})")
        return False

    def follow_user(self, target_user_id: str) -> bool:
        """Theo dõi một User TikTok"""
        print(f"👥 Đang theo dõi user ID: {target_user_id}")
        endpoint = "/api/commit/follow/user/"
        params = {
            "user_id": target_user_id,
            "type": "1" # 1 = Follow, 0 = Unfollow
        }
        url = self._build_url(endpoint, params)
        
        headers = self.base_headers.copy()
        headers["content-type"] = "application/x-www-form-urlencoded"
        headers["tt-csrf-token"] = "rNxvjvuT-wYsETGohF4DfeBct55xRmeEp-qo"
        
        res = self.fetcher.post(url, headers=headers, cookies=self.cookies)
        
        if res.status == 200:
            data = res.json()
            if data.get("status_code") == 0:
                print("✅ Follow thành công!")
                return True
        print(f"❌ Follow thất bại (Status: {res.status})")
        return False

    def get_feed(self, count: int = 10) -> Optional[Any]:
        """Lấy danh sách video trên feed"""
        print(f"📺 Đang lướt feed để lấy {count} video...")
        endpoint = "/api/item_list/"
        params = {
            "count": str(count),
            "id": "1",
            "type": "5",
            "minCursor": "0",
            "maxCursor": "0",
            "pullType": "1"
        }
        url = self._build_url(endpoint, params)
        
        res = self.fetcher.get(url, headers=self.base_headers, cookies=self.cookies)
        
        if res.status == 200:
            if not res.text.strip():
                print(f"⚠️ Trả về content rỗng từ {url}")
                return None
            try:
                data = res.json()
                items = data.get("itemList", [])
                print(f"✅ Lấy thành công {len(items)} video từ feed!")
                return items
            except Exception as e:
                print(f"❌ Lỗi parse JSON: {e}")
                return None
        print(f"❌ Lỗi lấy feed (Status: {res.status})")
        return None

if __name__ == "__main__":
    sdk = TikTok_SDK()
    
    # Test các hàm
    # Lưu ý: Các ID dưới đây chỉ là dự kiến, bạn cần trích xuất trực tiếp trên TikTok.
    sdk.get_feed(count=5)
    
    # ID video vừa tương tác trong Payload (7595085611594157330)
    sdk.like_post(aweme_id="7595085611594157330") 
    
    # Cần thay target_user_id thành ID thật của một kênh TikTok
    # sdk.follow_user(target_user_id="1234567890123456789")
