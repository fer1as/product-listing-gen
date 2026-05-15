"""Product Listing Generator - LLM-powered via OpenRouter"""
import os, json, time, urllib.parse, urllib.request, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from pathlib import Path
from datetime import datetime

PORT = int(os.environ.get("PORT", "8768"))
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
_lock = threading.RLock()

env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")

CATEGORIES = {
    "home": {"name": "Home & Living", "price": (15, 65)},
    "jewelry": {"name": "Jewelry & Accessories", "price": (12, 45)},
    "clothing": {"name": "Clothing", "price": (20, 60)},
    "art": {"name": "Art & Collectibles", "price": (20, 120)},
    "craft": {"name": "Craft Supplies", "price": (5, 30)},
    "vintage": {"name": "Vintage", "price": (25, 100)},
    "wedding": {"name": "Wedding", "price": (15, 80)},
    "paper": {"name": "Paper & Party Supplies", "price": (5, 25)},
    "beauty": {"name": "Bath & Beauty", "price": (10, 35)},
    "books": {"name": "Books & Movies", "price": (10, 40)},
    "music": {"name": "Music", "price": (15, 50)},
    "toys": {"name": "Toys & Games", "price": (10, 45)},
    "pets": {"name": "Pet Supplies", "price": (10, 35)},
    "electronics": {"name": "Electronics", "price": (15, 80)},
    "sports": {"name": "Sports & Outdoors", "price": (15, 60)},
}

SYSTEM_PROMPT = """You are an Etsy listing optimization expert. Generate a complete, ready-to-use Etsy listing in JSON format.

Rules:
- Title: max 140 chars, front-load with most important keywords, pipe or dash separators
- Description: 3-4 short paragraphs, conversational but persuasive, include dimensions/materials if provided, end with a soft CTA
- Tags: exactly 13 single words or short phrases, comma-separated, no quotes, no repeats
- Price: suggest a price point in USD based on category benchmarks, no dollar sign in the response value
- Be specific, not generic. No filler phrases like "perfect for any occasion" or "makes a wonderful gift"
- Match the tone to the product aesthetic (e.g. boho=warm, modern=clean, vintage=nostalgic)

Respond ONLY with valid JSON, no markdown, no backticks:
{"title": "...", "description": "...", "tags": ["tag1","tag2",..."tag13"], "price": "29.99"}"""

def load_history():
    f = DATA_DIR / "history.json"
    if f.exists():
        try:
            with open(f, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except:
            return []
    return []

def save_history(history):
    with _lock:
        f = DATA_DIR / "history.json"
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(history[-100:], fh, indent=2, ensure_ascii=False)

def generate_listing(data):
    product = data.get("product", "").strip()
    keywords_raw = data.get("keywords", "").strip()
    cat_key = data.get("category", "home")
    user_desc = data.get("description", "").strip()
    category = CATEGORIES.get(cat_key, CATEGORIES["home"])
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]

    user_prompt = f"Product: {product}\nCategory: {category['name']}"
    if keywords:
        user_prompt += f"\nTarget keywords: {', '.join(keywords)}"
    if user_desc:
        user_prompt += f"\nDetails: {user_desc}"
    user_prompt += "\n\nGenerate the complete Etsy listing JSON."

    models = ["openrouter/free"]
    payload = json.dumps({
        "model": models[0],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 1000
    }).encode()

    last_error = None
    for attempt, model in enumerate(models):
        payload_dict = json.loads(payload)
        payload_dict["model"] = model
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload_dict).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "HTTP-Referer": "https://etsy-listing-gen.onrender.com",
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                result = json.loads(resp.read())
                msg = result["choices"][0]["message"]
                content = (msg.get("content") or "").strip()
                if not content:
                    last_error = f"Model {model} returned empty content"
                    continue
                if content.startswith("```"):
                    content = content.split("\n", 1)[1]
                    content = content.rsplit("```", 1)[0]
                parsed = json.loads(content.strip())
                if not isinstance(parsed.get("tags"), list):
                    tags = [t.strip() for t in parsed.get("tags", "").split(",") if t.strip()]
                else:
                    tags = parsed["tags"]
                return {
                    "title": parsed.get("title", product),
                    "description": parsed.get("description", ""),
                    "tags": tags[:13],
                    "price": f"${float(parsed.get('price', 0)):.2f}",
                    "keywords_used": keywords,
                    "category": category["name"],
                    "generated_at": datetime.now().isoformat(),
                }
        except Exception as e:
            last_error = f"Model {model} failed: {str(e)}"
            continue
    return {"error": last_error or "All models failed", "generated_at": datetime.now().isoformat()}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            self._serve_file(BASE_DIR / "dashboard.html", "text/html")
        elif path == "/flyer":
            self._serve_file(BASE_DIR / "flyer.html", "text/html")
        elif path == "/history":
            self._json_response(load_history())
        elif path.startswith("/static/"):
            filepath = BASE_DIR / path.lstrip("/")
            if filepath.exists() and filepath.is_file():
                ext = filepath.suffix.lower()
                mime = {"css": "text/css", "js": "application/javascript",
                        "png": "image/png", "jpg": "image/jpeg",
                        "svg": "image/svg+xml"}.get(ext, "application/octet-stream")
                self._serve_file(filepath, mime)
            else:
                self._send(404, "Not Found")
        elif path.startswith("/plantillas/"):
            filepath = BASE_DIR / path.lstrip("/")
            if filepath.exists() and filepath.is_file():
                ext = filepath.suffix.lower()
                mime = {"pdf": "application/pdf", "html": "text/html",
                        "css": "text/css", "png": "image/png"}.get(ext, "application/octet-stream")
                self._serve_file(filepath, mime)
            else:
                self._send(404, "Not Found")
        elif path == "/plantillas":
            self._serve_file(BASE_DIR / "plantillas" / "index.html", "text/html")
        else:
            self._send(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"

        try:
            data = json.loads(body)
        except:
            self._json_response({"error": "Invalid JSON"}, 400)
            return

        if parsed.path == "/generate":
            product = data.get("product", "").strip()
            if not product:
                self._json_response({"error": "Product name is required"}, 400)
                return
            result = generate_listing(data)
            if "error" in result:
                self._json_response(result, 500)
                return
            history = load_history()
            history.append(result)
            save_history(history)
            self._json_response(result)
        elif parsed.path == "/clear-history":
            save_history([])
            self._json_response({"ok": True})
        else:
            self._json_response({"error": "Not found"}, 404)

    def _serve_file(self, path, mime):
        try:
            with open(path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except:
            self._send(404, "Not Found")

    def _json_response(self, data, code=200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _send(self, code, msg):
        self._json_response({"error": msg}, code)

    def log_message(self, fmt, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]} {args[1]} {args[2]}")


class ThreadedServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

if __name__ == "__main__":
    if not OPENROUTER_KEY:
        print("ERROR: No OpenRouter API key found")
        exit(1)
    print(f"\n  Product Listing Generator (LLM)")
    print(f"  http://localhost:{PORT}")
    print(f"  Press Ctrl+C to stop\n")
    server = ThreadedServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
        server.shutdown()
