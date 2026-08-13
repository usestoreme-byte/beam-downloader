import os
import json
import base64
import asyncio
import re
import requests
from telethon import TelegramClient, events

# ============================================================================
# CONFIGURATION
# ============================================================================
TURSO_URL = os.environ.get("TURSO_URL", "https://beambot-music.aws-ap-northeast-1.turso.io")
TURSO_TOKEN = os.environ.get("TURSO_TOKEN", "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODI2NDUwNzksImlkIjoiMDE5ZjBkZGUtOTkwMS03ZTU5LTlkMzAtMTMwNjY4MjBiNjQwIiwicmlkIjoiNzMwZTQ3MzYtMmRkYi00OTllLTk3NzctNzE0ODA5N2I0ODRmIn0.zGzfC062A0UMFuzn-aSl0pkuUIeJt9yy46NXnmg4bCoSx-PCgTMiEw2SeQwwsSr--X7PkD5f9LBezl-w70Z3Aw")

API_ID = int(os.environ.get("TG_API_ID", "39631214"))
API_HASH = os.environ.get("TG_API_HASH", "341da0c5a267f02ccc36efe6582049e6")
SESSION_BASE64 = os.environ.get("TG_SESSION_BASE64")

PRIVATE_CHANNEL_ID = -1003998322386
AV_F2L_BOT_USERNAME = 'AV_F2L_BOT'

CHECKPOINT_FILE = "state.json"
BATCH_SIZE = 100

# ============================================================================
# TURSO DB CLIENT (Fixed formatting)
# ============================================================================
def to_turso_arg(value):
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": "1" if value else "0"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": str(value)}
    return {"type": "text", "value": str(value)}

def turso_execute(sql, args=[]):
    payload = {
        "requests": [
            {"type": "execute", "stmt": {"sql": sql, "args": [to_turso_arg(a) for a in args]}},
            {"type": "close"}
        ]
    }
    headers = {"Authorization": f"Bearer {TURSO_TOKEN}", "Content-Type": "application/json"}
    res = requests.post(f"{TURSO_URL}/v2/pipeline", json=payload, headers=headers, timeout=30)
    res.raise_for_status()
    return res.json()["results"][0]["response"]["result"]

def turso_query_all(sql, args=[]):
    result = turso_execute(sql, args)
    cols = [c["name"] for c in result["cols"]]
    return [dict(zip(cols, row)) for row in result["rows"]]

# ============================================================================
# TELEGRAM F2L BOT
# ============================================================================
def decode_session():
    if SESSION_BASE64:
        with open('beam_session.session', 'wb') as f:
            f.write(base64.b64decode(SESSION_BASE64))

async def get_download_link(channel_msg_id):
    client = TelegramClient('beam_session', API_ID, API_HASH)
    await client.start()
    
    await client.forward_messages(
        entity=AV_F2L_BOT_USERNAME,
        messages=channel_msg_id,
        from_peer=PRIVATE_CHANNEL_ID
    )
    
    future = asyncio.Future()
    @client.on(events.NewMessage(from_users=AV_F2L_BOT_USERNAME))
    async def handler(event):
        if not future.done():
            future.set_result(event.message)
            
    try:
        reply_msg = await asyncio.wait_for(future, timeout=60.0)
        match = re.search(r'📥.*?:\s*`(https?://\S+)`', reply_msg.text)
        if match:
            return match.group(1)
        return None
    except asyncio.TimeoutError:
        return None
    finally:
        client.remove_event_handler(handler)
        await client.disconnect()

# ============================================================================
# CHECKPOINT LOGIC
# ============================================================================
def get_checkpoint():
    if not os.path.exists(CHECKPOINT_FILE):
        return 0
    with open(CHECKPOINT_FILE, 'r') as f:
        return json.load(f).get("last_id", 0)

def save_checkpoint(last_id):
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump({"last_id": last_id}, f)

# ============================================================================
# MAIN PIPELINE (DRY RUN)
# ============================================================================
async def main():
    print("=" * 60)
    print("BEAM PIPELINE - DRY RUN TEST")
    print("=" * 60)
    
    decode_session()
    checkpoint = get_checkpoint()
    print(f"Current Checkpoint: {checkpoint}")
    
    # Fetch next 100 rows from download_files
    rows = turso_query_all(
        "SELECT * FROM download_files WHERE id > ? ORDER BY id ASC LIMIT ?",
        [checkpoint, BATCH_SIZE]
    )
    
    if not rows:
        print("No new files to process. Exiting.")
        return
        
    print(f"Found {len(rows)} candidate rows. Finding first one with missing work...\n")
    
    for row in rows:
        # Extract row data carefully handling potential nulls
        df_id = row["id"]["value"] if isinstance(row["id"], dict) else row["id"]
        content_type = row["content_type"]["value"] if isinstance(row["content_type"], dict) else row["content_type"]
        content_id = row["content_id"]["value"] if isinstance(row["content_id"], dict) else row["content_id"]
        quality = row["quality"]["value"] if isinstance(row["quality"], dict) else row["quality"]
        channel_msg_id = row["channel_msg_id"]["value"] if isinstance(row["channel_msg_id"], dict) else row["channel_msg_id"]
        file_name = row["file_name"]["value"] if isinstance(row["file_name"], dict) else row["file_name"]
        
        audio_lang_raw = row["audio_languages"]["value"] if isinstance(row["audio_languages"], dict) else row["audio_languages"]
        declared_langs = json.loads(audio_lang_raw or "[]")
        
        if not declared_langs:
            declared_langs = ["Unknown"]
            
        # Determine which links table to check
        links_table = "movie_links" if content_type == "movie" else "episode_links"
        id_column = "movie_id" if content_type == "movie" else "episode_id"
        
        # Check what languages are ALREADY done for this file's quality
        existing_links = turso_query_all(
            f"SELECT audio_languages FROM {links_table} WHERE {id_column} = ? AND quality = ?",
            [content_id, quality]
        )
        
        done_langs = set()
        for link_row in existing_links:
            lang_raw = link_row["audio_languages"]["value"] if isinstance(link_row["audio_languages"], dict) else link_row["audio_languages"]
            langs = json.loads(lang_raw or "[]")
            for l in langs:
                done_langs.add(l)
                
        # What languages are actually missing?
        missing_langs = [l for l in declared_langs if l not in done_langs]
        
        if not missing_langs:
            # Fully resolved, advance checkpoint safely
            print(f"[{df_id}] {file_name} - All languages already done. Skipping & advancing checkpoint.")
            save_checkpoint(df_id)
            continue
            
        # WE FOUND WORK TO DO
        print(f"*** FOUND WORK TO DO ***")
        print(f"  Row ID      : {df_id}")
        print(f"  File        : {file_name}")
        print(f"  Quality     : {quality}")
        print(f"  Type        : {content_type}")
        print(f"  Declared    : {declared_langs}")
        print(f"  Already Done: {list(done_langs)}")
        print(f"  Missing     : {missing_langs}")
        
        print(f"\nForwarding to F2L Bot (msg_id: {channel_msg_id})...")
        link = await get_download_link(channel_msg_id)
        
        if link:
            print(f"  F2L Link    : {link}")
            print("\n=> If this was a real run, I would download this file, split it into " + ", ".join(missing_langs) + ", upload to Vidara, and insert into DB.")
        else:
            print("  Failed to get link from F2L bot.")
            
        print("\nStopping dry run here so you can verify everything looks correct.")
        break

if __name__ == "__main__":
    asyncio.run(main())
