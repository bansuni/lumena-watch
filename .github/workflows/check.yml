# -*- coding: utf-8 -*-
# 루메나 FAN GRANDE 2 "GRANDE 2 [단품] - 실키화이트" 재입고 감시
#  + 재입고 후 재고 유지 동안 24시간마다 리마인더
import os
import sys
import time
from playwright.sync_api import sync_playwright

URL = ("https://lumena.co.kr/product/"
       "%EB%A3%A8%EB%A9%94%EB%82%98-%EB%AC%B4%EC%86%8C%EC%9D%8C-bldc-"
       "%EC%9C%A0%EC%84%A0-%EC%97%90%EC%96%B4-%EC%8D%A8%ED%81%98%EB%A0%88"
       "%EC%9D%B4%ED%84%B0-fan-grande-2/473/category/42/display/1/")

PRODUCT_KEYWORDS = ["GRANDE", "단품"]
COLOR_KEYWORD = "실키화이트"
SOLDOUT_MARKERS = ["품절", "일시품절", "soldout", "sold out", "sold-out"]
REMINDER_HOURS = 24            # ★ 재입고 후 재고 있는 동안 이 시간마다 리마인더 (48로 바꾸면 이틀)
STATE_FILE = "state.txt"

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def norm(s):
    return (s or "").replace(" ", "").lower()


def is_soldout(text, disabled):
    return disabled or any(norm(m) in norm(text) for m in SOLDOUT_MARKERS)


def send_telegram(text):
    import urllib.request
    import urllib.parse
    if not TOKEN or not CHAT_ID:
        print("[WARN] 텔레그램 미설정 - 전송 생략"); return
    url = "https://api.telegram.org/bot%s/sendMessage" % TOKEN
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=20) as r:
            print("[INFO] 텔레그램", r.status)
    except Exception as e:
        print("[ERROR] 텔레그램 실패:", e)


def read_state():
    # 반환: (status, last_notify_epoch)
    try:
        raw = open(STATE_FILE, "r", encoding="utf-8").read().strip()
    except FileNotFoundError:
        return ("", 0)
    parts = raw.split("|")
    status = parts[0]
    ts = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return (status, ts)


def write_state(status, ts):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write("%s|%d" % (status, ts))


def check_in_stock():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"))
        page.on("dialog", lambda d: d.dismiss())
        page.set_default_timeout(30000)
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        selects = page.locator("select[id^='product_option_id']")
        if selects.count() == 0:
            selects = page.locator("select")
        if selects.count() == 0:
            print("[ERROR] 옵션 박스 못 찾음"); browser.close(); return None

        first = selects.nth(0)
        first_opts = first.locator("option")
        target_value = None
        target_text = ""
        for i in range(first_opts.count()):
            t = (first_opts.nth(i).text_content() or "").strip()
            if all(norm(k) in norm(t) for k in PRODUCT_KEYWORDS) and target_value is None:
                target_value = first_opts.nth(i).get_attribute("value")
                target_text = t
        if target_value is None:
            print("[ERROR] '단품' 옵션 못 찾음"); browser.close(); return None
        print("[INFO] 단품 옵션 =", target_text)
        try:
            first.select_option(value=target_value)
            page.wait_for_timeout(3000)
        except Exception as e:
            print("[WARN] 단품 선택 막힘:", e)

        selects = page.locator("select[id^='product_option_id']")
        if selects.count() == 0:
            selects = page.locator("select")
        found_color = False
        color_available = False
        for s in range(selects.count()):
            opts = selects.nth(s).locator("option")
            for i in range(opts.count()):
                t = (opts.nth(i).text_content() or "").strip()
                disabled = opts.nth(i).get_attribute("disabled") is not None
                if not t or "옵션을 선택" in t or set(t) <= set("- "):
                    continue
                if all(norm(k) in norm(t) for k in PRODUCT_KEYWORDS) or "2pack" in norm(t):
                    continue
                if norm(COLOR_KEYWORD) in norm(t):
                    found_color = True
                    mark = "  (품절)"
                    if not is_soldout(t, disabled):
                        color_available = True
                        mark = "  <=== 재고 있음!"
                    print("    -", t, mark)
        browser.close()
        return bool(found_color and color_available)


def main():
    result = check_in_stock()

    # 수동 실행(Run workflow) 시 '작동 확인 + 현재 상태' 메시지
    if os.environ.get("GITHUB_EVENT_NAME", "") == "workflow_dispatch":
        if result is None:
            send_telegram("[감시 작동 확인] 루메나 실키화이트 감시는 실행됐으나 "
                          "페이지 옵션을 못 읽었습니다. 로그 확인이 필요할 수 있어요.")
        else:
            status_txt = "재고 있음 (지금 구매 가능)" if result else "품절"
            send_telegram("[감시 작동 확인] 루메나 FAN GRANDE 2 [단품] 실키화이트 "
                          "감시가 정상 작동 중입니다.\n현재 상태: %s\n"
                          "재입고되면 알려드리고, 재고가 유지되면 하루 한 번 리마인더도 보냅니다."
                          % status_txt)

    if result is None:
        sys.exit(0)

    prev_status, last_notify = read_state()
    now = int(time.time())
    link = "\n\n" + URL + "\n\n(구매 후엔 GitHub Actions 탭에서 이 워크플로우를 Disable 하면 알림이 멈춥니다.)"

    if result:  # 재고 있음
        if prev_status != "instock":
            send_telegram("[재입고] 루메나 FAN GRANDE 2 [단품] 실키화이트 재입고된 것 같습니다!" + link)
            print("[INFO] 재입고 최초 알림")
            write_state("instock", now)
        else:
            elapsed_h = (now - last_notify) / 3600.0
            print("[INFO] 재고 유지중 / 마지막 알림 후 %.1f시간" % elapsed_h)
            if now - last_notify >= REMINDER_HOURS * 3600:
                send_telegram("[리마인더] 아직 구매 안 하셨나요? 루메나 실키화이트 여전히 재고 있습니다." + link)
                print("[INFO] 리마인더 전송")
                write_state("instock", now)
            else:
                write_state("instock", last_notify)
    else:       # 품절
        if prev_status == "instock":
            print("[INFO] 다시 품절됨")
        write_state("soldout", 0)


if __name__ == "__main__":
    main()
