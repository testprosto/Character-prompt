import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from urllib.parse import quote

ANILIST_URL = "https://graphql.anilist.co"
SHIKIMORI = "https://shikimori.one"
DANBOORU = "https://danbooru.donmai.us"
HEADERS = {
    "User-Agent": "AnimaCharacterPromptGenerator/1.0 (local desktop app)",
    "Accept": "application/json",
}

def clean_html(value):
    if not value:
        return ""
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()

def anilist_search(name, anime=""):
    query = """
    query ($search: String) {
      Character(search: $search) {
        id
        name { full native alternative }
        image { large }
        description(asHtml: false)
        siteUrl
        media(perPage: 8) {
          nodes { id title { romaji english native } siteUrl type }
        }
      }
    }"""
    r = requests.post(ANILIST_URL, json={"query": query, "variables": {"search": name}},
                      headers=HEADERS, timeout=8)
    r.raise_for_status()
    item = (r.json().get("data") or {}).get("Character")
    if not item:
        return []
    media = item.get("media", {}).get("nodes", [])
    anime_names = []
    for m in media:
        title = m.get("title") or {}
        anime_names.extend([title.get("english"), title.get("romaji"), title.get("native")])
    anime_names = [x for x in dict.fromkeys(anime_names) if x]
    if anime:
        target = anime.casefold()
        matches = [m for m in media if target in " ".join(str(v or "") for v in (m.get("title") or {}).values()).casefold()]
        if matches:
            media = matches + [m for m in media if m not in matches]
    return [{
        "source": "AniList",
        "source_id": item.get("id"),
        "name": (item.get("name") or {}).get("full") or name,
        "native_name": (item.get("name") or {}).get("native") or "",
        "aliases": (item.get("name") or {}).get("alternative") or [],
        "anime": anime_names[0] if anime_names else anime,
        "anime_list": anime_names[:8],
        "description": clean_html(item.get("description")),
        "image": (item.get("image") or {}).get("large"),
        "url": item.get("siteUrl"),
    }]

def shikimori_search(name, anime=""):
    url = f"{SHIKIMORI}/api/characters"
    r = requests.get(url, params={"search": name, "limit": 10},
                     headers={**HEADERS, "User-Agent": "AnimaLocalPromptGenerator/1.0"}, timeout=8)
    r.raise_for_status()
    results = []
    for item in r.json()[:10]:
        russian = item.get("russian") or ""
        eng = item.get("name") or ""
        image = item.get("image") or {}
        url_obj = image.get("original") or image.get("preview") or ""
        results.append({
            "source": "Shikimori", "source_id": item.get("id"),
            "name": russian or eng or name, "native_name": eng,
            "aliases": [], "anime": anime, "anime_list": [],
            "description": "", "image": (SHIKIMORI + url_obj) if url_obj.startswith("/") else url_obj,
            "url": f"{SHIKIMORI}/characters/{item.get('id')}"
        })
    return results

# Alternate spellings for characters that may be missing from one database.
CHARACTER_ALIASES = {
    "hajun": ["Hajun", "Māra Pāpīyas", "Mara Papiyas", "Dairokuten Hajun", "波旬"],
    "波旬": ["波旬", "Hajun", "Māra Pāpīyas", "Mara Papiyas", "Dairokuten Hajun"],
    "mara papiyas": ["Māra Pāpīyas", "Mara Papiyas", "Hajun", "Dairokuten Hajun", "波旬"],
    "māra pāpīyas": ["Māra Pāpīyas", "Mara Papiyas", "Hajun", "Dairokuten Hajun", "波旬"],
}

MUDAE_HAJUN = {
    "name": "Hajun", "anime": "Kajiri Kamui Kagura",
    "url": "https://mudae.net/character/4062946/Hajun",
    "aliases": ["Māra Pāpīyas", "The Great Greedy Tengu", "Demon of the Sixth Heaven",
                "Dairokuten Hajun", "Sixth Demon King", "Mara Papiyas", "波旬"],
}

def search_character(name, anime=""):
    """Search external catalogs but never return an empty result list.

    Hajun has a verified Mudae fallback. For other characters, a manual
    candidate is returned when public APIs are unavailable or have no match.
    """
    key = (name or "").casefold().strip()
    aliases = CHARACTER_ALIASES.get(key, [name])
    hajun_terms = {x.casefold() for x in CHARACTER_ALIASES["hajun"]}
    candidates = []
    warnings = []

    # Add the known Hajun result before calling any external service.
    if key in hajun_terms:
        candidates.append({
            "source": "Mudae", "source_id": 4062946, "name": "Hajun",
            "native_name": "波旬", "aliases": MUDAE_HAJUN["aliases"],
            "anime": MUDAE_HAJUN["anime"],
            "anime_list": [MUDAE_HAJUN["anime"]],
            "description": "Verified Mudae character entry. External catalog lookups are optional.",
            "image": "https://mudae.net/uploads/4062946/ZHea1EZ~yrgcnoqkng4.png",
            "url": MUDAE_HAJUN["url"],
            "matched_query": "Mudae fallback"
        })

    # First try the exact spelling against both main catalogs.
    def query_pair(term):
        found = []
        errors = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            tasks = [
                ("AniList", pool.submit(anilist_search, term, anime)),
                ("Shikimori", pool.submit(shikimori_search, term, anime)),
            ]
            for label, future in tasks:
                try:
                    found.extend(future.result(timeout=12))
                except Exception as exc:
                    errors.append(f"{label} ({term}): {exc}")
        for item in found:
            item["matched_query"] = term
        return found, errors

    exact, errors = query_pair(name)
    candidates.extend(exact)
    warnings.extend(errors)

    # Retry alternate spellings only if the exact search found nothing.
    if not exact and len(aliases) > 1:
        for variant in aliases[1:]:
            found, errors = query_pair(variant)
            candidates.extend(found)
            warnings.extend(errors)
            if found:
                break

    # De-duplicate by provider and provider ID.
    unique = []
    seen = set()
    for item in candidates:
        identity = (
            item.get("source"),
            str(item.get("source_id") or item.get("name", "")).casefold()
        )
        if identity not in seen:
            seen.add(identity)
            unique.append(item)

    # Always let the user continue with a manually selected character.
    if not unique:
        unique.append({
            "source": "Manual", "source_id": None, "name": name,
            "native_name": "", "aliases": [], "anime": anime,
            "anime_list": [anime] if anime else [],
            "description": "No public catalog match. You can still build the profile manually.",
            "image": "", "url": "", "matched_query": name
        })

    return {"results": unique, "warnings": warnings}


def fetch_mudae_data(character):
    if (character.get("source") or "").casefold() != "mudae":
        return {"tags": [], "images": [], "url": None, "errors": []}
    url = character.get("url") or MUDAE_HAJUN["url"]
    try:
        r = requests.get(url, headers={**HEADERS, "User-Agent": "Mozilla/5.0 AnimaCharacterPromptGenerator/1.0"}, timeout=10)
        r.raise_for_status()
        html = r.text
        plain = unescape(re.sub(r"<[^>]+>", " ", html))
        plain = re.sub(r"\s+", " ", plain)
        # Extract linked tag labels from the relevant raw HTML sections. In Mudae,
        # each tag is an anchor, so stripping all markup first would merge labels.
        look_html = re.search(r"Look:\s*(.*?)(?:Other:|Custom Lists|Images \()", html, re.I | re.S)
        other_html = re.search(r"Other:\s*(.*?)(?:Custom Lists|Images \()", html, re.I | re.S)
        tags = []
        for section in (look_html.group(1) if look_html else "", other_html.group(1) if other_html else ""):
            labels = re.findall(r">\s*([^<>]+?)\s*</a>", section, re.I | re.S)
            tags.extend(unescape(x).strip() for x in labels if unescape(x).strip())
        # Keep only direct image links found in the page markup.
        image_urls = re.findall(r"(?:src|data-src|href)=[\"']((?:https?://|/uploads/)[^\"']+)[\"']", html, re.I)
        image_urls = [("https://mudae.net" + u if u.startswith("/") else u) for u in image_urls]
        image_urls = [u for u in image_urls if re.search(r"\.(?:png|jpe?g|webp|gif)(?:\?|$)", u, re.I)]
        return {"tags": list(dict.fromkeys(tags)), "images": list(dict.fromkeys(image_urls))[:12], "url": url, "errors": []}
    except Exception as e:
        return {"tags": [], "images": [], "url": url, "errors": [f"Mudae: {e}"]}

def slug(text):
    text = (text or "").strip().lower().replace(" ", "_")
    text = re.sub(r"[^a-z0-9_'-]", "", text)
    return re.sub(r"_+", "_", text).strip("_")

def fetch_booru_data(name, anime=""):
    # Search character tags by a conservative name match, then fetch safe-rated posts.
    variants = [slug(name)]
    if anime:
        variants.append(slug(anime))
    tags_found, posts, errors = [], [], []
    for term in variants[:1]:
        try:
            r = requests.get(f"{DANBOORU}/tags.json",
                params={"search[name_matches]": f"*{term}*", "limit": 30},
                headers=HEADERS, timeout=8)
            r.raise_for_status()
            for tag in r.json():
                tags_found.append({
                    "name": tag.get("name"),
                    "category": tag.get("category"),
                    "post_count": tag.get("post_count", 0)
                })
        except Exception as e:
            errors.append(f"Danbooru tags: {e}")
    # Character-tag exact search; only safe posts are requested.
    character_tags = [t["name"] for t in tags_found if t.get("category") == 4]
    candidate_tags = character_tags[:3] or [variants[0]]
    for tag in candidate_tags:
        try:
            r = requests.get(f"{DANBOORU}/posts.json",
                params={"tags": f"{tag} rating:s", "limit": 20},
                headers=HEADERS, timeout=10)
            r.raise_for_status()
            for p in r.json():
                if p.get("file_url"):
                    posts.append({
                        "id": p.get("id"),
                        "image": p.get("large_file_url") or p.get("file_url"),
                        "preview": p.get("preview_file_url") or p.get("file_url"),
                        "source": p.get("source"),
                        "tags": p.get("tag_string", ""),
                        "rating": p.get("rating")
                    })
        except Exception as e:
            errors.append(f"Danbooru posts ({tag}): {e}")
    # Unique images
    seen = set()
    unique_posts = []
    for p in posts:
        if p["image"] not in seen:
            seen.add(p["image"])
            unique_posts.append(p)
    return {"tags": tags_found, "posts": unique_posts[:18], "errors": errors,
            "source_url": f"{DANBOORU}/posts?tags={quote(candidate_tags[0] if candidate_tags else variants[0])}"}

TAG_MAP = {
    "hair": ["hair", "hair_color", "long_hair", "short_hair", "spiky_hair", "ponytail", "braid", "bangs"],
    "eyes": ["eyes", "eye_color", "red_eyes", "blue_eyes", "green_eyes", "yellow_eyes", "multiple_eyes"],
    "skin": ["skin", "dark_skin", "pale_skin", "tan"],
    "clothing": ["clothing", "dress", "shirt", "robe", "kimono", "armor", "uniform", "pants", "skirt", "hood"],
    "accessories": ["earrings", "jewelry", "necklace", "bracelet", "gloves", "hat", "weapon"],
    "body": ["muscular", "slim", "tall", "short", "large_breasts", "small_breasts"],
    "traits": ["wings", "halo", "horns", "tail", "third_eye", "multiple_arms", "aura", "tattoo", "facial_mark"],
}

def build_character_profile(character, booru, mudae=None):
    mudae = mudae or {"tags": [], "images": [], "errors": []}
    all_tags = []
    for post in booru.get("posts", []):
        all_tags.extend((post.get("tags") or "").split())
    # Count tags and retain useful descriptive tags. Danbooru category metadata is used as supporting evidence,
    # but tag strings from posts are also included because they describe visual content.
    counts = {}
    for tag in all_tags:
        counts[tag] = counts.get(tag, 0) + 1
    ranked = [k for k, _ in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]
    categories = {}
    for key, needles in TAG_MAP.items():
        categories[key] = [t.replace("_", " ") for t in ranked
                           if any(n in t for n in needles)][:18]
    # Add curated character-level tags from Mudae when available.
    mudae_tags = [str(t).strip() for t in mudae.get("tags", []) if str(t).strip()]
    curated = {
        "Dark Skin": ("skin", "dark skin"), "Blonde Hair": ("hair", "blonde hair"),
        "Black Sclera": ("eyes", "black sclera"), "White Eyes": ("eyes", "white eyes"),
        "Forehead Eye": ("traits", "third eye on forehead"), "Long Earlobes": ("traits", "long earlobes"),
        "Barefoot": ("clothing", "barefoot"), "Earrings": ("accessories", "earrings"),
    }
    for label, (category, prompt_tag) in curated.items():
        if label in mudae_tags:
            categories.setdefault(category, []).append(prompt_tag)
    desc = character.get("description") or ""
    return {
        "character": character,
        "description": desc,
        "appearance": categories.get("body", []),
        "colors": {
            "skin": [x for x in categories.get("skin", [])],
            "hair": [x for x in categories.get("hair", [])],
            "eyes": [x for x in categories.get("eyes", [])],
        },
        "clothing": categories.get("clothing", []),
        "accessories": categories.get("accessories", []),
        "special_traits": categories.get("traits", []),
        "personality": [x.lower() for x in mudae_tags if x in ("Arrogant", "Superiority Complex")],
        "abilities": [],
        "history": "",
        "all_tags": ranked[:100],
        "mudae_tags": mudae_tags,
        "mudae_images": mudae.get("images", []),
        "mudae_url": mudae.get("url"),
        "evidence_note": "Данные объединены из Danbooru и Mudae. Теги являются подсказками и не гарантируют каноничность каждого признака. Проверьте изображения и исправьте профиль вручную."
    }

def split_tags(value):
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [x.strip() for x in re.split(r"[,;\n]+", value) if x.strip()]
    return []

def generate_prompts(profile):
    character = profile.get("character") or {}
    name = character.get("name") or "character"
    anime = character.get("anime") or ""
    colors = profile.get("colors") or {}
    groups = [
        name, anime,
        *split_tags(profile.get("appearance")),
        *split_tags(colors.get("skin")),
        *split_tags(colors.get("hair")),
        *split_tags(colors.get("eyes")),
        *split_tags(profile.get("clothing")),
        *split_tags(profile.get("accessories")),
        *split_tags(profile.get("special_traits")),
    ]
    # Remove duplicates, keep descriptive tags. Do not inject unknown gender/age.
    positive = []
    for item in groups:
        item = re.sub(r"\s+", " ", str(item)).strip()
        if item and item.casefold() not in {x.casefold() for x in positive}:
            positive.append(item)
    positive = ", ".join(positive)
    negative = ", ".join([
        "low quality", "worst quality", "lowres", "blurry",
        "bad anatomy", "bad hands", "extra fingers", "missing fingers",
        "deformed", "mutated", "poorly drawn face", "text", "watermark", "logo"
    ])
    return {"positive": positive, "negative": negative}
