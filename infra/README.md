# Infrastructure

Deployment and runtime configuration for the fact-checking service.

```
infra/
├── compose/       # Docker Compose — local Ollama runtime (development)
└── terraform/     # Cloud infrastructure (placeholder — not yet implemented)
```

---

## compose/ — Local environment

Runs Ollama (the LLM runtime that powers all three agents).

## Bring up

```bash
docker compose up -d
docker compose logs -f ollama   # watch until "Listening on 0.0.0.0:11434"
```

## Pull the model the agents will use

The default model is large and assumes a workstation GPU.

```bash
# Default — 70B, ~40 GB on disk, needs ~48 GB VRAM (or runs slow on CPU)
docker exec -it ollama ollama pull llama3.1:70b-instruct

# Smaller fallback if VRAM is tight (set OLLAMA_MODEL=qwen2.5:7b-instruct in .env)
docker exec -it ollama ollama pull qwen2.5:7b-instruct
```

Tool-calling quality drops below ~30B parameters. If verification gives shaky verdicts, the model — not the prompt — is usually the cause.

## Sanity check

```bash
curl http://localhost:11434/api/tags          # lists pulled models
curl http://localhost:11434/api/generate -d '{"model":"qwen2.5:7b-instruct","prompt":"reply with the single word OK","stream":false}'
```

## Tear down

```bash
docker compose down            # keep model cache
docker compose down -v         # also delete the ~40 GB volume
```
