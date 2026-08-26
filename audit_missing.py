import os
import re
import json
import requests
import gspread
from google.oauth2.service_account import Credentials

# ============================================================================
# CONFIGURATION
# ============================================================================
TURSO_URL = os.environ.get("TURSO_URL")
TURSO_TOKEN = os.environ.get("TURSO_TOKEN")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
SHEET_TAB_NAME = "Missing_Audit"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# ============================================================================
# TURSO DB CLIENT
# ============================================================================
def to_turso_arg(value):
    if value is None: return {"type": "null"}
    if isinstance(value, bool): return {"type": "integer", "value": "1" if value else "0"}
    if isinstance(value, int): return {"type": "integer", "value": str(value)}
    if isinstance(value, float): return {"type": "float", "value": str(value)}
    return {"type": "text", "value": str(value)}

def unwrap_turso_cell(cell):
    if not cell or cell.get("type") == "null": return None
    if cell.get("type") == "integer": return int(cell.get("value"))
    if cell.get("type") == "float": return float(cell.get("value"))
    return cell.get("value")

def turso_execute(sql, args=[]):
    payload = {"requests": [{"type": "execute", "stmt": {"sql": sql, "args": [to_turso_arg(a) for a in args]}}, {"type": "close"}]}
    headers = {"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}
    res = requests.post(f"{TURSO_URL}/v2/pipeline", json=payload, headers=headers, timeout=30)
    res.raise_for_status()
    return res.json()["results"][0]["response"]["result"]

def turso_query_all(sql, args=[]):
    result = turso_execute(sql, args)
    cols = [c["name"] for c in result["cols"]]
    return [{cols[i]: unwrap_turso_cell(r[i]) for i in range(len(cols))} for r in result["rows"]]

# ============================================================================
# MAIN AUDIT LOGIC
# ============================================================================
def main():
    print("=" * 60)
    print("BEAM AUDIT SCRIPT - FINDING MISSING LANGUAGES")
    print("=" * 60)

    if not os.environ.get("GOOGLE_SHEETS_JSON"):
        raise ValueError("GOOGLE_SHEETS_JSON secret is missing!")

    creds_dict = json.loads(os.environ.get("GOOGLE_SHEETS_JSON"))
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    gc = gspread.authorize(creds)
    
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.worksheet(SHEET_TAB_NAME)
    except Exception as e:
        print(f"❌ ERROR: Could not open Google Sheet/Tab. Make sure tab is named '{SHEET_TAB_NAME}' and shared with Service Account. ({e})")
        return

    # 1. Fetch ALL expected files from download_files
    print("Fetching expected files from download_files...")
    expected_files = turso_query_all("SELECT id, content_type, content_id, tmdb_id, quality, audio_languages FROM download_files")
    
    # Group expected languages by (content_type, content_id, base_quality)
    expected_map = {}
    for f in expected_files:
        content_type = f["content_type"]
        content_id = f["content_id"]
        raw_quality = f["quality"] or ""
        
        # Extract base quality (e.g., "1080p" from "1080p WEB-DL")
        q_match = re.search(r'(2160p|1080p|720p|480p|360p)', raw_quality, re.IGNORECASE)
        base_quality = q_match.group(1).lower() if q_match else raw_quality.lower()
        
        key = (content_type, content_id, base_quality)
        
        if key not in expected_map:
            expected_map[key] = set()
            
        try:
            langs = json.loads(f["audio_languages"] or "[]")
            for l in langs:
                expected_map[key].add(l)
        except:
            pass # Ignore broken JSON

    # 2. Fetch ALL actual links from movie_links and episode_links
    print("Fetching actual links from DB...")
    actual_movie_links = turso_query_all("SELECT movie_id, quality, audio_languages FROM movie_links")
    actual_episode_links = turso_query_all("SELECT episode_id, quality, audio_languages FROM episode_links")
    
    actual_map = {}
    
    for l in actual_movie_links:
        key = ("movie", l["movie_id"], (l["quality"] or "").lower())
        if key not in actual_map: actual_map[key] = set()
        try:
            for lang in json.loads(l["audio_languages"] or "[]"):
                actual_map[key].add(lang)
        except: pass

    for l in actual_episode_links:
        key = ("episode", l["episode_id"], (l["quality"] or "").lower())
        if key not in actual_map: actual_map[key] = set()
        try:
            for lang in json.loads(l["audio_languages"] or "[]"):
                actual_map[key].add(lang)
        except: pass

    # 3. Calculate the Gaps
    print("Calculating missing languages...")
    missing_records = []
    
    for key, expected_langs in expected_map.items():
        content_type, content_id, base_quality = key
        actual_langs = actual_map.get(key, set())
        
        # Find what is in expected but not in actual
        missing_langs = expected_langs - actual_langs
        
        if missing_langs:
            missing_records.append({
                "content_type": content_type,
                "content_id": content_id,
                "quality": base_quality,
                "missing_langs": ", ".join(sorted(list(missing_langs))),
                "expected_langs": ", ".join(sorted(list(expected_langs)))
            })

    # 4. Fetch Clean Names (Titles, Seasons, Episodes) for the missing records
    print(f"Found {len(missing_records)} missing entries. Fetching clean names...")
    
    movie_ids = list(set([r["content_id"] for r in missing_records if r["content_type"] == "movie"]))
    episode_ids = list(set([r["content_id"] for r in missing_records if r["content_type"] == "episode"]))

    movies_map = {}
    if movie_ids:
        # Fetch movie titles
        placeholders = ",".join(["?" for _ in movie_ids])
        m_data = turso_query_all(f"SELECT id, title, release_year, tmdb_id FROM movies WHERE id IN ({placeholders})", movie_ids)
        for m in m_data:
            movies_map[m["id"]] = m

    episodes_map = {}
    if episode_ids:
        # Fetch episode titles + series info
        placeholders = ",".join(["?" for _ in episode_ids])
        ep_data = turso_query_all(f"""
            SELECT e.id, e.episode_number, e.season_id, s.season_number, ser.title AS series_title, ser.tmdb_id AS series_tmdb_id
            FROM episodes e
            JOIN seasons s ON e.season_id = s.id
            JOIN series ser ON e.series_id = ser.id
            WHERE e.id IN ({placeholders})
        """, episode_ids)
        for ep in ep_data:
            episodes_map[ep["id"]] = ep

    # 5. Format rows for Google Sheets
    sheet_rows = []
    for r in missing_records:
        if r["content_type"] == "movie":
            m = movies_map.get(r["content_id"], {})
            sheet_rows.append([
                "Movie",
                m.get("tmdb_id", "?"),
                m.get("title", "Unknown Movie"),
                "-", # Season
                "-", # Episode
                r["quality"],
                r["expected_langs"],
                r["missing_langs"]
            ])
        else:
            ep = episodes_map.get(r["content_id"], {})
            sheet_rows.append([
                "Series",
                ep.get("series_tmdb_id", "?"),
                ep.get("series_title", "Unknown Series"),
                ep.get("season_number", "?"),
                ep.get("episode_number", "?"),
                r["quality"],
                r["expected_langs"],
                r["missing_langs"]
            ])

    # 6. Write to Google Sheets (Clear first to avoid duplicates)
    print(f"Writing {len(sheet_rows)} rows to Google Sheets...")
    
    # Clear existing data (except the header row in A1)
    worksheet.clear(start_row=2, start_col=1, end_row=worksheet.row_count, end_col=8)
    
    if sheet_rows:
        # Append all missing records at once
        worksheet.append_rows(sheet_rows, value_input_option="USER_ENTERED", table_range="A2")
        print(f"✅ Successfully updated sheet with {len(sheet_rows)} missing records.")
    else:
        print("✅ Sheet updated. No missing languages found! Everything is complete.")

if __name__ == "__main__":
    main()
