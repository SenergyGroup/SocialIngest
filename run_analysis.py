import os
from supabase import create_client
from analysis.clustering import cluster_posts
from analysis.llm_generator import analyze_trend # <--- NEW IMPORT
import dotenv

dotenv.load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

PRODUCT_SUFFIXES = [
    "Stream Overlay",
    "Twitch Chat Widget",
    "Stream Alerts"
]

def fetch_recent_unprocessed_posts():
    """Fetch raw social inputs."""
    # We fetch a larger batch (e.g. 500) to ensure the 't=week' data has density.
    # We sort by engagement to ensure the 'Viral' post calculation is accurate.
    response = supabase.table("social_inputs")\
        .select("*")\
        .order("engagement_score", desc=True)\
        .limit(500)\
        .execute()
        
    return response.data

def main():
    print("--- Starting Trend Analysis ---")
    
    # 1. Get Data
    raw_posts = fetch_recent_unprocessed_posts()
    print(f"Fetched {len(raw_posts)} raw posts from Supabase.")
    
    if not raw_posts:
        print("No data found. Run the collectors first.")
        return

    # 2. Format for Clustering
    # We strip it down to just the text and ID for the math part.
    clustering_input = []
    for p in raw_posts:
        text_content = f"{p.get('title', '')} {p.get('content', '')}"
        clustering_input.append({
            'id': p['id'],
            'text': text_content,
            'engagement': p.get('engagement_score', 0),
            'source': p.get('source_platform')
        })

    # 3. Run Math (Clustering + Centroid Finding)
    # This now adds the 'is_centroid' flag to the posts
    clusters = cluster_posts(clustering_input)
    
    # 4. Review & Analyze
    for cluster_id, posts in clusters.items():
        print(f"\nProcessing Cluster #{cluster_id} ({len(posts)} posts)...")
        
        # Debug: Print the center vs the top
        center_post = next((p for p in posts if p.get('is_centroid')), posts[0])
        
        # FIX: Process text outside the f-string to avoid backslash error
        c_text = center_post['text'][:60].replace('\n', ' ')
        t_text = posts[0]['text'][:60].replace('\n', ' ')
        
        print(f"   Centroid (Vibe): {c_text}...")
        print(f"   Top Post (Viral): {t_text}...")
        
        # 5. Send to AI
        trend_data = analyze_trend(posts)
        
        if trend_data and trend_data.get('valid'):
            print(f"✅ VALID TREND: {trend_data['trend_name']}")
            print(f"   Core Vibe: {trend_data['aesthetic_keywords']}")
            
            try:
                # A. Insert Trend Parent
                trend_res = supabase.table("trends").insert({
                    "summary": f"{trend_data['trend_name']}: {trend_data['summary']}",
                    "source_platform": "aggregated"
                }).execute()
                
                if trend_res.data:
                    trend_id = trend_res.data[0]['id']
                    
                    # B. GENERATE SEARCHES PROGRAMMATICALLY
                    # logic: Aesthetic + Suffix
                    actions_payload = []
                    base_term = trend_data['aesthetic_keywords']
                    
                    for suffix in PRODUCT_SUFFIXES:
                        # e.g. "Neon Glitch Cyberpunk" + " " + "Stream Overlay"
                        final_phrase = f"{base_term} {suffix}"
                        
                        actions_payload.append({
                            "trend_id": trend_id,
                            "search_phrase": final_phrase,
                            "status": "PENDING"
                        })
                        print(f"   -> Queueing: {final_phrase}")
                    
                    if actions_payload:
                        supabase.table("search_actions").insert(actions_payload).execute()
                        
            except Exception as e:
                print(f"   -> DB Error: {e}")
                
        else:
            print("❌ Ignored (Noise/Irrelevant)")

if __name__ == "__main__":
    main()