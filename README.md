# T2T — Training Intelligence Platform

A professional AI-powered web app for training consultants, instructional designers, and career mentors.

## Features

- **💬 Chat Mode** — Conversational consulting, coaching, and Q&A
- **📄 Document Mode** — Generates full lesson plans, TNA reports, RFP responses, evaluation frameworks, and more
- **🔍 Research Mode** — Live web search integrated with expert responses

---

## Quick Start (Local)

### 1. Clone & Install

```bash
pip install -r requirements.txt
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Edit `.env` and add your OpenAI API key:
```
OPENAI_API_KEY=sk-proj-your-key-here
SECRET_KEY=any-long-random-string
```

### 3. Run

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000)

---

## Deploy to Railway (Recommended — Free Tier Available)

1. Push this folder to a GitHub repo
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. In Settings → Variables, add:
   - `OPENAI_API_KEY` = your key
   - `SECRET_KEY` = any random string (e.g. generate one at [randomkeygen.com](https://randomkeygen.com))
4. Railway auto-detects the Procfile and deploys — you get a public URL

## Deploy to Render (Also Free Tier)

1. Push to GitHub
2. Go to [render.com](https://render.com) → New Web Service → Connect repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120`
5. Add environment variables (same as above)

---

## Customisation

- **System prompt**: Edit the `SYSTEM_PROMPT` variable in `app.py`
- **Branding**: Change "T2T" to your app name in `templates/index.html` and `static/style.css`
- **Model**: Change `gpt-4o` in `app.py` to `gpt-4.1` or `gpt-4o-mini` to adjust cost/quality
- **Quick starters**: Edit the `.starter-btn` buttons in `templates/index.html`

---

## Tech Stack

- **Backend**: Python / Flask
- **AI**: OpenAI Responses API + Chat Completions API
- **Web Search**: OpenAI `web_search_preview` tool
- **Frontend**: Vanilla HTML/CSS/JS with marked.js for Markdown rendering

---

## Security Notes

- Never commit your `.env` file (it's in `.gitignore` by default)
- Regenerate your API key if it was ever shared publicly
- Add authentication before sharing the URL publicly (consider using a simple password middleware or a service like Cloudflare Access)
