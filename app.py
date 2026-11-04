from pathlib import Path
from flask import Flask, render_template, request, jsonify
from concurrent.futures import ThreadPoolExecutor
from services import (
    search_character, build_character_profile, fetch_booru_data,
    fetch_mudae_data, generate_prompts
)

ROOT = Path(__file__).resolve().parent
app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(ROOT / "public"),
    static_url_path="",
)
app.config["JSON_AS_ASCII"] = False
app.config["JSON_SORT_KEYS"] = False


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "anima-character-prompt-generator"})


@app.post("/api/search")
def api_search():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    anime = str(data.get("anime") or "").strip()
    if not name:
        return jsonify({"error": "Введите имя персонажа."}), 400
    try:
        result = search_character(name, anime)
        return jsonify(result)
    except Exception as exc:
        # Search service should normally return a manual fallback, but keep
        # the endpoint usable even if an unexpected exception occurs.
        return jsonify({
            "results": [{
                "source": "Manual", "source_id": None, "name": name,
                "native_name": "", "aliases": [], "anime": anime,
                "anime_list": [anime] if anime else [], "description": "",
                "image": "", "url": "", "matched_query": name
            }],
            "warnings": [str(exc)],
        })


@app.post("/api/analyze")
def api_analyze():
    data = request.get_json(silent=True) or {}
    character = data.get("character") or {}
    name = str(character.get("name") or data.get("name") or "").strip()
    anime = str(character.get("anime") or data.get("anime") or "").strip()
    if not name:
        return jsonify({"error": "Не выбран персонаж."}), 400
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            booru_future = pool.submit(fetch_booru_data, name, anime)
            mudae_future = pool.submit(fetch_mudae_data, character)
            booru = booru_future.result()
            mudae = mudae_future.result()
        profile = build_character_profile(character, booru, mudae)
        profile["booru"] = booru
        profile["mudae"] = mudae
        profile["prompts"] = generate_prompts(profile)
        return jsonify(profile)
    except Exception as exc:
        return jsonify({"error": f"Ошибка анализа: {exc}"}), 502


@app.post("/api/generate")
def api_generate():
    data = request.get_json(silent=True) or {}
    profile = data.get("profile") or {}
    return jsonify(generate_prompts(profile))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=7860, debug=False)
