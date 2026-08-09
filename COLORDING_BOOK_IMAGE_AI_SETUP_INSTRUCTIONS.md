# Coloring Book AI Image Setup

## Requirements

Coloring Book AI Image mode requires:

```
AI_INTEGRATIONS_OPENAI_API_KEY
AI_INTEGRATIONS_OPENAI_BASE_URL
```

## Setup

1. Open `flask_app/.env`
2. Replace `PASTE_YOUR_OPENAI_API_KEY_HERE` with your real OpenAI API key
3. Save the file
4. Restart the Flask app

## Status Check

After restarting, open:

```
GET /coloring-ai-status
```

Ready state should show:

- `api_key_present`: `true`
- `base_url_present`: `true`
- `ready`: `true`

## If Not Ready

If `ready` is `false`, do not generate AI Image Coloring Page. The quality gate will block it and show an error.

## Basic Test Fallback

Basic Test Fallback still works without any API key. It is not sellable quality.
