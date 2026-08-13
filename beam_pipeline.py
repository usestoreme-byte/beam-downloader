import os
import re
import json
import shutil
import base64
import asyncio
import requests
import subprocess
import time
from pathlib import Path
from pymediainfo import MediaInfo
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor
from telethon import TelegramClient, events

# ============================================================================
# CONFIGURATION
# ============================================================================
TURSO_URL = os.environ.get("TURSO_URL")
TURSO_TOKEN = os.environ.get("TURSO_TOKEN")
VIDARA_API_KEY = os.environ.get("VIDARA_API_KEY", "").strip()

API_ID = int(os.environ.get("TG_API_ID"))
API_HASH = os.environ.get("TG_API_HASH")
SESSION_BASE64 = os.environ.get("TG_SESSION_BASE64")

PRIVATE_CHANNEL_ID = -1003998322386

F2L_BOT_USERNAME = 'AV_F2L_BOT'
LCU_BOT_USERNAME = 'LCU_Filetolinkbot'
LINK_STREAMER_BOT = 'linkstreamerbot'

CHECKPOINT_FILE = "state.json"
FOLDERS_FILE = "folders.json"
BATCH_SIZE = 100

OUTPUT_FOLDER = "./media/processed"
TEMP_FOLDER = "./temp_downloads"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

# Archive.org / Litterbox config (from your original code)
IA_ACCESS_KEY = os.environ.get("IA_ACCESS_KEY", "EQ6XJ3AACbxfK4n7").strip()
IA_SECRET_KEY = os.environ.get("IA_SECRET_KEY", "BlzN7vT0uJo7g3n2").strip()
LITTERBOX_API = "https://litterbox.catbox.moe/resources/internals/api.php"

LANG_MAP = {
    "as": "Assamese", "te": "Telugu", "hi": "Hindi", "ta": "Tamil", "ml": "Malayalam",
    "kn": "Kannada", "bn": "Bengali", "pa": "Punjabi", "gu": "Gujarati", "mr": "Marathi",
    "or": "Oriya", "en": "English", "ja": "Japanese", "ko": "Korean", "es": "Spanish",
    "fr": "French", "de": "German", "ru": "Russian", "zh": "Chinese", "it": "Italian",
    "pt": "Portuguese", "ar": "Arabic", "tr": "Turkish",
    "id": "Indonesian", "ms": "Malay", "th": "Thai", "vi": "Vietnamese", "tl": "Filipino",
    "he": "Hebrew", "fa": "Persian", "ur": "Urdu", "ne": "Nepali", "si": "Sinhala",
    "my": "Burmese", "km": "Khmer", "lo": "Lao", "mn": "Mongolian",
    "nl": "Dutch", "sv": "Swedish", "no": "Norwegian", "da": "Danish", "fi": "Finnish",
    "pl": "Polish", "cs": "Czech", "sk": "Slovak", "hu": "Hungarian", "ro": "Romanian",
    "el": "Greek", "uk": "Ukrainian", "bg": "Bulgarian", "hr": "Croatian", "sr": "Serbian",
    "sl": "Slovenian", "bs": "Bosnian", "mk": "Macedonian", "sq": "Albanian",
    "lt": "Lithuanian", "lv": "Latvian", "et": "Estonian", "is": "Icelandic",
    "ga": "Irish", "cy": "Welsh", "eu": "Basque", "ca": "Catalan", "gl": "Galician",
    "af": "Afrikaans", "zu": "Zulu", "xh": "Xhosa", "sw": "Swahili", "am": "Amharic",
    "so": "Somali", "ha": "Hausa", "yo": "Yoruba", "ig": "Igbo", "st": "Sotho",
    "ka": "Georgian", "hy": "Armenian", "az": "Azerbaijani", "kk": "Kazakh",
    "uz": "Uzbek", "ky": "Kyrgyz", "tg": "Tajik", "tk": "Turkmen", "ps": "Pashto",
    "ku": "Kurdish", "sd": "Sindhi", "bo": "Tibetan", "dz": "Dzongkha",
    "jv": "Javanese", "su": "Sundanese", "ceb": "Cebuano", "haw": "Hawaiian",
    "mi": "Maori", "sm": "Samoan", "to": "Tongan", "fj": "Fijian",
    "eo": "Esperanto", "la": "Latin", "yi": "Yiddish", "mt": "Maltese",
    "lb": "Luxembourgish", "fo": "Faroese", "gd": "Scottish Gaelic", "br": "Breton",
    "co": "Corsican", "oc": "Occitan", "rm": "Romansh", "gn": "Guarani",
    "qu": "Quechua", "ay": "Aymara", "ht": "Haitian Creole",
}
UNKNOWN_TOKENS = {"", "und", "unknown", "unk", "n/a", "none"}
ISO2_TO_ISO3 = { "as": "asm", "te": "tel", "hi": "hin", "ta": "tam", "ml": "mal", "kn": "kan", "bn": "ben", "pa": "pan", "gu": "guj", "mr": "mar", "or": "ori", "en": "eng", "ja": "jpn", "ko": "kor", "es": "spa", "fr": "fre", "de": "ger", "ru": "rus", "zh": "chi", "it": "ita", "pt": "por", "ar": "ara", "tr": "tur", "id": "ind", "ms": "may", "th": "tha", "vi": "vie", "tl": "fil", "he": "heb", "fa": "per", "ur": "urd", "ne": "nep", "si": "sin", "my": "bur", "km": "khm", "lo": "lao", "mn": "mon", "nl": "dut", "sv": "swe", "no": "nor", "da": "dan", "fi": "fin", "pl": "pol", "cs": "cze", "sk": "slo", "hu": "hun", "ro": "rum", "el": "gre", "uk": "ukr", "bg": "bul", "hr": "hrv", "sr": "srp", "sl": "slv", "bs": "bos", "mk": "mac", "sq": "alb", "lt": "lit", "lv": "lav", "et": "est", "is": "ice", "ga": "gle", "cy": "wel", "eu": "baq", "ca": "cat", "gl": "glg", "af": "afr", "zu": "zul", "xh": "xho", "sw": "swa", "am": "amh", "so": "som", "ha": "hau", "yo": "yor", "ig": "ibo", "st": "sot", "ka": "geo", "hy": "arm", "az": "aze", "kk": "kaz", "uz": "uzb", "ky": "kir", "tg": "tgk", "tk": "tuk", "ps": "pus", "ku": "kur", "sd": "snd", "bo": "tib", "dz": "dzo", "jv": "jav", "su": "sun", "ceb": "ceb", "haw": "haw", "mi": "mao", "sm": "smo", "to": "ton", "fj": "fij", "eo": "epo", "la": "lat", "yi": "yid", "mt": "mlt", "lb": "ltz", "fo": "fao", "gd": "gla", "br": "bre", "co": "cos", "oc": "oci", "rm": "roh", "gn": "grn", "qu": "que", "ay": "aym", "ht": "hat" }
NAME_TO_ISO3 = {name: ISO2_TO_ISO3[code] for code, name in LANG_MAP.items() if code in ISO2_TO_ISO3}
SERIES_AUDIO_LANG_OVERRIDES = { "1399": {"is": "English"} }

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

def turso_query_one(sql, args=[]):
    rows = turso_query_all(sql, args)
    return rows[0] if rows else None

# ============================================================================
# TELEGRAM BOTS
# ============================================================================
def decode_session():
    if SESSION_BASE64:
        with open('beam_session.session', 'wb') as f:
            f.write(base64.b64decode(SESSION_BASE64))

async def wait_for_bot_reply(client, bot_username, target_regex, timeout=90):
    future = asyncio.Future()
    
    @client.on(events.NewMessage(from_users=bot_username))
    async def handler(event):
        msg = event.message
        text = msg.raw_text or ""
        if re.search(target_regex, text):
            if not future.done(): future.set_result(msg)
            return
        if msg.buttons:
            for row in msg.buttons:
                for btn in row:
                    if btn.url and re.search(target_regex, btn.url):
                        if not future.done(): future.set_result(msg)
                        return
                        
    try:
        await asyncio.wait_for(future, timeout=timeout)
        return future.result()
    except asyncio.TimeoutError:
        return None
    finally:
        client.remove_event_handler(handler)

async def get_download_link_f2l(client, channel_msg_id):
    try:
        await client.forward_messages(entity=F2L_BOT_USERNAME, messages=int(channel_msg_id), from_peer=PRIVATE_CHANNEL_ID)
        reply_msg = await wait_for_bot_reply(client, F2L_BOT_USERNAME, r'av-f2l-bot\.avbotz26\.workers\.dev', timeout=60)
        if not reply_msg: return None
        
        text = reply_msg.raw_text or ""
        links = re.findall(r'(https?://[^\s`\'"]+)', text)
        for l in links:
            if '/watch/' not in l: return l
        if links: return links[0]
        
        if reply_msg.buttons:
            for row in reply_msg.buttons:
                for btn in row:
                    if btn.url: return btn.url
        return None
    except Exception as e:
        print(f"  F2L Error: {e}")
        return None

async def get_download_link_lcu(client, channel_msg_id):
    try:
        await client.forward_messages(entity=LCU_BOT_USERNAME, messages=int(channel_msg_id), from_peer=PRIVATE_CHANNEL_ID)
        reply1 = await wait_for_bot_reply(client, LCU_BOT_USERNAME, r'player2\.mrfooll\.xyz', timeout=60)
        if not reply1:
            print("  LCU did not provide a player link.")
            return None
            
        text1 = reply1.raw_text or ""
        links1 = re.findall(r'(https?://player2\.mrfooll\.xyz[^\s`\'"]+)', text1)
        player_link = links1[0] if links1 else None
        
        if not player_link and reply1.buttons:
            for row in reply1.buttons:
                for btn in row:
                    if btn.url and 'player2.mrfooll.xyz' in btn.url:
                        player_link = btn.url
                        break
                if player_link: break
                
        if not player_link: return None
        print(f"  LCU Player Link: {player_link}")
        
        await client.send_message(LINK_STREAMER_BOT, player_link)
        reply2 = await wait_for_bot_reply(client, LINK_STREAMER_BOT, r'streamapi\.mrfooll\.xyz', timeout=90)
        if not reply2:
            print("  Streamer did not provide a streamapi link.")
            return None
            
        text2 = reply2.raw_text or ""
        links2 = re.findall(r'(https?://streamapi\.mrfooll\.xyz[^\s`\'"]+)', text2)
        return links2[0] if links2 else None
        
    except Exception as e:
        print(f"  LCU Error: {e}")
        return None

async def get_download_link(client, channel_msg_id):
    print("  Trying LCU 2-step bot...")
    link = await get_download_link_lcu(client, channel_msg_id)
    if link:
        print(f"  LCU Link: {link}")
        return link
        
    print("  LCU failed. Falling back to AV_F2L_BOT...")
    link = await get_download_link_f2l(client, channel_msg_id)
    print(f"  F2L Link: {link}")
    return link

# ============================================================================
# STATE FILES
# ============================================================================
def get_checkpoint():
    if not os.path.exists(CHECKPOINT_FILE): return 0
    with open(CHECKPOINT_FILE, 'r') as f: return json.load(f).get("last_id", 0)

def save_checkpoint(last_id):
    with open(CHECKPOINT_FILE, 'w') as f: json.dump({"last_id": last_id}, f)

def get_or_create_vidara_folder(series_name, season_num, quality):
    cache = {}
    if os.path.exists(FOLDERS_FILE):
        with open(FOLDERS_FILE, 'r') as f:
            cache = json.load(f)
            
    cache_key = f"{series_name}_{season_num}_{quality}"
    if cache_key in cache:
        return cache[cache_key]
        
    clean_name = clean_string_for_vidara(series_name)
    folder_name = f"{clean_name} Season {int(season_num):02d} {quality}"
    
    try:
        res = requests.get(f"https://api.vidara.so/v1/folder/create?api_key={VIDARA_API_KEY}&name={requests.utils.quote(folder_name)}", timeout=30).json()
        if res.get("status") == 200:
            fld_id = res["result"]["folder_id"]
            cache[cache_key] = fld_id
            with open(FOLDERS_FILE, 'w') as f:
                json.dump(cache, f)
            print(f"  [FOLDER] Created/Fetched '{folder_name}' -> {fld_id}")
            return fld_id
        else:
            print(f"  [FOLDER] Warning: {res}")
    except Exception as e:
        print(f"  [FOLDER] Error: {e}")
    return None

# ============================================================================
# MEDIA PROCESSING & SUBTITLES
# ============================================================================
def normalize_audio_lang(raw_code, raw_name=None, override_map=None):
    code = (raw_code or "").strip().lower()
    if override_map and code in override_map: return override_map[code]
    if code in LANG_MAP: return LANG_MAP[code]
    name = (raw_name or "").strip()
    if name:
        for full in LANG_MAP.values():
            if name.lower() == full.lower(): return full
    return "Unknown"

def normalize_subtitle_lang(raw_code, raw_name=None):
    code = (raw_code or "").strip().lower()
    if code in LANG_MAP: return LANG_MAP[code]
    name = (raw_name or "").strip()
    if name:
        for full in LANG_MAP.values():
            if name.lower() == full.lower(): return full
    return "English"

def iso3_for_language(language_name):
    return NAME_TO_ISO3.get(language_name, "und")

def inspect_tracks(file_path, tmdb_id=None):
    override_map = SERIES_AUDIO_LANG_OVERRIDES.get(str(tmdb_id)) if tmdb_id is not None else None
    media = MediaInfo.parse(str(file_path))
    audio_tracks, subtitle_tracks = [], []
    audio_pos, sub_pos = 0, 0
    for track in media.tracks:
        if track.track_type == "Audio":
            title = str(getattr(track, "title", "")).lower()
            if any(kw in title for kw in ["commentary", "director", "descriptive", "visual impairment", "dvs"]): continue
            lang = normalize_audio_lang(track.language, getattr(track, "language_full", None), override_map)
            audio_tracks.append({"stream_index": audio_pos, "language": lang})
            audio_pos += 1
        elif track.track_type == "Text":
            lang = normalize_subtitle_lang(track.language, getattr(track, "language_full", None))
            sub_fmt = str(getattr(track, "format", "")).lower()
            sub_codec = str(getattr(track, "codecid", "")).lower()
            subtitle_tracks.append({"stream_index": sub_pos, "language": lang, "format": sub_fmt, "codec": sub_codec})
            sub_pos += 1
    if not audio_tracks: audio_tracks = [{"stream_index": 0, "language": "Unknown"}]
    return audio_tracks, subtitle_tracks

def remux_single_audio(source_path, output_path, audio_track, subtitle_tracks, subtitle_srt_overrides=None):
    subtitle_srt_overrides = subtitle_srt_overrides or {}
    cmd = ["ffmpeg", "-y", "-i", str(source_path)]
    override_input_idx = {}
    next_input = 1
    for sub in subtitle_tracks:
        override_path = subtitle_srt_overrides.get(sub["stream_index"])
        if override_path and os.path.exists(override_path):
            cmd += ["-i", str(override_path)]
            override_input_idx[sub["stream_index"]] = next_input
            next_input += 1

    cmd += ["-map", "0:v:0", "-map", f"0:a:{audio_track['stream_index']}"]
    mapped_subs = []
    for sub in subtitle_tracks:
        if sub["stream_index"] in override_input_idx:
            mapped_subs.append(sub)
            cmd += ["-map", f"{override_input_idx[sub['stream_index']]}:0"]
            cmd += [f"-c:s:{len(mapped_subs)-1}", "copy"]
        else:
            fmt = sub.get("format", "").lower()
            codec = sub.get("codec", "").lower()
            if not any(s in fmt or s in codec for s in ["subrip", "srt", "utf-8", "ass", "ssa", "pgs", "pgssub", "hdmv", "vobsub", "dvd_subtitle", "s_text", "s_hdmv"]): continue
            mapped_subs.append(sub)
            cmd += ["-map", f"0:s:{sub['stream_index']}"]

    cmd += ["-c", "copy", "-map_chapters", "-1"]
    cmd += ["-metadata:s:a:0", f"language={iso3_for_language(audio_track['language'])}"]
    for out_idx, sub in enumerate(mapped_subs):
        cmd += [f"-metadata:s:s:{out_idx}", f"language={iso3_for_language(sub['language'])}"]
    cmd.append(str(output_path))
    
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) < 1024:
        raise Exception(f"ffmpeg remux failed: {result.stderr[-500:] if result.stderr else 'unknown error'}")

def clean_string_for_vidara(text):
    if not text: return ""
    text = text.replace(".", "").replace("/", "-")
    text = re.sub(r'[:*?"<>|]', "", text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def build_filename(content_type, title, year, season, episode, quality, language):
    clean_title = clean_string_for_vidara(title)
    if content_type == "movie":
        if year: return f"{clean_title} ({year}) {quality} {language}.mkv"
        return f"{clean_title} {quality} {language}.mkv"
    else:
        return f"{clean_title} S{int(season):02d} E{int(episode):02d} {quality} {language}.mkv"

# --- Subtitle OCR & Hosting (From your original code) ---
def extract_subtitle_to_srt(source_path, subtitle_stream_index, output_srt_path):
    cmd = ["ffmpeg", "-y", "-i", str(source_path), "-map", f"0:s:{subtitle_stream_index}", "-c:s", "srt", str(output_srt_path)]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0 or not os.path.exists(output_srt_path) or os.path.getsize(output_srt_path) < 10:
        raise Exception(f"ffmpeg subtitle extraction failed: {result.stderr[-300:] if result.stderr else 'unknown error'}")
    return True

def extract_subtitle_raw_copy(source_path, subtitle_stream_index, output_path):
    cmd = ["ffmpeg", "-y", "-i", str(source_path), "-map", f"0:s:{subtitle_stream_index}", "-c:s", "copy", str(output_path)]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) < 10:
        raise Exception(f"ffmpeg raw subtitle copy failed: {result.stderr[-300:] if result.stderr else 'unknown error'}")
    return True

def fix_common_ocr_errors(text):
    return text.replace("|", "I")

def ocr_pgs_from_source(source_path, language_code="en", timeout=600):
    cmd = ["pgsrip", "-l", language_code, str(source_path)]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
    base, _ = os.path.splitext(str(source_path))
    expected_srt = f"{base}.{language_code}.srt"
    if not os.path.exists(expected_srt) or os.path.getsize(expected_srt) < 10:
        raise Exception(f"pgsrip produced no usable output: {(result.stderr or result.stdout)[-300:]}")
    with open(expected_srt, "r", encoding="utf-8", errors="replace") as f:
        corrected = fix_common_ocr_errors(f.read())
    with open(expected_srt, "w", encoding="utf-8") as f:
        f.write(corrected)
    return expected_srt

def slugify_for_ia(text, max_len=80):
    text = re.sub(r'[^a-zA-Z0-9\-_.]', '-', text or "")
    text = re.sub(r'-+', '-', text).strip('-_.')
    return (text.lower() or "item")[:max_len]

def upload_to_archive_org(file_path, bucket_hint, key_hint, content_type="application/x-subrip", extension="srt", wait_seconds=60):
    bucket = slugify_for_ia(f"beamplay-subs-{bucket_hint}")
    key = slugify_for_ia(key_hint) + f".{extension}"
    upload_url = f"https://s3.us.archive.org/{bucket}/{key}"
    headers = {
        "authorization": f"LOW {IA_ACCESS_KEY}:{IA_SECRET_KEY}",
        "x-amz-auto-make-bucket": "1", "x-archive-meta-mediatype": "texts",
        "x-archive-meta-collection": "opensource", "x-archive-ignore-preexisting-bucket": "1",
        "Content-Type": content_type,
    }
    with open(file_path, "rb") as fh: data = fh.read()
    response = requests.put(upload_url, data=data, headers=headers, timeout=60)
    if response.status_code not in (200, 201):
        raise Exception(f"Archive.org upload failed: {response.status_code} {response.text[:200]}")
    direct_url = f"https://archive.org/download/{bucket}/{key}"
    attempts = max(1, wait_seconds // 5)
    for _ in range(attempts):
        try:
            check = requests.head(direct_url, timeout=10, allow_redirects=True)
            if check.status_code == 200: return direct_url
        except Exception: pass
        time.sleep(5)
    return direct_url

def upload_to_litterbox(file_path, expire="72h"):
    with open(file_path, "rb") as fh:
        response = requests.post(LITTERBOX_API, data={"reqtype": "fileupload", "time": expire}, files={"fileToUpload": fh}, timeout=30)
    response.raise_for_status()
    url = response.text.strip()
    if not url.startswith("http"): raise Exception(f"Litterbox did not return a URL: {url[:200]}")
    return url

def host_subtitle_everywhere(sub_path, bucket_hint, key_hint, content_type="application/x-subrip", extension="srt"):
    hosted, errors = [], []
    try: hosted.append((upload_to_archive_org(sub_path, bucket_hint, key_hint, content_type=content_type, extension=extension), "Archive.org"))
    except Exception as e: errors.append(f"Archive.org: {e}")
    try: hosted.append((upload_to_litterbox(sub_path), "Litterbox"))
    except Exception as e: errors.append(f"Litterbox: {e}")
    if not hosted: raise Exception(" | ".join(errors))
    return hosted

def prepare_english_subtitle_urls(source_path, subtitle_tracks, bucket_hint, tmp_prefix):
    candidates, failures, srt_overrides = [], [], {}
    english_tracks = [s for s in subtitle_tracks if s["language"] == "English"]
    if not english_tracks: return candidates, failures, srt_overrides

    whole_file_ocr_tried, whole_file_ocr_srt, whole_file_ocr_error = False, None, None

    for idx, sub in enumerate(english_tracks):
        srt_path = os.path.join(TEMP_FOLDER, f"{tmp_prefix}_sub{idx}.srt")
        sup_path = os.path.join(TEMP_FOLDER, f"{tmp_prefix}_sub{idx}.sup")
        srt_err_msg = None
        try:
            extract_subtitle_to_srt(source_path, sub["stream_index"], srt_path)
            hosted = host_subtitle_everywhere(srt_path, bucket_hint, f"{tmp_prefix}_sub{idx}")
            candidates.append({"hosts": hosted, "format": "srt"})
            srt_overrides[sub["stream_index"]] = srt_path
            for url, host in hosted: print(f"         [SUB] English subtitle #{idx+1} (srt) hosted via {host} -> {url}")
            continue
        except Exception as e:
            srt_err_msg = str(e)
            safe_delete(srt_path)

        if not whole_file_ocr_tried:
            whole_file_ocr_tried = True
            try:
                produced_path = ocr_pgs_from_source(source_path, language_code="en")
                shutil.copy(produced_path, srt_path)
                safe_delete(produced_path)
                whole_file_ocr_srt = srt_path
            except Exception as e:
                whole_file_ocr_error = str(e)
                print(f"         [WARN] PGS OCR failed: {e}")
        elif whole_file_ocr_srt:
            shutil.copy(whole_file_ocr_srt, srt_path)

        if whole_file_ocr_srt and os.path.exists(srt_path):
            try:
                hosted = host_subtitle_everywhere(srt_path, bucket_hint, f"{tmp_prefix}_sub{idx}")
                candidates.append({"hosts": hosted, "format": "srt (OCR)"})
                srt_overrides[sub["stream_index"]] = srt_path
                for url, host in hosted: print(f"         [SUB] English subtitle #{idx+1} (OCR'd from PGS) hosted via {host} -> {url}")
                continue
            except Exception as host_err:
                safe_delete(srt_path)
                failures.append(f"track #{idx+1}: OCR succeeded but hosting failed ({host_err})")
                continue

        try:
            extract_subtitle_raw_copy(source_path, sub["stream_index"], sup_path)
            hosted = host_subtitle_everywhere(sup_path, bucket_hint, f"{tmp_prefix}_sub{idx}", content_type="application/octet-stream", extension="sup")
            candidates.append({"hosts": hosted, "format": "sup (OCR failed, raw)"})
            for url, host in hosted: print(f"         [SUB] English subtitle #{idx+1} (raw .sup, OCR failed) hosted via {host} -> {url}")
        except Exception as raw_err:
            failures.append(f"track #{idx+1}: srt failed ({srt_err_msg}); OCR failed ({whole_file_ocr_error}); raw backup failed ({raw_err})")
            print(f"         [WARN] Could not prepare English subtitle #{idx+1} via any method")
        finally:
            safe_delete(sup_path)

    return candidates, failures, srt_overrides

# ============================================================================
# VIDARA & DOWNLOAD
# ============================================================================
def fetch_vidara_upload_server():
    try:
        res = requests.get("https://api.vidara.so/v1/upload/server", params={"api_key": VIDARA_API_KEY}, timeout=30)
        res.raise_for_status()
        data = res.json()
        return data.get("result", {}).get("upload_server") or data.get("upload_server")
    except: return "https://api.vidara.so/v1/upload/server"

def extract_vidara_urls(data):
    full_url = data.get("url") or data.get("result", {}).get("url")
    filecode = data.get("filecode") or data.get("result", {}).get("filecode")
    if not full_url and not filecode: raise Exception(f"Vidara upload returned no url/filecode: {data}")
    if not full_url: full_url = filecode
    if not filecode: filecode = full_url.rstrip("/").split("/")[-1]
    return full_url, filecode

def upload_to_vidara(file_path, custom_name, folder_id=None):
    upload_server = fetch_vidara_upload_server()
    fields = {"api_key": VIDARA_API_KEY}
    with open(file_path, "rb") as fh:
        fields["file"] = (custom_name, fh, "video/x-matroska")
        if folder_id:
            fields["fld_id"] = str(folder_id)
            fields["folder_id"] = str(folder_id)
        encoder = MultipartEncoder(fields=fields)
        monitor = MultipartEncoderMonitor(encoder)
        response = requests.post(upload_server, data=monitor, headers={"Content-Type": monitor.content_type}, timeout=None)
    if response.status_code == 200: return extract_vidara_urls(response.json())
    raise Exception(f"Vidara upload failed: {response.status_code} {response.text[:200]}")

def download_file(url, dest_path):
    cmd = ["aria2c", "-x", "16", "-s", "16", "-j", "16", "-k", "1M", "--file-allocation=none", "--summary-interval=0", "--retry-wait=5", "--max-tries=8", "--timeout=45", "--connect-timeout=15", "--auto-file-renaming=false", "--disable-ipv6=true", "--max-connection-per-server=16", "--min-split-size=1M", "--user-agent=Mozilla/5.0", "-d", os.path.dirname(dest_path), "-o", os.path.basename(dest_path), url]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if result.returncode == 0 and os.path.exists(dest_path) and os.path.getsize(dest_path) > 1024 * 1024: return True
    try:
        if os.path.exists(dest_path): os.remove(dest_path)
        with requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk: f.write(chunk)
        return os.path.exists(dest_path) and os.path.getsize(dest_path) > 1024 * 1024
    except: return False

def safe_delete(path):
    try:
        if path and os.path.exists(path): os.remove(path)
    except: pass

# ============================================================================
# MAIN PIPELINE
# ============================================================================
async def process_row(client, row):
    df_id = row["id"]
    content_type = row["content_type"]
    content_id = row["content_id"]
    tmdb_id = row["tmdb_id"]
    raw_quality = row["quality"] or ""
    channel_msg_id = row["channel_msg_id"]
    file_name = row["file_name"]
    
    q_match = re.search(r'(2160p|1080p|720p|480p|360p)', raw_quality, re.IGNORECASE)
    base_quality = q_match.group(1).lower() if q_match else raw_quality.lower()
    
    links_table = "movie_links" if content_type == "movie" else "episode_links"
    id_column = "movie_id" if content_type == "movie" else "episode_id"
    
    existing_links = turso_query_all(f"SELECT audio_languages FROM {links_table} WHERE {id_column} = ? AND quality = ?", [content_id, base_quality])
    done_langs = set()
    for link_row in existing_links:
        for l in json.loads(link_row["audio_languages"] or "[]"): done_langs.add(l)
            
    print(f"\n*** PROCESSING: {file_name} ***")
    print(f"  Already Done: {list(done_langs)}")
    
    link = await get_download_link(client, channel_msg_id)
    if not link:
        raise Exception("Both F2L and LCU bots failed to return a link.")
    
    temp_path = os.path.join(TEMP_FOLDER, f"row{df_id}_{base_quality}.mkv")
    print(f"  Downloading...")
    if not download_file(link, temp_path):
        raise Exception("Download failed.")
        
    print(f"  Inspecting tracks...")
    audio_tracks, subtitle_tracks = inspect_tracks(temp_path, tmdb_id=tmdb_id)
    print(f"  Found Audio: {[a['language'] for a in audio_tracks]}")
    
    title = ""
    year = None
    season = None
    episode = None
    folder_id = None
    
    if content_type == "movie":
        m_data = turso_query_one("SELECT title, release_year FROM movies WHERE id = ?", [content_id])
        if m_data:
            title = m_data["title"]
            year = m_data["release_year"]
    else:
        ep_data = turso_query_one("SELECT ser.title AS series_title, sea.season_number AS season_number, e.episode_number AS episode_number FROM episodes e JOIN seasons sea ON e.season_id = sea.id JOIN series ser ON e.series_id = ser.id WHERE e.id = ?", [content_id])
        if ep_data:
            title = ep_data["series_title"]
            season = ep_data["season_number"]
            episode = ep_data["episode_number"]

    seen_langs = set()
    
    for track in audio_tracks:
        lang = track["language"]
        if lang in done_langs or lang in seen_langs:
            print(f"  Skipping {lang} (already processed)")
            continue
            
        print(f"  Processing language: {lang}")
        
        # ONLY create folder if we are actually uploading an episode
        if content_type == "episode" and folder_id is None:
            folder_id = get_or_create_vidara_folder(title, season, base_quality)
            
        output_name = build_filename(content_type, title, year, season, episode, base_quality, lang)
        output_path = os.path.join(OUTPUT_FOLDER, output_name)
        
        # Prepare subtitles (OCR if needed)
        sub_candidates, sub_failures, sub_overrides = prepare_english_subtitle_urls(
            temp_path, subtitle_tracks, f"{tmdb_id}", f"row{df_id}_{base_quality}"
        )
        
        remux_single_audio(temp_path, output_path, track, subtitle_tracks, sub_overrides)
        
        # Clean up OCR temp files
        for p in sub_overrides.values(): safe_delete(p)
        
        print(f"  Uploading to Vidara: {output_name}")
        video_url, filecode = upload_to_vidara(output_path, output_name, folder_id)
        safe_delete(output_path)
        
        print(f"  Inserting into DB: {video_url}")
        turso_execute(
            f"INSERT INTO {links_table} ({id_column}, url, quality, audio_languages, created_at) VALUES (?, ?, ?, ?, ?)",
            [content_id, video_url, base_quality, json.dumps([lang]), int(time.time())]
        )
        
        seen_langs.add(lang)
        print(f"  [OK] {lang} done.")
        
    safe_delete(temp_path)
    print(f"*** FINISHED ROW {df_id} ***")
    save_checkpoint(df_id)

async def main():
    print("=" * 60)
    print("BEAM PIPELINE - FULL RUN")
    print("=" * 60)
    
    decode_session()
    checkpoint = get_checkpoint()
    print(f"Current Checkpoint: {checkpoint}")
    
    rows = turso_query_all("SELECT * FROM download_files WHERE id > ? ORDER BY id ASC LIMIT ?", [checkpoint, BATCH_SIZE])
    if not rows:
        print("No new files to process. Exiting.")
        return
        
    client = TelegramClient('beam_session', API_ID, API_HASH)
    await client.start()
    
    for row in rows:
        try:
            await process_row(client, row)
        except Exception as e:
            print(f"\n[ERROR] Failed to process row {row['id']}: {e}")
            print("Stopping pipeline. Will retry this row next run.")
            break
            
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
