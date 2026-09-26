import os, re, json, urllib.request, urllib.error

TOKEN = os.environ["NOTION_TOKEN"].strip()

_raw = os.environ["NOTION_DB_ID"].strip()
_m = re.search(r"[0-9a-fA-F]{32}", _raw.replace("-", ""))
DB = _m.group(0) if _m else _raw

H = {"Authorization": f"Bearer {TOKEN}",
     "Notion-Version": "2026-03-11",
     "Content-Type": "application/json"}

# ===== ТЕГИ → КАТЕГОРИЯ =====
# В Notion заведи колонку «Теги» (Multi-select). Категорию скрипт определяет
# по словам в тегах (регистр не важен, достаточно начала слова).
# Порядок важен: сначала проверяется турнир, потом тренинг, потом ивент.
RULES = [
    ("comp",     ["чемп", "турнир", "соревн", "судейств", "competition"]),
    ("training", ["тренинг", "обучен", "курс", "урок", "класс", "training"]),
    ("event",    ["ивент", "событ", "каппинг", "капинг", "казино", "дегустац",
                  "мероприят", "лекци", "event", "cupping"]),
]
DEFAULT_CAT = "event"

NAMES_DESC = ["описание", "description", "desc"]
NAMES_LINK = ["ссылка", "запись", "link", "url"]


def api(url, method="GET", body=None, quiet=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=H, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        e.body = e.read().decode("utf-8")
        if not quiet:
            print(f"--- Notion ответил {e.code} на {method} {url}")
            print(e.body)
        raise


def find_db_in_page(block_id, depth=0):
    """Ищем базу внутри страницы (в т.ч. внутри колонок и переключателей)."""
    cursor = None
    while True:
        url = f"https://api.notion.com/v1/blocks/{block_id}/children?page_size=100"
        if cursor:
            url += f"&start_cursor={cursor}"
        res = api(url)
        for b in res["results"]:
            if b.get("type") == "child_database":
                title = b["child_database"].get("title", "")
                print(f"Нашёл базу на странице: «{title}» ({b['id']})")
                return b["id"]
        if depth < 3:
            for b in res["results"]:
                if b.get("has_children") and b.get("type") != "child_page":
                    found = find_db_in_page(b["id"], depth + 1)
                    if found:
                        return found
        if res.get("has_more"):
            cursor = res["next_cursor"]
        else:
            return None


def open_database(db_id):
    """Открываем базу; если передали страницу — ищем базу внутри неё."""
    try:
        return api(f"https://api.notion.com/v1/databases/{db_id}", quiet=True)
    except urllib.error.HTTPError as e:
        if e.code == 400 and "is a page" in getattr(e, "body", ""):
            print("По ссылке страница, а не база — ищу базу внутри страницы...")
            inner = find_db_in_page(db_id)
            if not inner:
                raise SystemExit(
                    "На странице не нашлось базы. Проверь: база должна быть "
                    "настоящей (не «linked view» другой базы), а интеграция — "
                    "подключена к странице через ••• → Connections.")
            return api(f"https://api.notion.com/v1/databases/{inner}")
        print(f"--- Notion ответил {e.code}")
        print(getattr(e, "body", ""))
        raise


def text_of(prop):
    """Текст из свойства любого 'текстового' типа."""
    t = prop.get("type")
    if t in ("title", "rich_text"):
        return "".join(x.get("plain_text", "") for x in prop[t])
    if t in ("select", "status"):
        return prop[t]["name"] if prop.get(t) else ""
    if t == "multi_select":
        return prop[t][0]["name"] if prop[t] else ""
    if t == "url":
        return prop["url"] or ""
    return ""


def find(props, names, types):
    """Ищем колонку по имени (из списка) нужного типа."""
    for name, prop in props.items():
        if name.strip().lower() in names and prop.get("type") in types:
            return prop
    return None


def all_tags(props):
    """Все значения из колонок типа select / multi_select."""
    tags = []
    for prop in props.values():
        t = prop.get("type")
        if t == "multi_select":
            tags += [x["name"] for x in prop["multi_select"]]
        elif t == "select" and prop["select"]:
            tags.append(prop["select"]["name"])
    return tags


def category(tags):
    low = [t.lower() for t in tags]
    for cat, words in RULES:
        if any(w in t for t in low for w in words):
            return cat
    return DEFAULT_CAT


def parse_page(props):
    title, start, end = "", None, None
    for prop in props.values():
        if prop.get("type") == "title":
            title = text_of(prop)
        elif prop.get("type") == "date" and prop["date"] and start is None:
            start = prop["date"]["start"][:10]
            end = (prop["date"].get("end") or "")[:10] or None

    desc_p = find(props, NAMES_DESC, ("rich_text",))
    if desc_p is None:
        desc_p = next((p for p in props.values() if p.get("type") == "rich_text"), None)
    link_p = find(props, NAMES_LINK, ("url", "rich_text"))

    tags = all_tags(props)
    return {
        "d": start,
        "e": end if end and end != start else None,
        "t": title,
        "c": category(tags),
        "tags": tags,
        "desc": text_of(desc_p) if desc_p else "",
        "url": text_of(link_p) if link_p else "",
    }


print(f"Использую ID базы: {DB}")
db_info = open_database(DB)
ds_id = db_info["data_sources"][0]["id"]

events, cursor, dumped = [], None, False
while True:
    body = {"page_size": 100}
    if cursor:
        body["start_cursor"] = cursor
    res = api(f"https://api.notion.com/v1/data_sources/{ds_id}/query", "POST", body)
    if res["results"] and not dumped:
        print("Колонки базы (имя: тип):")
        for name, prop in res["results"][0]["properties"].items():
            print(f"   {name}: {prop.get('type')}")
        dumped = True
    for pg in res["results"]:
        ev = parse_page(pg["properties"])
        if ev["d"]:
            events.append(ev)
    if res.get("has_more"):
        cursor = res["next_cursor"]
    else:
        break

events.sort(key=lambda e: e["d"])
with open("events.json", "w", encoding="utf-8") as f:
    json.dump(events, f, ensure_ascii=False, indent=2)
print(f"Готово: записано {len(events)} событий")
