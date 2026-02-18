import os
import re
import time
from datetime import datetime, timezone

import dotenv
import requests
from supabase import create_client

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
    # "gamingsetups", "battlestations"
]

VISUAL_SUBS = {
    "unixporn", "Rainmeter", "desksetup", "macsetups", "gamerooms",
    "battlestations", "gamingsetups", "PixelArt", "Outrun", "Cyberpunk"
}

FETCH_VARIANTS = [
    ("top", {"t": "week", "limit": 100}),
    ("new", {"limit": 100}),
]

KEYWORD_PATTERNS = [
    r"\boverlay(?:s)?\b",
    r"\bwidget(?:s)?\b",
    r"\bhud\b",
    r"\btheme(?:s)?\b",
    r"\baesthetic(?:s)?\b",
    r"\bplugin(?:s)?\b",
    r"\btransition(?:s)?\b",
    r"\bstinger(?:s)?\b",
    r"\balert(?:s)?\b",
    r"\bchat\s?box(?:es)?\b",
    r"\bpanel(?:s)?\b",
    r"\bcozy\b",
    r"\bcyberpunk\b",
    r"\boutrun\b",
    r"\bretro\b",
    r"\bpixel\b",
    r"\bsetup(?:s)?\b",
    r"\bstation(?:s)?\b",
    r"\bdesk(?:s)?\b",
    r"\broom(?:s)?\b",
    r"\bvibe(?:s)?\b",
    r"\blayout(?:s)?\b",
    r"\brebrand(?:ing)?\b",
    r"\basset(?:s)?\b",
    r"\bdesign(?:s|er)?\b",
    r"\bvtuber\smodel(?:s)?\b",
    r"\bemote(?:s)?\b",
    r"\bbadge(?:s)?\b",
    r"\bshowcase\b",
    r"\binspiration\b",
]

# Only high-signal support/problem terms to reduce false negatives.
BLACKLIST_PATTERNS = [
    r"\berror(?:s)?\b",
    r"\bcrash(?:es|ed|ing)?\b",
    r"\bbug(?:s)?\b",
    r"\bbroken\b",
    r"\bhow\s+to\s+fix\b",
    r"\bbitrate\b",
    r"\bdropped\s+frames?\b",
    r"\bstutter(?:ing)?\b",
    r"\bdisconnect(?:ed|ion|ing)?\b",
    r"\blogin\b",
    r"\bpassword\b",
    r"\bdriver(?:s)?\b",
    r"\bblack\s+screen\b",
    r"\bblue\s+screen\b",
]

KEYWORD_REGEX = re.compile("|".join(KEYWORD_PATTERNS), re.IGNORECASE)
BLACKLIST_REGEX = re.compile("|".join(BLACKLIST_PATTERNS), re.IGNORECASE)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_best_media_url(post):
    """Pick the best available media URL for downstream visual analysis."""
    gallery_metadata = post.get("media_metadata") or {}
    if post.get("is_gallery") and gallery_metadata:
        for media in gallery_metadata.values():
            source = media.get("s") if isinstance(media, dict) else None
            candidate = source.get("u") if source else None
            if candidate:
                return candidate.replace("&amp;", "&")

    preview_images = ((post.get("preview") or {}).get("images") or [])
    if preview_images:
        source = preview_images[0].get("source") or {}
        preview_url = source.get("url")
        if preview_url:
            return preview_url.replace("&amp;", "&")

    for field in ("url_overridden_by_dest", "url"):
        candidate = post.get(field)
        if candidate:
            return candidate

    return None


def fetch_json_with_backoff(url, headers, params, max_retries=4):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)
            if response.status_code == 429:
                backoff = min(2 ** attempt, 16)
                print(f"Rate limited on {url} with params={params}. Retrying in {backoff}s...")
                time.sleep(backoff)
                continue

            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            if attempt == max_retries - 1:
                print(f"Request failed for {url} params={params}: {exc}")
                return None
            backoff = min(2 ** attempt, 16)
            print(f"Request error for {url} params={params}: {exc}. Retrying in {backoff}s...")
            time.sleep(backoff)
    return None


def should_keep_post(subreddit, full_text):
    is_visual_sub = subreddit in VISUAL_SUBS

    if BLACKLIST_REGEX.search(full_text):
        return False

    if is_visual_sub:
        return True

    return bool(KEYWORD_REGEX.search(full_text))


def map_post(subreddit, fetch_variant, post):
    posted_at = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc).isoformat()
    media_url = get_best_media_url(post)
    post_hint = post.get("post_hint")

    media_type = "text"
    if post.get("is_gallery"):
        media_type = "gallery"
    elif post_hint in {"image", "link", "hosted:video", "rich:video"}:
        media_type = post_hint
    elif media_url:
        media_type = "media"

    preview_images = ((post.get("preview") or {}).get("images") or [])
    thumbnail = None
    if preview_images:
        thumbnail = ((preview_images[0].get("source") or {}).get("url") or "").replace("&amp;", "&") or None

    return {
        "source_platform": "reddit",
        "external_id": post["id"],
        "title": post.get("title", ""),
        "content": post.get("selftext", "")[:2000],
        "url": f"https://reddit.com{post.get('permalink', '')}",
        "author_name": f"r/{subreddit}",
        "posted_at": posted_at,
        "engagement_score": post.get("score", 0) + post.get("num_comments", 0),
        "metadata": {
            "subreddit": subreddit,
            "fetch_variant": fetch_variant,
            "upvotes": post.get("score", 0),
            "comments": post.get("num_comments", 0),
            "upvote_ratio": post.get("upvote_ratio", 0),
            "is_self": post.get("is_self", False),
            "post_hint": post_hint,
            "is_gallery": post.get("is_gallery", False),
            "media_url": media_url,
            "media_type": media_type,
            "thumbnail": thumbnail or post.get("thumbnail"),
            "url_overridden_by_dest": post.get("url_overridden_by_dest"),
        },
        "raw_data": post,
    }


def fetch_reddit_posts(subreddit):
    headers = {"User-Agent": "python:trend-hunter:v1.1 (by /u/ConfidentSession1009)"}
    base_url = f"https://www.reddit.com/r/{subreddit}"

    deduped = {}
    for listing, params in FETCH_VARIANTS:
        listing_url = f"{base_url}/{listing}.json"
        data = fetch_json_with_backoff(listing_url, headers, params)
        if not data:
            continue

        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            full_text = f"{post.get('title', '')} {post.get('selftext', '')}".lower()
            if not should_keep_post(subreddit, full_text):
                continue

            mapped = map_post(subreddit, listing, post)
            deduped[mapped["external_id"]] = mapped

    return list(deduped.values())


def main():
    print("Starting Reddit Collection...")
    for sub in SUBREDDITS:
        posts = fetch_reddit_posts(sub)
        if posts:
            try:
                supabase.table("social_inputs").upsert(
                    posts,
                    on_conflict="source_platform, external_id",
                    ignore_duplicates=False,
                ).execute()
                print(f"Saved {len(posts)} posts from r/{sub}")
            except Exception as exc:
                print(f"DB Error for r/{sub}: {exc}")
        time.sleep(2)


if __name__ == "__main__":
    main()
