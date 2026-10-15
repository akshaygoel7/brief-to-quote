# Brief to Quote

A local quote desk for freelancers. Paste a client’s WhatsApp brief and get a fixed quote in rupees: deliverables, total, timeline, and payment terms.

Client text stays on the laptop. If [Ollama](https://ollama.com) is running with `gemma2:2b`, the quote comes from that open-weight model. Otherwise the app prices the brief with local rules so it still runs.

## Run

```bash
python3 app.py
```

Open http://127.0.0.1:8765

## Optional local model

```bash
ollama pull gemma2:2b
ollama serve
```

Restart the app after the model is available. The quote response shows `ollama:gemma2:2b` when that path is used.
