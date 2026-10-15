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
OLLAMA_MODEL = "gemma3:1b"
PORT = 8787

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


def normalize_quote(quote, client):
    deliverables = quote.get("deliverables")
    if not isinstance(deliverables, list) or not deliverables:
        raise ValueError("missing deliverables")
    cleaned = []
    for item in deliverables:
        if not isinstance(item, dict):
            raise ValueError("bad deliverable")
        name = str(item.get("name") or "").strip()
        detail = str(item.get("detail") or "").strip()
        amount = int(round(float(item.get("amount_inr"))))
        if not name or amount < 0:
            raise ValueError("bad line")
        cleaned.append({"name": name, "detail": detail, "amount_inr": amount})
    assumptions = quote.get("assumptions")
    if not isinstance(assumptions, list):
        assumptions = []
    total = quote.get("total_inr")
    if total is None:
        total = sum(item["amount_inr"] for item in cleaned)
    return {
        "client": str(quote.get("client") or client).strip() or client,
        "summary": str(quote.get("summary") or f"Fixed quote for {client}.").strip(),
        "deliverables": cleaned,
        "assumptions": [str(item) for item in assumptions if str(item).strip()],
        "timeline": str(quote.get("timeline") or "5 working days").strip(),
        "total_inr": int(round(float(total))),
        "payment_terms": str(quote.get("payment_terms") or "50% to start, 50% on delivery.").strip(),
        "source": f"ollama:{OLLAMA_MODEL}",
    }


def ollama_quote(payload):
    client = (payload.get("client") or "Client").strip()
    prompt = (
        "Price freelance work in INR. Return JSON only. "
        "deliverables is a list of objects with name, detail, and amount_inr as numbers. "
        "The letter k after a number means thousands: 25k is 25000. "
        "total_inr must equal the sum of amount_inr and must not exceed a stated budget. "
        "Add one deliverable object for each thing the client asked for. "
        "Write a new quote. Do not copy the example client or prices.\n"
        "Shape example only: "
        '{"client":"Example Studio","summary":"Fixed quote for a poster.",'
        '"deliverables":[{"name":"Poster","detail":"One A3 poster","amount_inr":4000}],'
        '"assumptions":["One revision is included."],"timeline":"3 working days",'
        '"total_inr":4000,"payment_terms":"50% to start, 50% on delivery."}\n'
        f"Client: {client}\n"
        f"Brief: {payload.get('brief') or ''}"
    )
    schema = {
        "type": "object",
        "properties": {
            "client": {"type": "string"},
            "summary": {"type": "string"},
            "deliverables": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "detail": {"type": "string"},
                        "amount_inr": {"type": "integer"},
                    },
                    "required": ["name", "detail", "amount_inr"],
                },
            },
            "assumptions": {"type": "array", "items": {"type": "string"}},
            "timeline": {"type": "string"},
            "total_inr": {"type": "integer"},
            "payment_terms": {"type": "string"},
        },
        "required": ["client", "summary", "deliverables", "timeline", "total_inr", "payment_terms"],
    }
    body = json.dumps(
        {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, "format": schema}
    ).encode()
    request = urllib.request.Request(
        OLLAMA_URL,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = json.loads(response.read().decode())
    return normalize_quote(json.loads(raw["response"]), client)


def make_quote(payload):
    try:
        quote = ollama_quote(payload)
        budget = extract_budget((payload.get("brief") or "").lower())
        if budget is not None and quote["total_inr"] > budget:
            raise ValueError("over budget")
        return quote
    except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError, OSError, ValueError, TypeError):
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
