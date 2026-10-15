#!/usr/bin/env python3
"""Local quote desk for freelancers. Client briefs stay on this machine."""

import json
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "gemma2:2b"
PORT = 8765

SAMPLE = {
    "client": "Mehra Foods",
    "brief": (
        "Hi, we run a cloud kitchen in Lajpat Nagar. Need a one-page menu site "
        "and a WhatsApp order button by next Friday. Also a simple logo. "
        "Budget is around 25k. We can pay half on UPI today."
    ),
}


def inr(value):
    return int(round(value / 500.0) * 500)


def extract_budget(text):
    amounts = []
    for match in re.finditer(
        r"(?:₹|rs\.?|inr)?\s*([0-9][0-9,]*(?:\.\d+)?)\s*(k|thousand)?",
        text,
        re.I,
    ):
        amount = float(match.group(1).replace(",", ""))
        suffix = match.group(2)
        if suffix:
            amount *= 1000
        window = text[max(0, match.start() - 40): match.end() + 8]
        if suffix or re.search(r"budget|₹|rs\.?|inr|pay", window, re.I):
            amounts.append(amount)
    if not amounts:
        return None
    return inr(amounts[-1])


def extract_timeline(text):
    match = re.search(
        r"\b(next\s+\w+|by\s+[a-z]+\s+\d{1,2}|\d+\s+(?:day|days|week|weeks))\b",
        text,
        re.I,
    )
    return match.group(1) if match else "5 working days"


def has_word(text, word):
    return re.search(rf"\b{word}\b", text) is not None


def deliverables_for(text):
    catalog = [
        (has_word(text, "site") or has_word(text, "website"), "One-page site", "Mobile-first page with menu, address, and hours", 12000),
        ("whatsapp" in text, "WhatsApp order button", "Click-to-chat with a prefilled order message", 3000),
        (has_word(text, "logo"), "Logo", "Two concepts, one final mark, PNG and SVG", 6000),
        (has_word(text, "invoice"), "Invoice template", "GST-ready invoice the client can reuse", 4000),
        (has_word(text, "app"), "Small web app", "One working flow, no extra screens", 18000),
    ]
    picked = [item[1:] for item in catalog if item[0]]
    if not picked:
        picked = [("Scoped build", "The work described in the brief, kept to one deliverable", 15000)]
    return picked


def fit_budget(items, budget):
    if budget is None:
        return items
    total = sum(amount for _, _, amount in items)
    if total <= budget:
        return items
    scale = budget / total
    fitted = []
    for name, detail, amount in items:
        fitted.append((name, detail, max(1500, inr(amount * scale))))
    drift = budget - sum(amount for _, _, amount in fitted)
    name, detail, amount = fitted[-1]
    fitted[-1] = (name, detail, max(1500, amount + drift))
    return fitted


def rules_quote(payload):
    brief = (payload.get("brief") or "").strip()
    client = (payload.get("client") or "Client").strip()
    low = brief.lower()
    budget = extract_budget(low)
    items = fit_budget(deliverables_for(low), budget)
    total = sum(amount for _, _, amount in items)
    return {
        "client": client,
        "summary": f"Fixed quote for {client}. The brief stays on this laptop.",
        "deliverables": [
            {"name": name, "detail": detail, "amount_inr": amount}
            for name, detail, amount in items
        ],
        "assumptions": [
            "One round of revisions is included.",
            "Copy and photos come from the client.",
            "Hosting, domain, and ad spend are extra.",
        ],
        "timeline": extract_timeline(low),
        "total_inr": total,
        "payment_terms": "50% on UPI to start, 50% on delivery.",
        "source": "local-rules",
    }


def ollama_quote(payload):
    prompt = (
        "Return only JSON for a freelance quote in INR. Keys: client, summary, "
        "deliverables (list of {name, detail, amount_inr}), assumptions (list), "
        "timeline, total_inr, payment_terms. Use the client's budget if they gave one.\n"
        f"Client: {payload.get('client') or 'Client'}\n"
        f"Brief: {payload.get('brief') or ''}"
    )
    body = json.dumps(
        {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": "json"}
    ).encode()
    request = urllib.request.Request(
        OLLAMA_URL,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        raw = json.loads(response.read().decode())
    quote = json.loads(raw["response"])
    quote["source"] = f"ollama:{OLLAMA_MODEL}"
    return quote


def make_quote(payload):
    try:
        return ollama_quote(payload)
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError, OSError):
        return rules_quote(payload)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send(self, code, body, content_type):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, INDEX.read_text(), "text/html; charset=utf-8")
            return
        if self.path == "/api/sample":
            self._send(200, json.dumps(SAMPLE), "application/json")
            return
        self._send(404, "Not found", "text/plain; charset=utf-8")

    def do_POST(self):
        if self.path != "/api/quote":
            self._send(404, "Not found", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode() or "{}")
        except json.JSONDecodeError:
            self._send(400, json.dumps({"error": "Send JSON."}), "application/json")
            return
        if not (payload.get("brief") or "").strip():
            self._send(400, json.dumps({"error": "Paste a client brief."}), "application/json")
            return
        self._send(200, json.dumps(make_quote(payload)), "application/json")


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Quote desk running at http://127.0.0.1:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
