# analysis/llm_generator.py

import os
import dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

dotenv.load_dotenv()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


class TrendAnalysis(BaseModel):
    valid: bool = Field(
        description="True only if the cluster contains a coherent, nameable visual aesthetic (not just a topic)."
    )
    relevance_score: int = Field(
        description="0 to 100. 0 = no visual relevance, 100 = extremely strong, cohesive visual aesthetic signal."
    )
    trend_name: str = Field(
        description=(
            "2-5 word AESTHETIC NAME ONLY. Do NOT include words like 'chat widget', 'overlay', 'alert', "
            "'stream', 'streaming', 'setup', 'tutorial', 'pack', 'theme'. "
            "Example: 'Cozy Pixel Farm'."
        )
    )
    summary: str = Field(
        description=(
            "1 sentence describing the visual aesthetic. Do NOT mention 'chat widget', 'overlay', or 'alert'."
        )
    )
    aesthetic_keywords: str = Field(
        description=(
            "3-8 short phrases describing the look (palette/texture/typography/era). "
            "NO product names. Do NOT include words like 'overlay', 'widget', 'alert', 'stream', 'tutorial'."
        )
    )


def _sanitize_trend_name(name: str) -> str:
    """
    Defensive cleanup in case the model still includes banned product-ish tokens.
    Keeps the aesthetic name plain so suffixing can be done in run_analysis.py.
    """
    if not name:
        return name

    s = " ".join(name.strip().split())  # normalize whitespace
    lowered = s.lower()

    banned_phrases = [
        "chat widget",
        "twitch chat widget",
        "stream overlay",
        "overlay",
        "stream alerts",
        "alerts",
        "alert",
        "streaming",
        "stream",
        "tutorial",
        "setup",
        "pack",
        "theme",
        "widget",
    ]

    # Remove any banned phrase occurrences (simple, pragmatic)
    for b in banned_phrases:
        if b in lowered:
            parts = lowered.split(b)
            lowered = " ".join(p.strip() for p in parts if p.strip())

    # If we nuked too much, fall back to the original string
    cleaned = " ".join(lowered.split()).strip()
    if not cleaned:
        cleaned = s

    # Title case for nicer DB display (optional)
    cleaned = cleaned.title()

    # Hard cap to avoid run-on names
    words = cleaned.split()
    if len(words) > 6:
        cleaned = " ".join(words[:6])

    return cleaned


def analyze_trend(cluster_posts):
    """
    Returns a dict of TrendAnalysis fields if valid, else None.
    trend_name is returned as aesthetic-only (no suffix).
    """
    if not cluster_posts:
        return None

    # --- Smart Selection ---
    centroid_post = next((p for p in cluster_posts if p.get("is_centroid")), cluster_posts[0])

    sorted_posts = sorted(cluster_posts, key=lambda x: x.get("engagement", 0), reverse=True)
    top_post = sorted_posts[0]

    if top_post.get("id") == centroid_post.get("id") and len(sorted_posts) > 1:
        viral_post = sorted_posts[1]
    else:
        viral_post = top_post

    context_text = (
        f"POST A (Definition):\n{(centroid_post.get('text') or '')[:600]}\n\n"
        f"POST B (Viral):\n{(viral_post.get('text') or '')[:600]}"
    )

    system_prompt = """
You are a Design Trend Scout for streaming and gaming.

Goal: decide whether this cluster contains a coherent, nameable VISUAL AESTHETIC (not just a topic)
that can directly inform the design of a chat widget.

Think in terms of design tokens: color palette, typography vibe, textures/materials, icon/illustration style,
layout density, shapes (rounded vs sharp), lighting (glow vs flat), and animation feel.

DECISION RULES

A) Set valid=True only if BOTH are true:
1) Visual evidence: at least 2 posts contain meaningful visual description or show visuals (setups, UI skins, art style, etc.).
2) Cohesion: you can describe ONE consistent aesthetic that repeats across the cluster.
   Cohesion means at least 2 shared style signals appear in multiple posts
   (examples: “pastel + rounded UI”, “neon glow + dark city + chrome”, “pixel art + warm earthy palette”,
   “brutalist mono + grid layout”).

B) Set valid=False if:
- The cluster is mainly tech support, bugs, performance logs, or troubleshooting with no style language.
- It’s mainly growth/strategy/career advice with no concrete visual characteristics.
- It’s deals/promos/product drops without consistent style descriptors.
- Visuals exist but are scattered (no single aesthetic summary fits without being generic).

C) If visuals exist but cohesion is weak, set valid=False.

SCORING
relevance_score:
0-20: no visual content
21-49: visuals present but no cohesion (mixed)
50-74: cohesive aesthetic is present but somewhat broad
75-100: strong, distinctive aesthetic with repeated signals

Set valid=True only if relevance_score >= 50.

OUTPUT REQUIREMENTS (IMPORTANT)
- trend_name: 2-5 words. AESTHETIC ONLY.
  Do NOT include or reference: chat widget, overlay, alert, stream, streaming, setup, tutorial, pack, theme.
  Good: "Neon Chrome Noir" / "Cozy Pixel Farm"
  Bad: "Neon Chrome Noir Chat Widget" / "Cozy Pixel Farm Overlay"

- aesthetic_keywords: 3-8 short phrases describing the look (no product names; avoid overlay/widget/alert/stream/tutorial words).

Respond using the TrendAnalysis schema.
"""

    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context_text},
            ],
            response_format=TrendAnalysis,
        )

        result = completion.choices[0].message.parsed
        if not result.valid:
            return None

        out = result.model_dump()
        out["trend_name"] = _sanitize_trend_name(out.get("trend_name", ""))
        return out

    except Exception as e:
        print(f"LLM Error: {e}")
        return None
