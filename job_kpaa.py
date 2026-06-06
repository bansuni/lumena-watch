# -*- coding: utf-8 -*-
# 변리사회(KPAA) 구인공고 새 글 감시 + Gemini 요약 + 텔레그램 알림
import os, re, sys, json, time, urllib.request
from playwright.sync_api import sync_playwright

LIST_URL = "https://www.kpaa.or.kr/kpaa/info/readJobOfferList.do?srch_job_type=4"
DETAIL_FMT = "https://www.kpaa.or.kr/kpaa/info/readJobOfferView.do?seq=%s&srch_job_type=4"
SEEN_FILE = "seen_kpaa.txt"
SOURCE = "변리사회"
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"]

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GKEY = os.environ.get("GEMINI_API_KEY", "")

LABELS = ["사무소명", "제목", "마감일", "고용형태", "채용직급", "작성일", "조회수", "번호"]


def clean(t):
    t = (t or "")
    for lb in LABELS:
        t = t.replace(lb, " ")
    return re.sub(r"\s+", " ", t).strip()


def tg(text):
    if not TOKEN or not CHAT_ID:
        print("[WARN] 텔레그램 미설정 - 전송 생략"); return
    url = "https://api.telegram.org/bot%s/sendMessage" % TOKEN
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text,
                                   "disable_web_page_preview": "false"}).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=20) as r:
            print("[INFO] 텔레그램", r.status)
    except Exception as e:
        print("[ERROR] 텔레그램 실패:", e)


import urllib.parse  # noqa


def summarize(text):
    if not GKEY:
        return None
    prompt = ("다음은 변리사 구인공고 내용이다. 한국어로 핵심만 3~4줄로 요약하라. "
              "분야(기술분야), 경력요건(신입/경력 및 연차), 근무지역, 마감일/고용형태, "
              "특이사항(연봉·우대 등)이 있으면 포함하라. 군더더기 없이.\n\n" + text[:4000])
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 0.2}}).encode()
    for m in GEMINI_MODELS:
        url = ("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s"
               % (m, GKEY))
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                d = json.loads(r.read())
                return d["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            print("[WARN] Gemini(%s) 실패: %s" % (m, str(e)[:80]))
            continue
    return None


def read_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(x.strip() for x in f if x.strip())
    except FileNotFoundError:
        return None  # 첫 실행


def write_seen(seen):
    seen = list(seen)[-800:]  # 최근 800개만 유지
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(seen))


def get_list():
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"))
        pg.set_default_timeout(40000)
        pg.goto(LIST_URL, wait_until="networkidle")
        pg.wait_for_timeout(2000)
        rows = pg.locator("table tbody tr")
        for i in range(rows.count()):
            r = rows.nth(i)
            oc = r.get_attribute("onclick") or ""
            mm = re.search(r"fnGoView\('(\d+)'\)", oc)
            if not mm:
                continue
            seq = mm.group(1)
            tds = r.locator("td")
            if tds.count() < 8:
                continue
            office = clean(tds.nth(1).text_content())
            # 제목은 a.text-truncate 가 가장 깔끔
            try:
                title = (r.locator("a.text-truncate").first.text_content() or "").strip()
            except Exception:
                title = clean(tds.nth(3).text_content())
            date = clean(tds.nth(7).text_content())
            out.append({"seq": seq, "office": office, "title": title,
                        "date": date, "url": DETAIL_FMT % seq})
        b.close()
    return out


def get_detail_text(url):
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"))
        pg.set_default_timeout(40000)
        pg.goto(url, wait_until="networkidle")
        pg.wait_for_timeout(1200)
        body = pg.locator("body").inner_text()
        b.close()
    # 본문 핵심부만 슬라이스 (사무소 정보 ~ 이후)
    for marker in ["사무소 정보", "사무소명", "모집요강"]:
        idx = body.find(marker)
        if idx >= 0:
            return body[idx:idx + 3000]
    return body[:3000]


def main():
    postings = get_list()
    print("[INFO] 목록에서 %d건 수집" % len(postings))
    if not postings:
        print("[ERROR] 목록을 못 읽음 - 구조 변경 가능성")
        sys.exit(0)

    seen = read_seen()
    first_run = seen is None
    if first_run:
        seen = set()

    current_ids = [pp["seq"] for pp in postings]
    new_items = [pp for pp in postings if pp["seq"] not in seen]
    print("[INFO] 신규 %d건 / 첫실행=%s" % (len(new_items), first_run))

    if first_run:
        # 첫 실행: 기존 글 전부 '본 것'으로 기록만 (도배 방지)
        for pp in postings:
            seen.add(pp["seq"])
        write_seen(seen)
        tg("[감시 시작] 변리사회 구인공고 감시를 시작했습니다. "
           "지금부터 새로 올라오는 공고를 요약해서 보내드립니다. "
           "(현재 게시판에 있는 %d건은 기존 글로 처리)" % len(postings))
        print("[INFO] 첫 실행 베이스라인 기록 완료")
        return

    # 신규 글 처리 (오래된 것부터 알림 가도록 역순)
    for pp in reversed(new_items):
        print("[INFO] 신규:", pp["seq"], pp["title"])
        detail = get_detail_text(pp["url"])
        summary = summarize(detail)
        if not summary:
            # 요약 실패 시 본문 앞부분으로 대체
            summary = "(요약 생성 실패) " + re.sub(r"\s+", " ", detail)[:200]
        msg = ("[변리사회 새 구인공고]\n\n"
               "제목: %s\n사무소: %s\n등록일: %s\n\n[요약]\n%s\n\n링크: %s"
               % (pp["title"], pp["office"], pp["date"], summary, pp["url"]))
        tg(msg)
        seen.add(pp["seq"])
        time.sleep(1)

    write_seen(seen)
    print("[INFO] 완료")


if __name__ == "__main__":
    main()
