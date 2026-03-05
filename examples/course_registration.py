"""Course registration example - Automate course enrollment"""

import asyncio

from vibeengine import Browser, Agent
from vibeengine.llm import ChatOpenAI


async def main():
    """Example: Automate course registration"""

    # Configuration
    university_url = "https://dangky.hust.edu.vn"  # Example URL
    course_name = "Công nghệ phần mềm"
    course_class = "2"

    task = f"""
    1. Truy cập trang đăng ký môn học: {university_url}
    2. Đăng nhập với username và password (nếu cần)
    3. Tìm môn học '{course_name}' lớp '{course_class}'
    4. Nhấn nút đăng ký
    5. Xác nhận đăng ký thành công
    """

    agent = Agent(
        task=task,
        llm=ChatOpenAI(model="gpt-4"),
        browser=Browser(headless=False),
        max_steps=20,
    )

    print("Starting course registration automation...")
    history = await agent.run()

    print(f"\n=== Results ===")
    print(f"Steps: {len(history.actions)}")
    print(f"URLs visited: {history.urls}")
    print(f"Errors: {[e for e in history.errors if e]}")


if __name__ == "__main__":
    asyncio.run(main())
