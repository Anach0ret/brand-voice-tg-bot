# brand-voice-tg-bot

A Telegram bot that generates marketing copy in a fixed **brand voice** via the
Gemini API. Send it a task in plain text — a social post, a product description,
a customer reply — and it answers the way the brand would.

The brand's voice, product line and rules live in two plain-text files
(`prompts/system_prompt.md`, `prompts/checklist.md`). Swap them and the bot
speaks for a different brand. This repo ships `*.example.md` stubs; the real
prompts are git-ignored.

Built as a course project (a wrapper around a Gemini "Gem"), kept generic enough
to reuse.

## Features

| Command | What it does |
|---|---|
| any text | generates copy in the brand voice; picks the mode (social / product / PR / complaint) from the request |
| `/check` | Brand-Voice compliance: a second call rates the last answer against `checklist.md` (matches / partial / no + violations) |
| `/reset` | clears the conversation history for that user |
| `/stats` | request counters for the session + current model |

- **Model fallback.** `GEMINI_MODEL` is a comma-separated list. On a daily-quota
  `429` or a missing model `404` the bot moves to the next one; transient
  `429/500/503` are retried twice with backoff. History carries over on a switch.
- **No database, no webhooks.** Conversation history lives in process memory
  (per Telegram user) and is lost on restart. Long polling.

## Run with Docker (recommended)

Needs Docker with the Compose plugin.

```sh
git clone https://github.com/Anach0ret/brand-voice-tg-bot.git && cd brand-voice-tg-bot

cp .env.example .env
# edit .env — set BOT_TOKEN and GEMINI_API_KEY

cp prompts/system_prompt.example.md prompts/system_prompt.md
cp prompts/checklist.example.md     prompts/checklist.md
# edit both — describe your brand (or run as-is on the example brand)

docker compose up -d --build
docker compose logs -f          # watch it start
docker compose down             # stop
```

The container restarts unless stopped (`restart: unless-stopped`). It reads
`.env` and the `prompts/` directory from the build context.

## Run locally (development)

Needs [uv](https://docs.astral.sh/uv/).

```sh
cp .env.example .env
cp prompts/system_prompt.example.md prompts/system_prompt.md
cp prompts/checklist.example.md     prompts/checklist.md

uv run bot
```

## Configuration (`.env`)

| Variable | |
|---|---|
| `BOT_TOKEN` | from [@BotFather](https://t.me/BotFather) (`/newbot`) — **required** |
| `GEMINI_API_KEY` | from [Google AI Studio](https://aistudio.google.com/apikey) — **required**. New keys start with `AQ.` |
| `GEMINI_MODEL` | comma-separated model list, priority order. Optional — a 7-model default with fallback is built in. `lite` models get ~1000 free requests/day, full `flash` only ~20 |
| `ALLOWED_USER_IDS` | comma-separated Telegram user IDs allowed to use the bot. Empty = open to everyone |

## Layout

```
src/brand_voice_tg_bot/
  __init__.py    main() — wire dependencies, start long polling
  config.py      Config      — reads .env
  prompts.py     Prompts     — loads prompts/ (falls back to *.example.md)
  modelpool.py   ModelPool   — model list with fallback
  assistant.py   Assistant   — one per user: Gemini chat session, retry, fallback
  handlers.py    Commands    — Telegram handlers, command auto-registration, menu
  stats.py       Stats       — session counters
prompts/
  system_prompt.example.md   brand voice, product line, rules (template)
  checklist.example.md       what /check flags (template)
```
