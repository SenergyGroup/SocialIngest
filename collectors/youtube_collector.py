import os
import time
from datetime import datetime, timezone
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from supabase import create_client
import dotenv

dotenv.load_dotenv()

# --- CONFIGURATION ---
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# List of Channel IDs (Not the @name, the ID starting with UC)
# These are top channels for Streaming Tech, OBS, and Desk Setups
TARGET_CHANNELS = [
    "UCVpO-u5394IXxcsLfRXsrMQ", # Harris Heller (Senpai Gaming)
    "UCRBHiacaQb5S70pljtJYB2g", # EposVox (The OBS Guy)
    "UCI5t_ve3cr5a1_3rrmbp6jQ", # Nutty (Advanced Stream widgets)
    "UCrCriLCMUusVqHVtONIBnXg", # Stream Scheme
    "UChnN9MPURwKV2PbEoT2vhTQ", # RandomFrankP (Desk Setups)
    "UChIZGfcnjHI0DG4nweWEduw", # TechSource (Setup Wars)
    "UCXKNiazqmuUi9CeX_kyDpjw", # Alpha Beta Gamer
    "UC4vxRjQ0R7vWWKjlpFpt4Tg", # Gael LEVEL
    "UCXKNiazqmuUi9CeX_kyDpjw", # Gaming Careers
    "UCATWC1JSlhzmYeDbjnS8WwA", # Senpai Gaming
]

KEYWORDS = [
    "overlay", "widget", "hud", "theme", "aesthetic", "plugin", 
    "obs", "transition", "stinger", "alert", "chatbox", "panels", 
    "setup", "desk", "room", "tour", "vibe", "cozy", "minimal"
]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_channel_uploads_id(youtube, channel_id):
    """Get the ID of the 'Uploads' playlist for a channel."""
    try:
        request = youtube.channels().list(
            part="contentDetails,snippet",
            id=channel_id,
            maxResults=1,
        )
        response = request.execute()
    except HttpError as e:
        print(f"[channels] HttpError for {channel_id}: {e}")
        return None, None

    items = response.get('items')
    if not items:
        print(f"[channels] No items for {channel_id}. Raw response: {response}")
        return None, None
        
    uploads_id = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    channel_name = response['items'][0]['snippet']['title']
    return uploads_id, channel_name

def get_recent_videos(youtube, playlist_id, limit=5):
    """Get the last X videos from a playlist."""
    request = youtube.playlistItems().list(
        part="snippet,contentDetails",
        playlistId=playlist_id,
        maxResults=limit
    )
    response = request.execute()
    return response.get('items', [])

def get_video_stats(youtube, video_ids):
    if not video_ids:
        return {}

    try:
        request = youtube.videos().list(
            part="statistics",
            id=",".join(video_ids)
        )
        response = request.execute()
    except HttpError as e:
        print(f"[videos] HttpError for IDs {video_ids}: {e}")
        return {}

    items = response.get('items', [])
    if not items:
        print(f"[videos] No items for IDs {video_ids}. Raw response: {response}")
        return {}

    stats = {}
    for item in items:
        stats[item['id']] = item['statistics']
    return stats

def main():
    if not YOUTUBE_API_KEY:
        print("Error: YOUTUBE_API_KEY not found.")
        return

    print("--- Starting YouTube Collection ---")
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    
    all_videos = []

    for channel_id in TARGET_CHANNELS:
        try:
            # 1. Get Uploads Playlist
            uploads_id, channel_name = get_channel_uploads_id(youtube, channel_id)
            if not uploads_id:
                continue
                
            print(f"Checking {channel_name}...")
            
            # 2. Get Recent Videos
            videos = get_recent_videos(youtube, uploads_id, limit=5)
            
            # 3. Filter by Keyword (Save quota by filtering BEFORE fetching stats)
            relevant_videos = []
            for v in videos:
                title = v['snippet']['title']
                desc = v['snippet']['description']
                full_text = (title + " " + desc).lower()
                
                if any(k in full_text for k in KEYWORDS):
                    relevant_videos.append(v)
            
            if not relevant_videos:
                continue

            # 4. Get Stats for relevant videos only
            video_ids = [v['contentDetails']['videoId'] for v in relevant_videos]
            stats_map = get_video_stats(youtube, video_ids)

            # 5. Map to Schema
            for v in relevant_videos:
                vid = v['contentDetails']['videoId']
                stats = stats_map.get(vid, {})
                
                # Metrics
                views = int(stats.get('viewCount', 0))
                likes = int(stats.get('likeCount', 0))
                comments = int(stats.get('commentCount', 0))
                
                # Weighting: YouTube views are inflated compared to Reddit upvotes.
                # We divide views by 100 to make the "Engagement Score" comparable across platforms.
                normalized_score = (views // 100) + likes + comments

                # Date Formatting
                published_at_raw = v['snippet']['publishedAt'] # Already ISO format
                
                all_videos.append({
                    "source_platform": "youtube",
                    "external_id": vid,
                    "title": v['snippet']['title'],
                    "content": v['snippet']['description'][:2000],
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "author_name": channel_name,
                    "posted_at": published_at_raw,
                    
                    "engagement_score": normalized_score,
                    
                    "metadata": {
                        "channel_id": channel_id,
                        "views": views,
                        "likes": likes,
                        "thumbnail": v['snippet']['thumbnails']['high']['url']
                    },
                    "raw_data": v # Optional backup
                })
                
        except Exception as e:
            print(f"Error processing {channel_id}: {e}")

    # 6. Save to Supabase
    if all_videos:
        try:
            supabase.table("social_inputs").upsert(
                all_videos, 
                on_conflict="source_platform, external_id",
                ignore_duplicates=False
            ).execute()
            print(f"✅ Saved {len(all_videos)} YouTube videos.")
        except Exception as e:
            print(f"DB Error: {e}")
    else:
        print("No relevant videos found this run.")

if __name__ == "__main__":
    main()