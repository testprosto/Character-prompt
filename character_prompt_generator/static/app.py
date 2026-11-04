from flask import Flask, render_template, request, jsonify
from concurrent.futures import ThreadPoolExecutor
from services import search_character, build_character_profile, fetch_booru_data, fetch_mudae_data, generate_prompts
import os

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

@app.get("/")
def index():
    return render_template("index.html")

@app.post("/api/search")
def api_search():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    anime = (data.get("anime") or "").strip()
    if not name:
        return jsonify({"error": "Введите имя персонажа."}), 400
    try:
        return jsonify(search_character(name, anime))
    except Exception as exc:
        return jsonify({"error": f"Ошибка поиска: {exc}"}), 502

@app.post("/api/analyze")
def api_analyze():
    data = request.get_json(silent=True) or {}
    character = data.get("character") or {}
    name = (character.get("name") or data.get("name") or "").strip()
    anime = (character.get("anime") or data.get("anime") or "").strip()
    if not name:
        return jsonify({"error": "Не выбран персонаж."}), 400
    try:
        # Independent public sources are fetched in parallel to reduce the
        # serverless request duration on Vercel.
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
    profile["prompts"] = generate_prompts(profile)
    return jsonify(profile["prompts"])

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "7860")), debug=False)
