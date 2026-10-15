# Brief to Quote

A local quote desk for freelancers. Paste a client’s WhatsApp brief and get a fixed quote in rupees: deliverables, total, timeline, and payment terms.

Client text stays on the laptop. If [Ollama](https://ollama.com) is running with `gemma3:1b`, the quote comes from that open-weight Gemma model. Otherwise the app prices the brief with local rules so it still runs.

## Run

```bash
python3 app.py
```

Open http://127.0.0.1:8787

## Optional local model

```bash
ollama pull gemma3:1b
ollama serve
```

Restart the app after the model is available. The quote response shows `ollama:gemma3:1b` when that path is used. The model is Google's Gemma 3 1B, which is open-weight and runs on a laptop. A quote that is not valid JSON, or that costs more than the client's budget, is replaced by the local price list.
