# GloweUp Studio ritual planner

Consumer demo: a short AI check-in (mood, sleep, cycle) that recommends **one** hormone-safe product from the live [GloweUp Studio](https://gloweupstudio.com/collections/all) catalog. It does not scrape HTML, invent products, or give medical advice.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Put a real `OPENAI_API_KEY` in `.env`. Optional: `OPENAI_MODEL` (default `gpt-4o-mini`). The check-in needs the key.

## Ingest the catalog

```bash
python scripts/ingest.py
python scripts/check_match.py
```

Writes `data/catalog.json` and downloads images to `data/images/{handle}/`. Re-run anytime the shop changes.

## Run the demo

```bash
uvicorn app:app --reload --port 8000
```

Open http://127.0.0.1:8000

## Founder walkthrough

1. Land on **How’s your body tonight?** — not a product grid.
2. Tap **Period-ish**. Expect a question (mood or sleep), with tap chips. No product yet.
3. Answer two chips. Then **one** catalog card, not a three-pack. Heart it into **My ritual**.
4. After the product, tap **Start this plan**. It lands in the **My plans** sidebar with a description and daily checkboxes.

This is a demo against public storefront JSON. It is not a storefront clone, checkout, or medical product.
