import os, re, json, urllib.request, urllib.error

TOKEN = os.environ["NOTION_TOKEN"].strip()

# принимаем ID хоть как: чистый, с дефисами, или целую ссылку на базу.
# берём первый 32-символьный hex — это и есть ID базы (то, что до "?v=").
_raw = os.environ["NOTION_DB_ID"].strip()
_m = re.search(r"[0-9a-fA-F]{32}", _raw.replace("-", ""))
DB = _m.group(0) if _m else _raw

H = {"Authorization": f"Bearer {TOKEN}",
     "Notion-Version": "2026-03-11",
     "Content-Type": "application/json"}

def api(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=H, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # печатаем настоящую причину от Notion, а не просто "400"
        print(f"--- Notion ответил {e.code} на {method} {url}")
        print(e.read().decode("utf-8"))
        raise

print(f"Использую ID базы: {DB}")

# 1) у базы спрашиваем её data source (новый Notion API)
ds_id = api(f"https://api.notion.com/v1/databases/{DB}")["data_sources"][0]["id"]

# 2) выгружаем события (постранично)
CAT = {"Сенсори": "sensory", "Кастинг": "kasting", "Обжарка": "roast", "Кофе": "coffee"}
events, cursor = [], None
while True:
    body = {"page_size": 100}
    if cursor:
        body["start_cursor"] = cursor
    res = api(f"https://api.notion.com/v1/data_sources/{ds_id}/query", "POST", body)
    for pg in res["results"]:
        p = pg["properties"]
        d = p.get("Дата", {}).get("date")
        if not d:
            continue
        title = "".join(t["plain_text"] for t in p.get("Название", {}).get("title", []))
        sel = p.get("Тип", {}).get("select")
        events.append({"d": d["start"][:10], "t": title,
                       "c": CAT.get(sel["name"] if sel else "", "coffee")})
    if res.get("has_more"):
        cursor = res["next_cursor"]
    else:
        break

events.sort(key=lambda e: e["d"])
with open("events.json", "w", encoding="utf-8") as f:
    json.dump(events, f, ensure_ascii=False, indent=2)
print(f"Готово: записано {len(events)} событий")with open("events.json", "w", encoding="utf-8") as f:
    json.dump(events, f, ensure_ascii=False, indent=2)
print(f"wrote {len(events)} events")
