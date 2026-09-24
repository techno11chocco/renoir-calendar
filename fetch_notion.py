import os, re, json, urllib.request, urllib.error

TOKEN = os.environ["NOTION_TOKEN"].strip()

_raw = os.environ["NOTION_DB_ID"].strip()
_m = re.search(r"[0-9a-fA-F]{32}", _raw.replace("-", ""))
DB = _m.group(0) if _m else _raw

H = {"Authorization": f"Bearer {TOKEN}",
     "Notion-Version": "2026-03-11",
     "Content-Type": "application/json"}

CAT = {"Сенсори": "sensory", "Кастинг": "kasting", "Обжарка": "roast", "Кофе": "coffee"}


def api(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=H, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        print(f"--- Notion ответил {e.code} на {method} {url}")
        print(e.read().decode("utf-8"))
        raise


def parse_page(props):
    title, date_val, cat = "", None, ""
    for prop in props.values():
        t = prop.get("type")
        if t == "title":
            title = "".join(x["plain_text"] for x in prop["title"])
        elif t == "date" and prop["date"] and date_val is None:
            date_val = prop["date"]["start"]
        elif t == "select" and prop["select"] and not cat:
            cat = prop["select"]["name"]
        elif t == "status" and prop.get("status") and not cat:
            cat = prop["status"]["name"]
    return title, date_val, cat


print(f"Использую ID базы: {DB}")

db_info = api(f"https://api.notion.com/v1/databases/{DB}")
print("Название базы:", "".join(t.get("plain_text", "") for t in db_info.get("title", [])) or "(без имени)")
print("data sources:", [d["id"] for d in db_info["data_sources"]])
ds_id = db_info["data_sources"][0]["id"]

events, cursor, page_no, dumped = [], None, 0, False
while True:
    body = {"page_size": 100}
    if cursor:
        body["start_cursor"] = cursor
    res = api(f"https://api.notion.com/v1/data_sources/{ds_id}/query", "POST", body)
    page_no += 1
    print(f"Страница {page_no}: строк получено = {len(res['results'])}")
    if res["results"] and not dumped:
        print("=== Колонки первой строки (имя: тип) ===")
        for name, prop in res["results"][0]["properties"].items():
            print(f"   {name}: {prop.get('type')}")
        print("========================================")
        dumped = True
    for pg in res["results"]:
        title, date_val, cat = parse_page(pg["properties"])
        if not date_val:
            continue
        events.append({"d": date_val[:10], "t": title, "c": CAT.get(cat, "coffee")})
    if res.get("has_more"):
        cursor = res["next_cursor"]
    else:
        break

events.sort(key=lambda e: e["d"])
with open("events.json", "w", encoding="utf-8") as f:
    json.dump(events, f, ensure_ascii=False, indent=2)
print(f"Готово: записано {len(events)} событий")
