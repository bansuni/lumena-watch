# -*- coding: utf-8 -*-
# 사람인 '변리사' 구인공고 새 글 감시 (회사명에 특허법인/특허사무소 들어가면 제외)
#  + 상세페이지(모바일) 본문 읽어 Gemini 요약 + 텔레그램
import os, re, sys, json, time, urllib.request, urllib.parse
from bs4 import BeautifulSoup

SEARCH_URL = ("https://www.saramin.co.kr/zf_user/search?searchType=search"
              "&searchword=%EB%B3%80%EB%A6%AC%EC%82%AC"
              "&recruitPageCount=100&recruitSort=relation")
MOBILE_VIEW = "https://m.saramin.co.kr/job-search/view?rec_idx=%s"
SEEN_FILE = "seen_saramin.txt"
# ★ 회사명(corp_name)에 아래 단어가 들어가면 제외 (특허사무소 안 감) ★
EXCLUDE_COMPANY = ["특허법인", "특허법률사무소", "특허사무소"]
# ★ 제목(title)에 이 단어가 들어간 공고만 알림 ★
TITLE_MUST_INCLUDE = "변리사"
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"]

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GKEY = os.environ.get("GEMINI_API_KEY", "")
PC_HDRS = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
           "Accept-Language": "ko-KR,ko;q=0.9"}
M_HDRS = {"User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                         "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"),
          "Accept-Language": "ko-KR,ko;q=0.9"}


def fetch(url, hdrs):
    return urllib.request.urlopen(urllib.request.Request(url, headers=hdrs),
                                  timeout=30).read().decode("utf-8", "ignore")


def tg(text):
    if not TOKEN or not CHAT_ID:
        print("[WARN] 텔레그램 미설정 - 전송 생략"); return
    url = "https://api.telegram.org/bot%s/sendMessage" % TOKEN
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=20) as r:
            print("[INFO] 텔레그램", r.status)
    except Exception as e:
        print("[ERROR] 텔레그램 실패:", e)


def summarize(text):
    if not GKEY:
        return None
    prompt = ("다음 변리사 구인공고 상세내용을 한국어로 3~4줄로 요약하라. "
              "기술분야, 담당업무, 자격·경력요건, 근무지역, 우대사항/연봉(있으면) 위주로. 군더더기 없이.\n\n"
              + text[:4000])
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 0.2}}).encode()
    for m in GEMINI_MODELS:
        url = ("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s"
               % (m, GKEY))
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                d = json.loads(r.read())
                return d["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            print("[WARN] Gemini(%s) 실패: %s" % (m, str(e)[:80]))
    return None


def detail_text(rec_idx):
    """모바일 상세페이지에서 본문 추출 (자격요건/우대사항 등)"""
    try:
        html = fetch(MOBILE_VIEW % rec_idx, M_HDRS)
        soup = BeautifulSoup(html, "html.parser")
        for s in soup(["script", "style"]):
            s.extract()
        body = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
        start = body.find("자격요건")
        if start < 0:
            start = body.find("모집")
        return body[start:start + 2800] if start >= 0 else body[:2800]
    except Exception as e:
        print("[WARN] 상세 fetch 실패:", str(e)[:80])
        return ""


def read_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(x.strip() for x in f if x.strip())
    except FileNotFoundError:
        return None


def write_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(list(seen)[-1500:]))


def parse_list():
    soup = BeautifulSoup(fetch(SEARCH_URL, PC_HDRS), "html.parser")
    out = []
    for it in soup.select(".item_recruit"):
        idx = it.get("value")
        if not idx:
            continue
        corp_el = it.select_one(".corp_name a")
        corp = corp_el.get_text(strip=True) if corp_el else ""
        job = it.select_one(".job_tit a")
        if not job:
            continue
        title = job.get("title") or job.get_text(strip=True)
        href = job.get("href") or ""
        if href.startswith("/"):
            href = "https://www.saramin.co.kr" + href
        cond = it.select_one(".job_condition")
        cond = re.sub(r"\s+", " ", cond.get_text(" / ", strip=True)) if cond else ""
        out.append({"id": idx, "corp": corp, "title": title, "cond": cond, "url": href})
    return out


def excluded(corp):
    return any(x in corp for x in EXCLUDE_COMPANY)


def main():
    try:
        items = parse_list()
    except Exception as e:
        print("[ERROR] 사람인 접근 실패:", str(e)[:120]); sys.exit(0)
    print("[INFO] 검색결과 %d건" % len(items))
    if not items:
        print("[ERROR] 결과 0건 - 구조 변경/차단 가능성"); sys.exit(0)

    kept = [it for it in items
            if not excluded(it["corp"]) and TITLE_MUST_INCLUDE in it["title"]]
    print("[INFO] 제목에 '%s' 포함 + 특허법인/특허사무소 제외 후 %d건"
          % (TITLE_MUST_INCLUDE, len(kept)))

    seen = read_seen()
    first_run = seen is None
    if first_run:
        seen = set()

    new_items = [it for it in kept if it["id"] not in seen]
    print("[INFO] 신규 %d건 / 첫실행=%s" % (len(new_items), first_run))

    if first_run:
        for it in kept:
            seen.add(it["id"])
        write_seen(seen)
        tg("[감시 시작] 사람인 '변리사' 구인공고 감시를 시작했습니다. "
           "제목에 '변리사'가 들어간 공고만, 회사명에 특허법인/특허법률사무소/특허사무소가 "
           "들어가면 제외하고, 상세내용을 요약해 보내드립니다. (현재 %d건은 기존 글로 처리)" % len(kept))
        print("[INFO] 첫 실행 베이스라인 기록"); return

    for it in reversed(new_items):
        print("[INFO] 신규:", it["id"], it["corp"], it["title"])
        dt = detail_text(it["id"])
        src = dt if len(dt) > 60 else ("제목: %s / 조건: %s" % (it["title"], it["cond"]))
        summary = summarize(src) or ("(요약 실패) " + it["cond"])
        msg = ("[사람인 새 구인공고]\n\n제목: %s\n회사: %s\n조건: %s\n\n[요약]\n%s\n\n링크: %s"
               % (it["title"], it["corp"], it["cond"], summary, it["url"]))
        tg(msg)
        seen.add(it["id"])
        time.sleep(1)

    write_seen(seen)
    print("[INFO] 완료")


if __name__ == "__main__":
    main()
