# Interior Estimate Bot (Telegram POC)

A proof-of-concept Telegram bot that walks a user through:
floor plan upload → style selection → budget selection → mocked cost
estimate → budget-comparison branch → consultation CTA.

## Architecture (matches the flow diagram)

- **Agent 1** — `estimate_area_from_image()` in `bot.py`. Sends the uploaded
  floor plan to Gemini's vision API (`gemini-2.5-flash-lite`, free-tier
  friendly) and asks for a rough sq ft estimate. This is intentionally
  approximate.
- **Agent 2** — `estimate_cost()` in `pricing.py`. Uses a **mocked**
  ₹/sq ft rate table (one rate per style tier) to compute scope + cost.
  No real vendor pricing is used — tune `STYLE_TIERS` freely.
- **Branch logic** — `compare_to_budget()` in `pricing.py` decides whether
  the estimate is over, under, or matching the user's stated budget, and
  the bot sends the corresponding message + buttons from the diagram.
- **Dead ends** — "I'll explore later", "I'm happy with this",
  "Find Interior Partners", "Download Estimate" all just show a short
  closing message and end the conversation (as agreed for the POC).

## Prerequisites

- Python 3.10+
- A Telegram bot token (from @BotFather)
- A Gemini API key (free tier, from Google AI Studio)

## Setup — exact steps

### 1. Create your Telegram bot
1. Open Telegram, search **@BotFather**
2. Send `/newbot`
3. Give it a display name, then a username ending in `bot`
4. Copy the token BotFather gives you

### 2. Get a Gemini API key (free)
1. Go to https://aistudio.google.com/apikey
2. Sign in with a Google account → **Create API Key**
3. Copy the key — no credit card required for the free tier
4. Free tier has rate limits (requests per minute/day), which is more
   than enough for POC testing

### 3. Set up the project locally
```bash
git clone <your-repo-url>
cd interior-bot
python3 -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```
Now open `.env` and paste in your two tokens:
```
TELEGRAM_BOT_TOKEN=7123456789:AAHdq...
GEMINI_API_KEY=AIzaSy...
```

### 4. Run it
```bash
python bot.py
```
Open Telegram, find your bot, send `/start`, and upload a floor plan image.

## Deploying so it stays online (optional, for sharing the demo)

**Railway (recommended, free tier is enough for a POC):**
1. Push this repo to GitHub (see Git section below)
2. Go to railway.app → New Project → Deploy from GitHub repo
3. Add your two env vars (`TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`) in
   Railway's Variables tab
4. Set the start command to `python bot.py`
5. Deploy — Railway keeps it running so the bot responds even when your
   laptop is off

## Setting up Git (do this once, from inside the `interior-bot` folder)

```bash
git init
git add .
git commit -m "Initial POC: Telegram interior estimate bot"
```

Then create an empty repo on GitHub (no README/gitignore, since you
already have them), and connect it:

```bash
git remote add origin https://github.com/<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
```

`.env` is already excluded via `.gitignore` — never commit real tokens.

## Known limitations (by design, for a POC)

- Area estimate from the floor plan is a rough AI guess, not a real
  measurement/CV pipeline.
- Pricing is a mocked flat ₹/sq ft rate per style tier, not a real quote.
- Confidence score (91%) is a fixed display value, not statistically computed.
- "Download Estimate", "Find Interior Partners", and "Book a Free
  Consultation" just show closing text — no PDF generation, partner
  matching, or calendar booking is wired up yet.