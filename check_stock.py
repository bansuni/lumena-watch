# -*- coding: utf-8 -*-
# 루메나 FAN GRANDE 2 "GRANDE 2 [단품] - 실키화이트" 재입고 감시 스크립트
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
PRODUCT_KEYWORDS = ["GRANDE", "단품"]   # "GRANDE 2 [단품]" 매칭, "2PACK"은 제외
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


def is_soldout(text, disabled):
    return disabled or any(norm(m) in norm(text) for m in SOLDOUT_MARKERS)


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


def check_in_stock():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0 Safari/537.36"))
        # 품절 옵션 선택 시 뜰 수 있는 경고창 자동 닫기
        page.on("dialog", lambda d: d.dismiss())
        page.set_default_timeout(30000)
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        selects = page.locator("select[id^='product_option_id']")
        if selects.count() == 0:
            selects = page.locator("select")
        if selects.count() == 0:
            print("[ERROR] 옵션 선택 박스를 찾지 못했습니다. (페이지 구조 변경 가능성)")
            browser.close()
            return None

        # --- 1단계: 제품선택에서 'GRANDE 2 [단품]' 찾기 ---
        first = selects.nth(0)
        first_opts = first.locator("option")
        target_value = None
        target_text = ""
        print("[INFO] *** 제품선택 옵션 목록:")
        for i in range(first_opts.count()):
            t = (first_opts.nth(i).text_content() or "").strip()
            print("    -", t)
            if all(norm(k) in norm(t) for k in PRODUCT_KEYWORDS) and target_value is None:
                target_value = first_opts.nth(i).get_attribute("value")
                target_text = t

        if target_value is None:
            print("[ERROR] 제품선택에서 '단품' 옵션을 찾지 못했습니다.")
            browser.close()
            return None

        parent_soldout = is_soldout(target_text, False)
        print("[INFO] 단품 옵션 = '%s' / 단품 자체 품절? %s"
              % (target_text, parent_soldout))

        # 단품 옵션 선택 시도 (품절이어도 일단 눌러봐서 색상이 뜨는지 확인)
        try:
            first.select_option(value=target_value)
            page.wait_for_timeout(3000)
        except Exception as e:
            print("[WARN] 단품 옵션 선택이 막혔습니다:", e)

        # --- 2단계: 색상선택에서 실키화이트 찾기 ---
        selects = page.locator("select[id^='product_option_id']")
        if selects.count() == 0:
            selects = page.locator("select")

        found_color = False
        color_available = False
        any_color_printed = False
        print("[INFO] *** 색상선택(또는 채워진 옵션) 목록:")
        for s in range(selects.count()):
            opts = selects.nth(s).locator("option")
            for i in range(opts.count()):
                t = (opts.nth(i).text_content() or "").strip()
                disabled = opts.nth(i).get_attribute("disabled") is not None
                if not t or "옵션을 선택" in t or set(t) <= set("- "):
                    continue
                if all(norm(k) in norm(t) for k in PRODUCT_KEYWORDS) or "2pack" in norm(t):
                    continue
                any_color_printed = True
                mark = ""
                if norm(COLOR_KEYWORD) in norm(t):
                    found_color = True
                    if not is_soldout(t, disabled):
                        color_available = True
                        mark = "   <=== 재고 있음!"
                    else:
                        mark = "   (품절)"
                print("    -", t, mark)
        if not any_color_printed:
            print("    (색상 목록이 뜨지 않았습니다 - 단품 품절로 진입 불가 추정)")

        browser.close()

        print("[INFO] 실키화이트발견? %s / 실키화이트구매가능? %s / 단품품절? %s"
              % (found_color, color_available, parent_soldout))

        if found_color and color_available:
            return True
        return False


def main():
    result = check_in_stock()
    if result is None:
        sys.exit(0)

    prev = read_prev_state()
    current = "instock" if result else "soldout"
    print("[INFO] 이전 상태: '%s' / 현재 상태: '%s'" % (prev, current))

    if result and prev != "instock":
        msg = ("[재입고] 루메나 FAN GRANDE 2 [단품] 실키화이트 재입고된 것 같습니다!\n\n"
               "바로 확인하세요:\n" + URL +
               "\n\n구매 후에는 GitHub Actions 탭에서 워크플로우를 Disable 하면 알림이 멈춥니다.")
        send_telegram(msg)
        print("[INFO] 재입고 알림 전송함")

    write_state(current)


if __name__ == "__main__":
    main()
