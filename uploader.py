import os
import re
import json
import datetime
import subprocess
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

CLIENT_ID = "546480239670-" + "ogm0nio8rj9mmq3ra4hiprs85h1lpods" + ".apps.googleusercontent.com"
CLIENT_SECRET = "GOCSPX-" + "fIbl82ugB74Mum7WvCMskf-oaowm"
REDIRECT_URI = "http://localhost:8080/"

AUTH_CODE = "4/0AXlqoi45X-tQmDMFzGZ_fhSbcbuVFGvjwBXkjrM8EiaeGPUNK9iXqSebreDSdsWWpSw2QQ"
TOKEN_CACHE_FILE = "google_token.json"

TRACKER_FILE = "uploaded_shorts.json"
TIKTOK_PROFILE_URL = "https://www.tiktok.com/@the.qayyum8"
MAX_DAILY_UPLOADS = 5

def get_credentials():
    # 1. Saved token check karein
    if os.path.exists(TOKEN_CACHE_FILE):
        try:
            with open(TOKEN_CACHE_FILE, "r") as f:
                token_data = json.load(f)
            refresh_tok = token_data.get("refresh_token")
            if refresh_tok:
                creds = Credentials(
                    None,
                    refresh_token=refresh_tok,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=CLIENT_ID,
                    client_secret=CLIENT_SECRET,
                    scopes=["https://www.googleapis.com/auth/youtube.upload"]
                )
                return creds
        except Exception as e:
            print(f"Token cache read error: {e}")

    # 2. Agar token file na mile to authorization code se token exchange karein
    print("Step 0: Generating Refresh Token...")
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": AUTH_CODE,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI
        },
        timeout=25
    )
    data = resp.json()
    refresh_tok = data.get("refresh_token")
    if not refresh_tok:
        print("Token exchange error:", data)
        exit(1)

    with open(TOKEN_CACHE_FILE, "w") as f:
        json.dump(data, f)

    creds = Credentials(
        None,
        refresh_token=refresh_tok,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    return creds

creds = get_credentials()
youtube = build('youtube', 'v3', credentials=creds)

if os.path.exists(TRACKER_FILE):
    try:
        with open(TRACKER_FILE, "r") as f:
            uploaded_ids = set(json.load(f))
    except Exception:
        uploaded_ids = set()
else:
    uploaded_ids = set()

print(f"Step 1: yt-dlp ke zariye TikTok profile scan ho rahi hai: {TIKTOK_PROFILE_URL}...")

cmd_extract = [
    "yt-dlp",
    "--flat-playlist",
    "--playlist-end", "20",
    "-J",
    TIKTOK_PROFILE_URL
]

res = subprocess.run(cmd_extract, capture_output=True, text=True)
if res.returncode != 0:
    print(f"Extraction error: {res.stderr}")
    exit(1)

try:
    data = json.loads(res.stdout)
    entries = data.get("entries", [])
except Exception as e:
    print(f"JSON Parsing error: {e}")
    exit(1)

if not entries:
    print("Profile par koi video nahi mili.")
    exit(0)

# Filter out already uploaded videos
pending_videos = []
for item in entries:
    v_id = str(item.get("id"))
    if v_id and v_id not in uploaded_ids:
        pending_videos.append(item)

if not pending_videos:
    print("Koi nayi video nahi mili. Sab pehle se upload ho chuki hain.")
    exit(0)

to_upload = pending_videos[:MAX_DAILY_UPLOADS]
print(f"Nayi Videos Mili: {len(pending_videos)}. Aaj upload hone ke liye chuni gayi: {len(to_upload)}")

now_utc = datetime.datetime.now(datetime.timezone.utc)

for idx, item in enumerate(to_upload):
    video_id = str(item.get("id"))
    video_url = item.get("url") or f"https://www.tiktok.com/@the.qayyum8/video/{video_id}"
    raw_title = item.get("title", "").strip() or f"Shorts #{video_id[-4:]}"

    clean_title = re.sub(r'[\r\n]+', ' ', raw_title)
    if "#shorts" not in clean_title.lower():
        clean_title = f"{clean_title[:85]} #Shorts"
    clean_title = clean_title[:100]

    local_file = f"short_{idx+1}.mp4"
    if os.path.exists(local_file):
        os.remove(local_file)

    print(f"\n[{idx+1}/{len(to_upload)}] Downloading TikTok video: {clean_title}...")
    dl_cmd = [
        "yt-dlp",
        "-f", "best[ext=mp4]/best",
        "-o", local_file,
        video_url
    ]
    subprocess.run(dl_cmd, check=True)

    file_size_mb = os.path.getsize(local_file) / (1024 * 1024)
    print(f"Downloaded ({file_size_mb:.2f} MB). Scheduling upload...")

    # idx == 0: Foran Public
    # idx > 0: Har agli video pichli se 2 ghante baad schedule
    if idx == 0:
        status_body = {'privacyStatus': 'public'}
        print("Status: FORAN PUBLIC HOGI")
    else:
        scheduled_time = now_utc + datetime.timedelta(hours=(idx * 2))
        iso_schedule = scheduled_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        status_body = {
            'privacyStatus': 'private',
            'publishAt': iso_schedule
        }
        print(f"Status: Auto-Schedule hogi (Time: {iso_schedule}) [Pehli se {idx*2} ghante baad]")

    body = {
        'snippet': {
            'title': clean_title,
            'description': f"{clean_title}\n\nOriginal Creator: @the.qayyum8\n\n#Shorts #viral #tiktok",
            'tags': ["Shorts", "TikTok", "the.qayyum8", "viral", "trending"],
            'categoryId': '24'
        },
        'status': status_body
    }

    media = MediaFileUpload(local_file, chunksize=-1, resumable=True, mimetype='video/mp4')
    upload_req = youtube.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=media
    )
    upload_res = upload_req.execute()
    new_yt_id = upload_res.get("id")
    print(f"Upload Success! Link: https://youtube.com/shorts/{new_yt_id}")

    uploaded_ids.add(video_id)
    with open(TRACKER_FILE, "w") as f:
        json.dump(list(uploaded_ids), f, indent=2)

    if os.path.exists(local_file):
        os.remove(local_file)

print("\nAaj ki 5 Shorts upload/schedule ho chuki hain!")
