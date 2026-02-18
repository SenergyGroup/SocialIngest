import os
from supabase import create_client
from analysis.clustering import cluster_posts
from analysis.llm_generator import analyze_trend
import dotenv

dotenv.load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Changed: only generate "Chat Widget" searches (no overlay/alerts)
PRODUCT_SUFFIX = "Chat Widget"

def fetch_recent_unprocessed_posts():
    """Fetch raw social inputs."""
    response = supabase.table("social_inputs")\
        .select("*")\
        .order("engagement_score", desc=True)\
        .limit(500)\
        .execute()
    return response.data

def main():
    print("--- Starting Trend Analysis ---")

    raw_posts = fetch_recent_unprocessed_posts()
    print(f"Fetched {len(raw_posts)} raw posts from Supabase.")

    if not raw_posts:
        print("No data found. Run the collectors first.")
        return

    clustering_input = []
    for p in raw_posts:
        text_content = f"{p.get('title', '')} {p.get('content', '')}"
        clustering_input.append({
            "id": p["id"],
            "text": text_content,
            "engagement": p.get("engagement_score", 0),
            "source": p.get("source_platform"),
        })

    clusters = cluster_posts(clustering_input)

    for cluster_id, posts in clusters.items():
        print(f"\nProcessing Cluster #{cluster_id} ({len(posts)} posts)...")

        center_post = next((p for p in posts if p.get("is_centroid")), posts[0])

        c_text = center_post["text"][:60].replace("\n", " ")
        t_text = posts[0]["text"][:60].replace("\n", " ")

        print(f"   Centroid (Vibe): {c_text}...")
        print(f"   Top Post (Viral): {t_text}...")

        trend_data = analyze_trend(posts)

        if trend_data and trend_data.get("valid"):
            print(f"✅ VALID TREND: {trend_data['trend_name']}")
            print(f"   Core Vibe: {trend_data['aesthetic_keywords']}")

            try:
                trend_res = supabase.table("trends").insert({
                    # trend_name already comes back as "<Aesthetic> Chat Widget" after your llm_generator change
                    "summary": f"{trend_data['trend_name']}: {trend_data['summary']}",
                    "source_platform": "aggregated",
                }).execute()

                if trend_res.data:
                    trend_id = trend_res.data[0]["id"]

                    # Changed: use the aesthetic name as the base term for search phrases
                    # (keywords often become a long list; the name is cleaner for search and consistency)
                    base_term = trend_data["trend_name"]

                    final_phrase = f"{base_term} {PRODUCT_SUFFIX}"

                    actions_payload = [{
                        "trend_id": trend_id,
                        "search_phrase": final_phrase,
                        "status": "PENDING",
                    }]

                    supabase.table("search_actions").insert(actions_payload).execute()
                    print(f"   -> Queueing: {final_phrase}")

            except Exception as e:
                print(f"   -> DB Error: {e}")

        else:
            print("❌ Ignored (Noise/Irrelevant)")

if __name__ == "__main__":
    main()
