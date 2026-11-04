
import re
import requests
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from urllib.parse import quote

ANILIST_URL = "https://graphql.anilist.co"
SHIKIMORI = "https://shikimori.one"
DANBOORU = "https://danbooru.donmai.us"

HEADERS = {
    "User-Agent": "AnimaCharacterPromptGenerator/1.0",
    "Accept": "application/json",
}


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_html(value):
    if not value:
        return ""

    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)

    return re.sub(r"\n{3,}", "\n\n", value).strip()


def normalize_title(value):
    """
    Normalize anime titles for comparison.
    Supports Latin, Cyrillic and Japanese characters.
    """
    value = (value or "").casefold().strip()

    return re.sub(
        r"[^a-z0-9а-яё\u3040-\u30ff\u3400-\u9fff]+",
        "",
        value
    )


def anime_matches(requested, titles):
    """
    Check whether a character belongs to the requested anime.
    """
    if not requested:
        return True

    target = normalize_title(requested)

    if not target:
        return True

    for title in titles or []:
        candidate = normalize_title(title)

        if not candidate:
            continue

        if candidate == target:
            return True

        if target in candidate or candidate in target:
            return True

    return False


# ============================================================
# ANILIST
# ============================================================

def anilist_search(name, anime=""):
    query = """
    query ($search: String) {
      Character(search: $search) {
        id
        name {
          full
          native
          alternative
        }
        image {
          large
        }
        description(asHtml: false)
        siteUrl
        media(perPage: 50) {
          nodes {
            id
            title {
              romaji
              english
              native
            }
            siteUrl
            type
          }
        }
      }
    }
    """

    response = requests.post(
        ANILIST_URL,
        json={
            "query": query,
            "variables": {
                "search": name
            }
        },
        headers=HEADERS,
        timeout=12
    )

    response.raise_for_status()

    data = response.json()

    item = (data.get("data") or {}).get("Character")

    if not item:
        return []

    media = (item.get("media") or {}).get("nodes", [])

    anime_names = []

    for media_item in media:
        title = media_item.get("title") or {}

        anime_names.extend([
            title.get("english"),
            title.get("romaji"),
            title.get("native")
        ])

    anime_names = list(dict.fromkeys(
        title for title in anime_names if title
    ))

    # Strict anime filtering.
    # Do not return a character from an unrelated anime.
    if anime and not anime_matches(anime, anime_names):
        return []

    character_name = item.get("name") or {}
    character_image = item.get("image") or {}

    return [{
        "source": "AniList",
        "source_id": item.get("id"),
        "name": character_name.get("full") or name,
        "native_name": character_name.get("native") or "",
        "aliases": character_name.get("alternative") or [],
        "anime": anime or (
            anime_names[0] if anime_names else ""
        ),
        "anime_list": anime_names[:50],
        "description": clean_html(item.get("description")),
        "image": character_image.get("large"),
        "url": item.get("siteUrl")
    }]


# ============================================================
# SHIKIMORI
# ============================================================

def shikimori_search(name, anime=""):
    """
    Search Shikimori characters.

    Search endpoint:
    /api/characters/search

    Then fetch character details to check anime relations.
    """

    search_url = f"{SHIKIMORI}/api/characters/search"

    headers = {
        **HEADERS,
        "User-Agent": "AnimaCharacterPromptGenerator/1.0"
    }

    response = requests.get(
        search_url,
        params={
            "search": name
        },
        headers=headers,
        timeout=12
    )

    response.raise_for_status()

    items = response.json()

    if not isinstance(items, list):
        return []

    results = []

    for item in items[:10]:
        character_id = item.get("id")

        if not character_id:
            continue

        # Fetch detailed character information.
        detail_response = requests.get(
            f"{SHIKIMORI}/api/characters/{character_id}",
            headers=headers,
            timeout=10
        )

        detail_response.raise_for_status()

        detail = detail_response.json()

        anime_names = []

        for relation in detail.get("animes", []):
            anime_data = relation.get("anime") or {}

            anime_names.extend([
                anime_data.get("name"),
                anime_data.get("russian")
            ])

        anime_names = list(dict.fromkeys(
            title for title in anime_names if title
        ))

        # Exclude characters from unrelated anime.
        if anime and not anime_matches(anime, anime_names):
            continue

        russian_name = (
            detail.get("russian")
            or item.get("russian")
            or ""
        )

        english_name = (
            detail.get("name")
            or item.get("name")
            or ""
        )

        image = detail.get("image") or item.get("image") or {}

        image_url = (
            image.get("original")
            or image.get("preview")
            or ""
        )

        if image_url.startswith("/"):
            image_url = SHIKIMORI + image_url

        results.append({
            "source": "Shikimori",
            "source_id": character_id,
            "name": russian_name or english_name or name,
            "native_name": english_name,
            "aliases": [
                detail.get("altname") or ""
            ],
            "anime": anime or (
                anime_names[0] if anime_names else ""
            ),
            "anime_list": anime_names,
            "description": "",
            "image": image_url,
            "url": f"{SHIKIMORI}/characters/{character_id}"
        })

    return results


# ============================================================
# CHARACTER ALIASES
# ============================================================

CHARACTER_ALIASES = {
    "hajun": [
        "Hajun",
        "Māra Pāpīyas",
        "Mara Papiyas",
        "Dairokuten Hajun",
        "波旬"
    ],

    "波旬": [
        "波旬",
        "Hajun",
        "Māra Pāpīyas",
        "Mara Papiyas",
        "Dairokuten Hajun"
    ],

    "mara papiyas": [
        "Māra Pāpīyas",
        "Mara Papiyas",
        "Hajun",
        "Dairokuten Hajun",
        "波旬"
    ],

    "māra pāpīyas": [
        "Māra Pāpīyas",
        "Mara Papiyas",
        "Hajun",
        "Dairokuten Hajun",
        "波旬"
    ],
}


# ============================================================
# MUDAE FALLBACK
# ============================================================

MUDAE_HAJUN = {
    "name": "Hajun",
    "anime": "Kajiri Kamui Kagura",

    "url": "https://mudae.net/character/4062946/Hajun",

    "aliases": [
        "Māra Pāpīyas",
        "The Great Greedy Tengu",
        "Demon of the Sixth Heaven",
        "Dairokuten Hajun",
        "Sixth Demon King",
        "Mara Papiyas",
        "波旬"
    ],
}


# ============================================================
# MAIN CHARACTER SEARCH
# ============================================================

def search_character(name, anime=""):
    """
    Search AniList and Shikimori.

    Hajun has a verified Mudae fallback.

    Other characters receive a Manual fallback
    when public catalogs have no matching result.
    """

    key = (name or "").casefold().strip()

    aliases = CHARACTER_ALIASES.get(key, [name])

    hajun_terms = {
        value.casefold()
        for value in CHARACTER_ALIASES["hajun"]
    }

    candidates = []
    warnings = []

    # --------------------------------------------------------
    # Add verified Hajun result.
    # --------------------------------------------------------

    if key in hajun_terms:
        if (
            not anime
            or anime_matches(
                anime,
                [MUDAE_HAJUN["anime"]]
            )
        ):
            candidates.append({
                "source": "Mudae",
                "source_id": 4062946,
                "name": "Hajun",
                "native_name": "波旬",
                "aliases": MUDAE_HAJUN["aliases"],
                "anime": MUDAE_HAJUN["anime"],
                "anime_list": [
                    MUDAE_HAJUN["anime"]
                ],
                "description": (
                    "Verified Mudae character entry. "
                    "External catalog lookups are optional."
                ),
                "image": (
                    "https://mudae.net/uploads/"
                    "4062946/ZHea1EZ~yrgcnoqkng4.png"
                ),
                "url": MUDAE_HAJUN["url"],
                "matched_query": "Mudae fallback"
            })

    # --------------------------------------------------------
    # Query both catalogs independently.
    # --------------------------------------------------------

    def query_pair(term):
        found = []
        errors = []

        with ThreadPoolExecutor(max_workers=2) as pool:
            tasks = {
                "AniList": pool.submit(
                    anilist_search,
                    term,
                    anime
                ),

                "Shikimori": pool.submit(
                    shikimori_search,
                    term,
                    anime
                )
            }

            for label, future in tasks.items():
                try:
                    found.extend(future.result(timeout=20))

                except Exception as exc:
                    errors.append(
                        f"{label} ({term}): {exc}"
                    )

        for item in found:
            item["matched_query"] = term

        return found, errors

    # --------------------------------------------------------
    # Exact search.
    # --------------------------------------------------------

    exact, errors = query_pair(name)

    candidates.extend(exact)

    # Shikimori is optional.
    # Its failure must not interrupt successful results.
    warnings.extend(
        error
        for error in errors
        if not error.startswith("Shikimori")
    )

    # --------------------------------------------------------
    # Try alternate names if exact search found nothing.
    # --------------------------------------------------------

    if not exact and len(aliases) > 1:
        for variant in aliases[1:]:

            found, errors = query_pair(variant)

            candidates.extend(found)

            warnings.extend(
                error
                for error in errors
                if not error.startswith("Shikimori")
            )

            if found:
                break

    # --------------------------------------------------------
    # Final anime filter.
    # --------------------------------------------------------

    if anime:
        filtered = []

        for item in candidates:
            item_anime = []

            if item.get("anime"):
                item_anime.append(item["anime"])

            item_anime.extend(
                item.get("anime_list") or []
            )

            if anime_matches(anime, item_anime):
                filtered.append(item)

        candidates = filtered

    # --------------------------------------------------------
    # Remove duplicates.
    # --------------------------------------------------------

    unique = []
    seen = set()

    for item in candidates:
        identity = (
            item.get("source"),
            str(
                item.get("source_id")
                or item.get("name", "")
            ).casefold()
        )

        if identity not in seen:
            seen.add(identity)
            unique.append(item)

    # --------------------------------------------------------
    # Manual fallback.
    # --------------------------------------------------------

    if not unique:
        unique.append({
            "source": "Manual",
            "source_id": None,
            "name": name,
            "native_name": "",
            "aliases": [],
            "anime": anime,
            "anime_list": [anime] if anime else [],
            "description": (
                "No public catalog match. "
                "You can still build the profile manually."
            ),
            "image": "",
            "url": "",
            "matched_query": name
        })

    return {
        "results": unique,
        "warnings": warnings
    }


# ============================================================
# MUDAE DATA
# ============================================================

def fetch_mudae_data(character):

    if (character.get("source") or "").casefold() != "mudae":
        return {
            "tags": [],
            "images": [],
            "url": None,
            "errors": []
        }

    url = character.get("url") or MUDAE_HAJUN["url"]

    try:
        response = requests.get(
            url,
            headers={
                **HEADERS,
                "User-Agent": (
                    "Mozilla/5.0 "
                    "AnimaCharacterPromptGenerator/1.0"
                )
            },
            timeout=10
        )

        response.raise_for_status()

        html = response.text

        plain = unescape(
            re.sub(r"<[^>]+>", " ", html)
        )

        plain = re.sub(r"\s+", " ", plain)

        # Extract tag sections.
        look_html = re.search(
            r"Look:\s*(.*?)(?:Other:|Custom Lists|Images \()",
            html,
            re.I | re.S
        )

        other_html = re.search(
            r"Other:\s*(.*?)(?:Custom Lists|Images \()",
            html,
            re.I | re.S
        )

        tags = []

        for section in (
            look_html.group(1) if look_html else "",
            other_html.group(1) if other_html else ""
        ):
            labels = re.findall(
                r">\s*([^<>]+?)\s*</a>",
                section,
                re.I | re.S
            )

            tags.extend(
                unescape(value).strip()
                for value in labels
                if unescape(value).strip()
            )

        # Extract image URLs.
        image_urls = re.findall(
            r"""(?:src|data-src|href)=["']((?:https?://|/uploads/)[^"']+)["']""",
            html,
            re.I
        )

        image_urls = [
            "https://mudae.net" + value
            if value.startswith("/")
            else value
            for value in image_urls
        ]

        image_urls = [
            value
            for value in image_urls
            if re.search(
                r"\.(?:png|jpe?g|webp|gif)(?:\?|$)",
                value,
                re.I
            )
        ]

        return {
            "tags": list(dict.fromkeys(tags)),
            "images": list(dict.fromkeys(image_urls))[:12],
            "url": url,
            "errors": []
        }

    except Exception as exc:
        return {
            "tags": [],
            "images": [],
            "url": url,
            "errors": [f"Mudae: {exc}"]
        }


# ============================================================
# DANBOORU
# ============================================================

def slug(text):
    text = (text or "").strip().lower().replace(" ", "_")

    text = re.sub(
        r"[^a-z0-9_'-]",
        "",
        text
    )

    return re.sub(
        r"_+",
        "_",
        text
    ).strip("_")


def fetch_booru_data(name, anime=""):

    variants = [slug(name)]

    if anime:
        variants.append(slug(anime))

    tags_found = []
    posts = []
    errors = []

    # --------------------------------------------------------
    # Search character tags.
    # --------------------------------------------------------

    for term in variants[:1]:
        try:
            response = requests.get(
                f"{DANBOORU}/tags.json",
                params={
                    "search[name_matches]": f"*{term}*",
                    "limit": 30
                },
                headers=HEADERS,
                timeout=8
            )

            response.raise_for_status()

            for tag in response.json():
                tags_found.append({
                    "name": tag.get("name"),
                    "category": tag.get("category"),
                    "post_count": tag.get("post_count", 0)
                })

        except Exception as exc:
            errors.append(
                f"Danbooru tags: {exc}"
            )

    # --------------------------------------------------------
    # Only character category tags.
    # --------------------------------------------------------

    character_tags = [
        tag["name"]
        for tag in tags_found
        if tag.get("category") == 4
    ]

    candidate_tags = character_tags[:3] or [variants[0]]

    # --------------------------------------------------------
    # Search safe-rated posts.
    # --------------------------------------------------------

    for tag in candidate_tags:
        try:
            response = requests.get(
                f"{DANBOORU}/posts.json",
                params={
                    "tags": f"{tag} rating:s",
                    "limit": 20
                },
                headers=HEADERS,
                timeout=10
            )

            response.raise_for_status()

            for post in response.json():
                if post.get("file_url"):
                    posts.append({
                        "id": post.get("id"),
                        "image": (
                            post.get("large_file_url")
                            or post.get("file_url")
                        ),
                        "preview": (
                            post.get("preview_file_url")
                            or post.get("file_url")
                        ),
                        "source": post.get("source"),
                        "tags": post.get("tag_string", ""),
                        "rating": post.get("rating")
                    })

        except Exception as exc:
            errors.append(
                f"Danbooru posts ({tag}): {exc}"
            )

    # --------------------------------------------------------
    # Remove duplicate images.
    # --------------------------------------------------------

    seen = set()
    unique_posts = []

    for post in posts:
        if post["image"] not in seen:
            seen.add(post["image"])
            unique_posts.append(post)

    return {
        "tags": tags_found,
        "posts": unique_posts[:18],
        "errors": errors,
        "source_url": (
            f"{DANBOORU}/posts?tags="
            f"{quote(candidate_tags[0] if candidate_tags else variants[0])}"
        )
    }


# ============================================================
# TAG CATEGORIES
# ============================================================

TAG_MAP = {
    "hair": [
        "hair",
        "hair_color",
        "long_hair",
        "short_hair",
        "spiky_hair",
        "ponytail",
        "braid",
        "bangs"
    ],

    "eyes": [
        "eyes",
        "eye_color",
        "red_eyes",
        "blue_eyes",
        "green_eyes",
        "yellow_eyes",
        "multiple_eyes"
    ],

    "skin": [
        "skin",
        "dark_skin",
        "pale_skin",
        "tan"
    ],

    "clothing": [
        "clothing",
        "dress",
        "shirt",
        "robe",
        "kimono",
        "armor",
        "uniform",
        "pants",
        "skirt",
        "hood"
    ],

    "accessories": [
        "earrings",
        "jewelry",
        "necklace",
        "bracelet",
        "gloves",
        "hat",
        "weapon"
    ],

    "body": [
        "muscular",
        "slim",
        "tall",
        "short",
        "large_breasts",
        "small_breasts"
    ],

    "traits": [
        "wings",
        "halo",
        "horns",
        "tail",
        "third_eye",
        "multiple_arms",
        "aura",
        "tattoo",
        "facial_mark"
    ],
}


# ============================================================
# BUILD CHARACTER PROFILE
# ============================================================

def build_character_profile(character, booru, mudae=None):

    mudae = mudae or {
        "tags": [],
        "images": [],
        "errors": []
    }

    all_tags = []

    for post in booru.get("posts", []):
        all_tags.extend(
            (post.get("tags") or "").split()
        )

    # Count tags.
    counts = {}

    for tag in all_tags:
        counts[tag] = counts.get(tag, 0) + 1

    ranked = [
        key
        for key, value in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0])
        )
    ]

    categories = {}

    for key, needles in TAG_MAP.items():
        categories[key] = [
            tag.replace("_", " ")
            for tag in ranked
            if any(needle in tag for needle in needles)
        ][:18]

    # --------------------------------------------------------
    # Curated Mudae tags.
    # --------------------------------------------------------

    mudae_tags = [
        str(tag).strip()
        for tag in mudae.get("tags", [])
        if str(tag).strip()
    ]

    curated = {
        "Dark Skin": (
            "skin",
            "dark skin"
        ),

        "Blonde Hair": (
            "hair",
            "blonde hair"
        ),

        "Black Sclera": (
            "eyes",
            "black sclera"
        ),

        "White Eyes": (
            "eyes",
            "white eyes"
        ),

        "Forehead Eye": (
            "traits",
            "third eye on forehead"
        ),

        "Long Earlobes": (
            "traits",
            "long earlobes"
        ),

        "Barefoot": (
            "clothing",
            "barefoot"
        ),

        "Earrings": (
            "accessories",
            "earrings"
        ),
    }

    for label, (category, prompt_tag) in curated.items():
        if label in mudae_tags:
            categories.setdefault(
                category,
                []
            ).append(prompt_tag)

    description = character.get("description") or ""

    return {
        "character": character,

        "description": description,

        "appearance": categories.get("body", []),

        "colors": {
            "skin": categories.get("skin", []),
            "hair": categories.get("hair", []),
            "eyes": categories.get("eyes", [])
        },

        "clothing": categories.get("clothing", []),

        "accessories": categories.get("accessories", []),

        "special_traits": categories.get("traits", []),

        "personality": [
            tag.lower()
            for tag in mudae_tags
            if tag in (
                "Arrogant",
                "Superiority Complex"
            )
        ],

        "abilities": [],

        "history": "",

        "all_tags": ranked[:100],

        "mudae_tags": mudae_tags,

        "mudae_images": mudae.get("images", []),

        "mudae_url": mudae.get("url"),

        "evidence_note": (
            "Данные объединены из Danbooru и Mudae. "
            "Теги являются подсказками и не гарантируют "
            "каноничность каждого признака. "
            "Проверьте изображения и исправьте профиль вручную."
        )
    }


# ============================================================
# PROMPT HELPERS
# ============================================================

def split_tags(value):

    if isinstance(value, list):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    if isinstance(value, str):
        return [
            item.strip()
            for item in re.split(r"[,;\n]+", value)
            if item.strip()
        ]

    return []


# ============================================================
# GENERATE POSITIVE / NEGATIVE PROMPTS
# ============================================================

def generate_prompts(profile):

    character = profile.get("character") or {}

    name = character.get("name") or "character"

    anime = character.get("anime") or ""

    colors = profile.get("colors") or {}

    groups = [
        name,
        anime,

        *split_tags(
            profile.get("appearance")
        ),

        *split_tags(
            colors.get("skin")
        ),

        *split_tags(
            colors.get("hair")
        ),

        *split_tags(
            colors.get("eyes")
        ),

        *split_tags(
            profile.get("clothing")
        ),

        *split_tags(
            profile.get("accessories")
        ),

        *split_tags(
            profile.get("special_traits")
        ),
    ]

    # Remove duplicates.
    positive = []

    for item in groups:
        item = re.sub(
            r"\s+",
            " ",
            str(item)
        ).strip()

        if item and item.casefold() not in {
            value.casefold()
            for value in positive
        }:
            positive.append(item)

    positive = ", ".join(positive)

    negative = ", ".join([
        "low quality",
        "worst quality",
        "lowres",
        "blurry",
        "bad anatomy",
        "bad hands",
        "extra fingers",
        "missing fingers",
        "deformed",
        "mutated",
        "poorly drawn face",
        "text",
        "watermark",
        "logo"
    ])

    return {
        "positive": positive,
        "negative": negative
    }
