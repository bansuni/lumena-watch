# -*- coding: utf-8 -*-
# 루메나 FAN GRANDE 2 "GRAND2 실키화이트" 재입고 감시 스크립트
# (코드를 이해할 필요 없습니다. 그대로 두시면 됩니다.)

import os
import sys
from playwright.sync_api import sync_playwright

# ===== 감시 대상 설정 =====
URL = ("https://lumena.co.kr/product/"
       "%EB%A3%A8%EB%A9%94%EB%82%98-%EB%AC%B4%EC%86%8C%EC%9D%8C-bldc-"
       "%EC%9C%A0%EC%84%A0-%EC%97%90%EC%96%B4-%EC%8D%A8%ED%81%98%EB%A0%88"
       "%EC%9D%B4%ED%84%B0-fan-grande-2/473/category/42/display/1/")

# 1단계 '제품선택'에서 고를 옵션 (아래 단어가 모두 들어간 옵션을 고름)
PRODUCT_KEYWORDS = ["GRAND2", "단품"]
# 2단계 '색상선택'에서 감시할 색상
COLOR_KEYWORD = "실키화이트"
# 품절로 간주할 표시들
SOLDOUT_MARKERS = ["품절", "일시품절", "soldout", "sold out", "sold-out"]
# ==========================

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_FILE = "state.txt"


def norm(s):
    return (s or "").replace(" ", "").lower()


def send_telegram(text):
    import urllib.request
    import urllib.parse
    if not TOKEN or not CHAT_ID:
        print("[WARN] 텔레그램 토큰/챗ID가 없어 알림을 보낼 수 없습니다.")
        return
    url = "https://api.telegram.org/bot%s/sendMessage" % TOKEN
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=20) as r:
            print("[INFO] 텔레그램 응답 코드:", r.status)
    except Exception as e:
        print("[ERROR] 텔레그램 전송 실패:", e)


def read_prev_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def write_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(state)


def option_texts(select_locator):
    """select 안의 모든 option 텍스트 + 비활성화 여부 리스트로 반환"""
    out = []
    opts = select_locator.locator("option")
    for i in range(opts.count()):
        t = (opts.nth(i).text_content() or "").strip()
        disabled = opts.nth(i).get_attribute("disabled") is not None
        out.append((t, disabled))
    return out


def check_in_stock():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"))
        page.set_default_timeout(30000)
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # 카페24 옵션 선택 박스 찾기
        selects = page.locator("select[id^='product_option_id']")
        if selects.count() == 0:
            selects = page.locator("select")
        if selects.count() == 0:
            print("[ERROR] 옵션 선택 박스를 찾지 못했습니다. (페이지 구조 변경 가능성)")
            browser.close()
            return None

        # --- 1단계: 제품선택에서 GRAND2 단품 고르기 ---
        first = selects.nth(0)
        first_opts = first.locator("option")
        target_value = None
        target_text = ""
        for i in range(first_opts.count()):
            t = first_opts.nth(i).text_content() or ""
            nt = norm(t)
            if all(norm(k) in nt for k in PRODUCT_KEYWORDS):
                target_value = first_opts.nth(i).get_attribute("value")
                target_text = t.strip()
                break

        if target_value is None:
            print("[ERROR] 제품선택에서 'GRAND2 단품' 옵션을 찾지 못했습니다.")
            print("  ▼ 현재 제품선택 옵션 목록:")
            for i in range(first_opts.count()):
                print("    -", (first_opts.nth(i).text_content() or "").strip())
            browser.close()
            return None

        print("[INFO] 제품선택 ->", target_text)
        first.select_option(value=target_value)
        page.wait_for_timeout(3000)  # 색상선택이 채워질 시간

        # --- 2단계: 색상선택(또는 채워진 모든 select)에서 실키화이트 찾기 ---
        selects = page.locator("select[id^='product_option_id']")
        if selects.count() == 0:
            selects = page.locator("select")

        found_color = False
        in_stock = False
        print("[INFO] ▼ 현재 색상/옵션 목록:")
        for s in range(selects.count()):
            for (t, disabled) in option_texts(selects.nth(s)):
                if not t:
                    continue
                nt = norm(t)
                mark = ""
                if norm(COLOR_KEYWORD) in nt:
                    found_color = True
                    is_soldout = disabled or any(norm(m) in nt for m in SOLDOUT_MARKERS)
                    if not is_soldout:
                        in_stock = True
                        mark = "   <=== 재고 있음!"
                    else:
                        mark = "   (품절)"
                print("    -", t, mark)

        browser.close()

        if not found_color:
            print("[INFO] '%s' 색상이 목록에 아예 없음 -> 품절로 판단" % COLOR_KEYWORD)
            return False
        return in_stock


def main():
    result = check_in_stock()
    if result is None:
        # 페이지 구조 문제. 상태를 건드리지 않고 종료(다음 실행에서 재시도).
        sys.exit(0)

    prev = read_prev_state()
    current = "instock" if result else "soldout"
    print("[INFO] 이전 상태: '%s' / 현재 상태: '%s'" % (prev, current))

    if result and prev != "instock":
        msg = ("🎉 루메나 FAN GRANDE 2 'GRAND2 실키화이트' 재입고된 것 같습니다!\n\n"
               "바로 확인하세요:\n" + URL +
               "\n\n구매 후에는 GitHub의 Actions 탭에서 워크플로우를 Disable 하면 "
               "알림이 멈춥니다.")
        send_telegram(msg)
        print("[INFO] 재입고 알림 전송함")

    write_state(current)


if __name__ == "__main__":
    main()
