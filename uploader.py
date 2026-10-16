import os
import re
import json
import datetime
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

CLIENT_ID = "546480239670-" + "ogm0nio8rj9mmq3ra4hiprs85h1lpods" + ".apps.googleusercontent.com"
CLIENT_SECRET = "GOCSPX-" + "fIbl82ugB74Mum7WvCMskf-oaowm"
REDIRECT_URI = "http://localhost:8080/"

# Authorization Code jo aapne share kiya:
AUTH_CODE = "4/0AXlqoi5jIZWDYdRamp0Rqj-uJJ06GHN46HA65KDhlwGdHfRnwBwrkXPQ4KDaqjWWHAUBgw"
TOKEN_CACHE_FILE = "google_token.json"

TRACKER_FILE = "uploaded_shorts.json"
TIKTOK_USERNAME = "the.qayyum8"
MAX_DAILY_UPLOADS = 5

def get_credentials():
    creds = None
    # Agar pehle se token save hai to wahan se uthana
    if os.path.exists(TOKEN_CACHE_FILE):
        try:
            with open(TOKEN_CACHE_FILE, "r") as f:
                token_data = json.load(f)
            creds = Credentials(
                None,
                refresh_token=token_data.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET,
                scopes=["https://www.googleapis.com/auth/youtube.upload"]
            )
            return creds
        except Exception:
            pass

    # Pehli martaba authorization code se tokens generate karna
    print("Exchanging authorization code for tokens...")
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": AUTH_CODE,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI
        },
        timeout=20
    )
    data = resp.json()
    if "refresh_token" not in data and "access_token" not in data:
        print("Token exchange error:", data)
        exit(1)

    with open(TOKEN_CACHE_FILE, "w") as f:
        json.dump(data, f)

    creds = Credentials(
        None,
        refresh_token=data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    return creds

creds = get_credentials()
youtube = build('youtube', 'v3', credentials=creds)

# State Tracker Load
if os.path.exists(TRACKER_FILE):
    try:
        with open(TRACKER_FILE, "r") as f:
            uploaded_ids = set(json.load(f))
    except Exception:
        uploaded_ids = set()
else:
    uploaded_ids = set()

print(f"Step 1: TikTok account @{TIKTOK_USERNAME} se taaza videos fetch ho rahi hain...")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
api_url = f"https://www.tikwm.com/api/user/posts?unique_id={TIKTOK_USERNAME}&count=20"
resp = requests.get(api_url, headers=headers, timeout=25)

if resp.status_code != 200:
    print(f"Feed error: {resp.status_code}")
    exit(1)

posts = resp.json().get("data", {}).get("videos", [])
if not posts:
    print("Account par koi video nahi mili.")
    exit(0)

# Sirf un-uploaded videos filter karna
pending_videos = []
for post in posts:
    vid_id = str(post.get("video_id"))
    if vid_id not in uploaded_ids:
        pending_videos.append(post)

if not pending_videos:
    print("Koi nayi video nahi mili. Sab pehle hi upload ho chuki hain.")
    exit(0)

to_upload = pending_videos[:MAX_DAILY_UPLOADS]
print(f"Total Nayi Videos: {len(pending_videos)}. Aaj upload hone ke liye chuni gayi: {len(to_upload)}")

now_utc = datetime.datetime.now(datetime.timezone.utc)

for idx, post in enumerate(to_upload):
    video_id = str(post.get("video_id"))
    raw_title = post.get("title", "").strip() or f"Shorts #{video_id[-4:]}"
    
    clean_title = re.sub(r'[\r\n]+', ' ', raw_title)
    if "#shorts" not in clean_title.lower():
        clean_title = f"{clean_title[:85]} #Shorts"
    clean_title = clean_title[:100]

    video_stream_url = post.get("play")
    if not video_stream_url.startswith("http"):
        video_stream_url = f"https://www.tikwm.com{video_stream_url}"

    local_file = f"short_{idx+1}.mp4"
    if os.path.exists(local_file):
        os.remove(local_file)

    print(f"\n[{idx+1}/{len(to_upload)}] Video Download ho rahi hai: {clean_title}...")
    with requests.get(video_stream_url, stream=True, timeout=60) as dl:
        dl.raise_for_status()
        with open(local_file, "wb") as f:
            for chunk in dl.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    file_size_mb = os.path.getsize(local_file) / (1024 * 1024)
    print(f"Downloaded ({file_size_mb:.2f} MB). Setup scheduling...")

    # Scheduling Logic:
    # idx == 0: Foran Public
    # idx > 0: Har agli video pichli se 2 ghante baad schedule (private + publishAt)
    if idx == 0:
        status_body = {
            'privacyStatus': 'public'
        }
        print("Status: FORAN PUBLIC HOGI")
    else:
        scheduled_time = now_utc + datetime.timedelta(hours=(idx * 2))
        iso_schedule = scheduled_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        status_body = {
            'privacyStatus': 'private',
            'publishAt': iso_schedule
        }
        print(f"Status: Auto-Schedule hogi (UTC Time: {iso_schedule}) [Pehli se {idx*2} ghante baad]")

    body = {
        'snippet': {
            'title': clean_title,
            'description': f"{clean_title}\n\nOriginal Creator: @{TIKTOK_USERNAME}\n\n#Shorts #viral #tiktok",
            'tags': ["Shorts", "TikTok", TIKTOK_USERNAME, "viral", "trending"],
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

print("\nAaj ki 5 Shorts kamyabi se process ho chuki hain!")
