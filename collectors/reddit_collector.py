import requests
import os
import time
from datetime import datetime
from supabase import create_client
import dotenv

dotenv.load_dotenv()

# Config
SUBREDDITS = [
    "Twitch", "OBS", "streaming", "NewTubers", 
    "VirtualYoutubers", "vtubers", "LivestreamFail", 
    "GirlGamers", "Twitch_Startup", "streamup",
    "desksetup", "macsetups",
    "unixporn", "Rainmeter",
    "CozyGamers", "PixelArt", "Cyberpunk", "Outrun",
    "gamerooms", "StreamOverlaysArt",
    #  "gamingsetups", "battlestations"
]

# Keep any post that contains at least one of these
KEYWORDS = [
    "overlay", "widget", "hud", "theme", "aesthetic", "plugin", 
    "transition", "stinger", "alert", "chatbox", "panels", 
    "cozy", "cyberpunk", "layout", "rebrand", "debut", "subathon",
    "panels", "layout", "rebrand", "assets", "design", "vtuber model", 
    "emotes", "badges", "showcase", "inspiration", "cozy", 
    "cyberpunk", "retro", "pixel",
    "setup", "station", "desk", "room", "vibe",
    "screen", "monitor", "display", "custom", "look"
]

# BLACKLIST: Added "Tech Support" triggers.
BLACKLIST = [
    # Support Verbs/Nouns
    "help", "issue", "broken", "fix", "error", "bug", "crash", "lag", 
    "fps", "drop", "quality", "audio", "mic", "microphone", "camera", 
    "webcam", "connection", "bitrate", "disconnect", "login", "account",
    "password", "hack", "ban", "drama", "controversy", "stutter",
    "black screen", "blue screen", "update", "drivers", "specs", "pc build",
    "keyboard", "mouse", "headset" # Hardware support
]

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def fetch_reddit_json(subreddit):
    url = f"https://www.reddit.com/r/{subreddit}/top.json?t=week&limit=100"
    headers = {'User-Agent': 'python:trend-hunter:v1.0 (by /u/ConfidentSession1009)'}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return []
            
        data = response.json()
        clean_posts = []
        
        for child in data['data']['children']:
            p = child['data']
            
            # 1. Filter
            full_text = (p.get('title', '') + " " + p.get('selftext', '')).lower()
            if not any(k in full_text for k in KEYWORDS):
                continue 

            if any(b in full_text for b in BLACKLIST):
                continue

            # 2. Map to Unified Schema
            # Convert Reddit timestamp (Unix) to Postgres Timestamp
            posted_at = datetime.fromtimestamp(p['created_utc']).isoformat()
            
            clean_posts.append({
                "source_platform": "reddit",
                "external_id": p['id'],
                "title": p['title'],
                "content": p.get('selftext', '')[:2000],
                "url": f"https://reddit.com{p['permalink']}",
                "author_name": f"r/{subreddit}",
                "posted_at": posted_at,
                
                # Metric Calculation
                "engagement_score": p.get('score', 0) + p.get('num_comments', 0),
                
                # The Backpack (Specifics)
                "metadata": {
                    "subreddit": subreddit,
                    "upvotes": p.get('score', 0),
                    "comments": p.get('num_comments', 0),
                    "upvote_ratio": p.get('upvote_ratio', 0)
                },
                
                # Full fidelity backup (Optional, remove if saving space)
                "raw_data": p 
            })
        return clean_posts
        
    except Exception as e:
        print(f"Error scraping r/{subreddit}: {e}")
        return []

def main():
    print("Starting Reddit Collection...")
    for sub in SUBREDDITS:
        posts = fetch_reddit_json(sub)
        if posts:
            try:
                # Upsert to Supabase
                supabase.table("social_inputs").upsert(
                    posts, on_conflict="source_platform, external_id",
                    ignore_duplicates=False
                ).execute()
                print(f"Saved {len(posts)} posts from r/{sub}")
            except Exception as e:
                print(f"DB Error: {e}")
        time.sleep(2)

if __name__ == "__main__":
    main()