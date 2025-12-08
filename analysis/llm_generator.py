import os
from openai import OpenAI
from pydantic import BaseModel, Field
import dotenv

dotenv.load_dotenv()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# --- 1. Define the Rigid Structure ---
class TrendAnalysis(BaseModel):
    valid: bool = Field(
        description="True if this cluster is at all useful for visual/aesthetic trends, even if mixed with other topics."
    )
    relevance_score: int = Field(
        description="0 to 100. 0 = no visual relevance, 100 = extremely strong visual aesthetic signal."
    )
    trend_name: str = Field(description="Short name (e.g. 'Cozy Mushroom Battlestation').")
    summary: str = Field(description="1-sentence explanation of the visual trend.")
    aesthetic_keywords: str = Field(
        description="The core descriptive visual keywords. NO product names."
    )

def analyze_trend(cluster_posts):
    """
    Returns: Dict with 'aesthetic_keywords' to be used for suffixing.
    """
    if not cluster_posts:
        return None
    
     # --- 2. Smart Selection ---
    # Find the "Centroid" (The Definition)
    centroid_post = next((p for p in cluster_posts if p.get('is_centroid')), cluster_posts[0])
    
    # Find the "Viral" (The Proof)
    # Ensure sorted by engagement in the clustering step, or sort here just in case
    sorted_posts = sorted(cluster_posts, key=lambda x: x.get('engagement', 0), reverse=True)
    top_post = sorted_posts[0]
    
    # Pick a secondary viral post if the top one is the same as the centroid
    if top_post['id'] == centroid_post['id'] and len(sorted_posts) > 1:
        viral_post = sorted_posts[1]
    else:
        viral_post = top_post

    context_text = (
        f"POST A (Definition):\n{centroid_post['text'][:600]}\n\n"
        f"POST B (Viral):\n{viral_post['text'][:600]}"
    )

    system_prompt = """
    You are a Design Trend Scout for streaming and gaming.

    Your job: decide if this cluster of posts contains a **visual aesthetic or vibe** that could inform
    the look of stream overlays, alerts, chat widgets, thumbnails, or streaming setups.

    RULES:

    1) Set valid=True if ANY of the following are clearly present in the posts:
    - Gaming / streaming setups, battlestations, desks, rooms, workspaces, PC builds.
    - Desktop / OS themes (Hyprland, XFCE themes, wallpapers, icons, UI skins).
    - Cozy / cute / dark / cyberpunk / retro / minimal / RGB style descriptions.
    - Pixel art, game art, VTuber model design, character design, thumbnails.
    - Tutorials or guides about making overlays, stream graphics, or channel visuals.

    Even if the post also includes tips, deals, feedback requests, or self-promo,
    it is STILL valid as long as there is a visual style or setup being shown or described.

    - relevance_score:
    * 0-20: basically no visuals.
    * 21-60: some visuals but mixed with other stuff.
    * 61-100: strong visual aesthetic / repeated pattern.
    - If relevance_score >= 50, set valid=True.

    2) Set valid=False ONLY if the posts are basically:
    - Tech support, bug reports, crashes.
    - Pure growth/strategy/career advice with NO meaningful description
        of visuals, setups, rooms, art, themes, thumbnails, etc.
    - Generic promo / sales / deals with no aesthetic described.

    3) When you are unsure, default to valid=True.

    4) aesthetic_keywords:
    - Focus ONLY on core visual words and short phrases, NOT product names.
    - Examples of good outputs: "Cozy Pastel Desk Setup", "Neon RGB Cyberpunk",
        "Minimal Black-and-White Battlestation", "Soft Cottagecore Cozy Game UI",
        "Pixel Art Retro Icons".
    - Strip out words like "overlay", "stream", "widget", "tutorial", "deal".

    Respond using the TrendAnalysis schema.
    """


    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context_text}
            ],
            response_format=TrendAnalysis,
        )
        result = completion.choices[0].message.parsed
        if not result.valid:
            return None
        return result.model_dump()

    except Exception as e:
        print(f"LLM Error: {e}")
        return None