import requests
import time
import re
import gzip
import json
from datetime import datetime

# ============================================================
#  CONFIGURATION — edit these values
# ============================================================
PMA_URL     = "https://panel.disha-host.xyz/phpmyadmin/"
DB_USER     = "u18_xqZxhQ0CL3"
DB_PASS     = "Uwt2!woPg.Qhln@w@i^5oX2I"       # <-- paste your password here
DB_NAME     = "s18_user_yanis"

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1506904432405905529/fLeRYswoYAJrfbbKbNrZgwiUL8p8KhK6oRGejzjnNs4lIoOXSZVZwj4vTyCcEFNZY0tg"  # <-- your webhook URL

INTERVAL_MINUTES = 20
# ============================================================

def login(session):
    print("[*] Loading login page...")
    login_page = session.get(PMA_URL, timeout=15)

    token = ""
    match = re.search(r'name="token"\s+value="([^"]+)"', login_page.text)
    if match:
        token = match.group(1)

    login_resp = session.post(PMA_URL + "index.php", data={
        "pma_username": DB_USER,
        "pma_password": DB_PASS,
        "server": "1",
        "target": "index.php",
        "token": token
    }, timeout=15)

    if "pma_username" in login_resp.text:
        raise Exception("Login failed")

    print("[*] Logged in!")

    match = re.search(r'["\']token["\']\s*[,:]?\s*["\']([a-f0-9]{32})["\']', login_resp.text)
    if not match:
        match = re.search(r'token=([a-f0-9]{32})', login_resp.text)
    if not match:
        match = re.search(r'name="token"\s+value="([^"]+)"', login_resp.text)
    if not match:
        raise Exception("Could not extract session token")

    token = match.group(1)
    print(f"[*] Token: {token[:8]}...")
    return token

def get_tables(session, token):
    print("[*] Fetching table list via SQL...")

    # Use the SQL query page to get tables — most reliable method
    resp = session.post(PMA_URL + "index.php?route=/import", data={
        "db": DB_NAME,
        "token": token,
        "sql_query": f"SHOW TABLES FROM `{DB_NAME}`",
        "server": "1",
    }, timeout=15)

    tables = re.findall(r'<td[^>]*>\s*([a-zA-Z0-9_]+)\s*</td>', resp.text)
    # Filter out nav/UI text, keep only valid table names
    tables = list(set([
        t for t in tables
        if t and len(t) > 1 and len(t) < 64
        and not t.lower() in ['null','true','false','server','database','table','yes','no']
    ]))

    if tables:
        print(f"[*] Found {len(tables)} tables: {', '.join(tables)}")
        return tables

    # Fallback: try database structure page
    print("[*] Trying structure page for tables...")
    resp2 = session.get(
        PMA_URL + "index.php",
        params={"route": "/database/structure", "db": DB_NAME, "token": token},
        timeout=15
    )
    tables2 = re.findall(r'table=([a-zA-Z0-9_]+)[&"\']', resp2.text)
    tables2 = list(set([t for t in tables2 if t and len(t) < 64]))
    if tables2:
        print(f"[*] Found {len(tables2)} tables: {', '.join(tables2)}")
        return tables2

    return []

def export_database(session, token, tables):
    print("[*] Exporting database...")

    export_url = PMA_URL + "index.php?route=/export"

    # Build form data — must send each table as separate entries
    data = [
        ("db", DB_NAME),
        ("token", token),
        ("export_type", "database"),
        ("export_method", "custom"),
        ("quick_or_custom", "custom"),
        ("what", "sql"),
        ("sql_structure_or_data", "structure_and_data"),
        ("sql_create_table", "something"),
        ("sql_auto_increment", "something"),
        ("sql_truncate", "something"),
        ("sql_delayed", "something"),
        ("sql_ignore", "something"),
        ("sql_include_comments", "something"),
        ("sql_utc_time", "something"),
        ("compression", "none"),
        ("charset_of_file", "utf-8"),
        ("output_format", "sendit"),
        ("filename_template", f"backup_{DB_NAME}"),
        ("remember_template", "on"),
        ("server", "1"),
    ]

    # Add each table explicitly
    for table in tables:
        data.append(("table_select[]", table))
        data.append(("table_structure[]", table))
        data.append(("table_data[]", table))

    resp = session.post(export_url, data=data, timeout=120)

    print(f"[*] HTTP {resp.status_code} — {len(resp.content)} bytes")
    print(f"[*] Content-Type: {resp.headers.get('Content-Type','?')[:60]}")
    print(f"[*] Preview: {resp.text[:200]}")

    is_sql = (
        b"SET SQL_MODE" in resp.content or
        b"CREATE TABLE" in resp.content or
        b"INSERT INTO" in resp.content or
        b"/*!40" in resp.content
    )

    if resp.status_code == 200 and is_sql and len(resp.content) > 500:
        print("[*] Valid SQL export!")
        return resp.content

    raise Exception(f"Export returned {len(resp.content)} bytes — preview: {resp.text[:200]}")

def run_backup():
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"backup_{DB_NAME}_{date_str}.sql.gz"

    print(f"\n{'='*50}")
    print(f"[{date_str}] Starting backup...")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": PMA_URL,
    })

    try:
        token = login(session)
        tables = get_tables(session, token)

        if not tables:
            raise Exception("Could not find any tables in the database")

        content = export_database(session, token, tables)

        compressed = gzip.compress(content)
        size_mb = len(compressed) / (1024 * 1024)

        print(f"[*] Compressed: {size_mb:.2f} MB")
        print("[*] Sending to Discord...")

        message = (
            f"✅ **MTA:SA Backup**\n"
            f"📦 `{filename}`\n"
            f"🗄️ Database: `{DB_NAME}`\n"
            f"📊 Tables: `{len(tables)}`\n"
            f"💾 Size: `{size_mb:.2f} MB`\n"
            f"🕐 `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )

        response = requests.post(
            DISCORD_WEBHOOK,
            data={"payload_json": json.dumps({"content": message})},
            files={"file": (filename, compressed, "application/gzip")}
        )

        if response.status_code in (200, 204):
            print(f"[✓] Backup sent successfully!")
        else:
            print(f"[✗] Discord error: HTTP {response.status_code} — {response.text}")

    except Exception as e:
        print(f"[✗] Backup failed: {e}")
        try:
            requests.post(DISCORD_WEBHOOK, json={
                "content": f"❌ **MTA:SA Backup FAILED**\n🕐 `{date_str}`\n⚠️ `{e}`"
            })
        except:
            pass

def main():
    print(f"MTA:SA Auto Backup — every {INTERVAL_MINUTES} minutes")
    print(f"Database : {DB_NAME}")
    print(f"phpMyAdmin : {PMA_URL}")
    print(f"Press Ctrl+C to stop.\n")

    while True:
        run_backup()
        print(f"[*] Next backup in {INTERVAL_MINUTES} minutes... (Ctrl+C to stop)")
        time.sleep(INTERVAL_MINUTES * 60)

if __name__ == "__main__":
    main()