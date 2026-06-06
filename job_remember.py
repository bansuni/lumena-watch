# -*- coding: utf-8 -*-
# 리멤버 커리어 '변리사' 구인공고 감시 (공고에 '변리사' 정확히 포함된 것만)
#  + 본문 Gemini 요약 + 텔레그램. 로그인 불필요(공개 API 사용).
import os, re, sys, json, time, uuid, random, urllib.request, urllib.parse

API = "https://career-api.rememberapp.co.kr/job_postings/search"
DETAIL_FMT = "https://career.rememberapp.co.kr/job/postings/%s"
SEEN_FILE = "seen_remember.txt"
KEYWORD = "변리사"          # 검색어
MUST_INCLUDE = "변리사"     # 공고에 정확히 포함돼야 하는 단어
PAGES = 3                   # 페이지당 50건 -> 150건(약 3주치) 확인
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"]

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GKEY = os.environ.get("GEMINI_API_KEY", "")
HDRS = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0",
        "Origin": "https://career.rememberapp.co.kr",
        "Referer": "https://career.rememberapp.co.kr/"}

# 공고에 '변리사' 포함 여부를 볼 필드들
TEXT_FIELDS = ["title", "introduction", "job_description", "qualifications",
               "preferred_qualifications", "job_role"]


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
    prompt = ("다음 변리사 구인공고 내용을 한국어로 3~4줄로 요약하라. "
              "기술/직무분야, 담당업무, 자격·경력요건, 근무지역, 연봉/우대(있으면) 위주로. 군더더기 없이.\n\n"
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


def call_api(page):
    payload = {"search": {"include_applied_job_posting": False, "leader_position": False,
                          "organization_type": "all", "application_type": "all",
                          "keywords": [KEYWORD], "min_salary": None, "max_salary": None,
                          "only_salary_negotiable": True},
               "sort": "starts_at_desc", "ai_new_model": False,
               "meta": {"device_uid": str(uuid.uuid4())}, "page": page, "per": 50,
               "new_function_score": True, "seed": random.randint(1, 99999999)}
    req = urllib.request.Request(API, data=json.dumps(payload).encode(), headers=HDRS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("data", [])


def collect():
    seen_ids = set()
    out = []
    for pg in range(1, PAGES + 1):
        try:
            d = call_api(pg)
        except Exception as e:
            print("[WARN] page%d 실패: %s" % (pg, str(e)[:60]))
            break
        for p in d:
            if p["id"] in seen_ids:
                continue
            seen_ids.add(p["id"])
            out.append(p)
        if len(d) < 50:
            break
        time.sleep(0.5)
    return out


def includes_byeonrisa(p):
    blob = " ".join(str(p.get(k, "") or "") for k in TEXT_FIELDS)
    return MUST_INCLUDE in blob


def read_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(x.strip() for x in f if x.strip())
    except FileNotFoundError:
        return None


def write_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(str(x) for x in list(seen)[-1500:]))


def main():
    allp = collect()
    print("[INFO] 수집 %d건" % len(allp))
    if not allp:
        print("[ERROR] 수집 0건 - API 변경/차단 가능성"); sys.exit(0)

    matched = [p for p in allp if includes_byeonrisa(p)]
    print("[INFO] '변리사' 정확 포함 %d건" % len(matched))

    seen = read_seen()
    first_run = seen is None
    if first_run:
        seen = set()

    new_items = [p for p in matched if str(p["id"]) not in seen]
    print("[INFO] 신규 %d건 / 첫실행=%s" % (len(new_items), first_run))

    if first_run:
        for p in matched:
            seen.add(str(p["id"]))
        write_seen(seen)
        tg("[감시 시작] 리멤버 커리어 '변리사' 구인공고 감시를 시작했습니다. "
           "공고에 '변리사'가 정확히 포함된 것만 골라 상세내용을 요약해 보내드립니다. "
           "(현재 %d건은 기존 글로 처리)" % len(matched))
        print("[INFO] 첫 실행 베이스라인 기록"); return

    for p in reversed(new_items):
        org = (p.get("organization") or {}).get("name", "")
        addr = ""
        if p.get("addresses"):
            a = p["addresses"][0]
            addr = "%s %s" % (a.get("address_level1", ""), a.get("address_level2", ""))
        title = p.get("title", "")
        print("[INFO] 신규:", p["id"], org, title)
        src = "\n".join([title, p.get("introduction", "") or "",
                         p.get("qualifications", "") or "",
                         p.get("preferred_qualifications", "") or ""])
        summary = summarize(src) or "(요약 실패)"
        url = DETAIL_FMT % p["id"]
        msg = ("[리멤버 새 구인공고]\n\n제목: %s\n회사: %s\n지역: %s\n마감: %s\n\n[요약]\n%s\n\n링크: %s"
               % (title, org, addr.strip(), (p.get("ends_at", "") or "")[:10], summary, url))
        tg(msg)
        seen.add(str(p["id"]))
        time.sleep(1)

    write_seen(seen)
    print("[INFO] 완료")


if __name__ == "__main__":
    main()
