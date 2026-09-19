"""GloweUp Studio ritual planner — catalog-grounded consumer demo."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CATALOG_PATH = DATA_DIR / "catalog.json"
STATIC_DIR = ROOT / "static"
IMAGES_DIR = DATA_DIR / "images"

H_HARMONY = "hormone-harmony-balance-pms-pmdd-mood-post-pill-health"
H_MAG = "magnesium-oil-spray-unscented"
H_TALLOW = "whipped-tallow-unscented-2-oz"
H_DEO_GL = "grapefruit-lemon-deodorant-cream"
H_ENTHUSIASM = "enthusiasm-daily-dose-drops"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env(ROOT / ".env")

catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
products_by_handle = {p["handle"]: p for p in catalog["products"]}

app = FastAPI(title="GloweUp Studio ritual planner")


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatTurn] = Field(default_factory=list)


class ProductCard(BaseModel):
    handle: str
    title: str
    price: str | None
    url: str
    image: str
    vendor: str
    collections: list[str]
    why: str = ""


class Beat(BaseModel):
    when: str
    product: ProductCard


class DayStep(BaseModel):
    id: str
    label: str


class UsagePlan(BaseModel):
    title: str
    description: str
    handle: str
    product_title: str = ""
    image: str = ""
    steps: list[DayStep] = Field(default_factory=list)


class ChatOut(BaseModel):
    reply: str
    choices: list[str] = Field(default_factory=list)
    ready: bool = False
    ritual_name: str | None = None
    beats: list[Beat] = Field(default_factory=list)
    products: list[ProductCard] = Field(default_factory=list)
    plan: UsagePlan | None = None


def snippet(text: str, n: int = 88, title: str = "") -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if title and text.lower().startswith(title.lower()):
        text = text[len(title) :].lstrip(" -–|:.")
    if not text:
        return ""
    for sep in ".!?":
        i = text.find(sep)
        if 12 < i <= n:
            return text[: i + 1]
    if len(text) <= n:
        return text
    return text[: n - 1].rstrip() + "…"


def compact_catalog() -> list[dict]:
    rows = []
    for p in catalog["products"]:
        rows.append(
            {
                "handle": p["handle"],
                "title": p["title"],
                "vendor": p["vendor"],
                "collections": p["collections"],
                "price": p["price"],
                "available": p["available"],
                "description": p["description_text"],
                "url": p["url"],
            }
        )
    return rows


CATALOG_FOR_LLM = json.dumps(compact_catalog(), ensure_ascii=False)

SYSTEM_PROMPT = f"""You are GloweUp Studio's check-in — a warm, slightly witty friend helping someone notice mood, sleep, and cycle, then pick ONE hormone-safe product from the shop.

Brand: every catalog product is curated to avoid endocrine disruptors.

Conversation:
- Ask ONE question at a time. Short. Like iMessage, not a clinician.
- Cover mood, sleep, and cycle/period only if it wasn't already said. 2–3 questions max, then recommend.
- On question turns: ready=false, beats=[], choices=2-4 tap-sized answers (a Skip option is ok).
- Do NOT recommend a product, name a SKU, or fill beats until you have heard about at least two of: mood, sleep, cycle/body.
- When ready: exactly ONE in-stock catalog product. Tie the why to their answers.
- Also return a tiny daily plan for THAT product: 3 check-in prompts (did you use it / how you felt / keep it?). Not a prescription.
- Never diagnose, treat, or claim to balance hormones. Shopping notes only.
- Catalog only. Exact handles. Empty beats if nothing fits.

Return JSON only:
{{
  "reply": "1-3 short sentences",
  "choices": ["Anxious", "Flat", "Spicy", "Skip"],
  "ready": false,
  "ritual_name": null,
  "beats": [],
  "plan": null
}}

When recommending:
{{
  "reply": "one-line why + invite them to start the daily plan. Not medical advice.",
  "choices": ["Start this plan", "Not now"],
  "ready": true,
  "ritual_name": "2-4 word name",
  "beats": [{{"when": "Tonight", "handle": "exact-handle"}}],
  "plan": {{
    "title": "2-4 word plan name",
    "description": "one or two sentences: when to use it, what to notice. Not medical advice.",
    "steps": ["Did you use it tonight?", "How did mood or sleep feel after?", "Keep this in the ritual?"]
  }}
}}

CATALOG:
{CATALOG_FOR_LLM}
"""

KITS: list[dict] = [
    {
        "keys": ("period", "pms", "pmdd", "cramp", "luteal", "cycle", "bloat"),
        "name": "Luteal soft landing",
        "reply": "If this week is period-ish, this is the one I'd start with from the shop. Shopping note, not a diagnosis.",
        "beats": (("Tonight", H_HARMONY),),
    },
    {
        "keys": ("date", "romantic", "dinner", "glow"),
        "name": "Soft date night",
        "reply": "For glow-without-a-12-step, this is the one catalog pick.",
        "beats": (("Skin", H_TALLOW),),
    },
    {
        "keys": ("sleep", "wind-down", "wind down", "can't sleep", "cant sleep", "insomnia", "rest"),
        "name": "Lights-out",
        "reply": "If sleep is the loudest thing, start here. Not medical advice.",
        "beats": (("Lights out", H_MAG),),
    },
    {
        "keys": ("moisturizer", "dry", "reactive", "tallow", "scrub", "skincare", "skin"),
        "name": "Bare glow",
        "reply": "For dull, dry skin, this is the simple catalog pick.",
        "beats": (("Seal", H_TALLOW),),
    },
    {
        "keys": ("energy", "focus", "stamina", "tired", "slump", "gummies", "mushroom"),
        "name": "Soft focus",
        "reply": "For a soft lift, this is the one I'd try from the shop.",
        "beats": (("Morning", H_ENTHUSIASM),),
    },
    {
        "keys": ("deodorant", "scent", "aluminum"),
        "name": "Stay fresh",
        "reply": "Aluminum- and baking-soda-free from the catalog.",
        "beats": (("Fresh", H_DEO_GL),),
    },
]


def image_url(product: dict) -> str:
    images = product.get("images") or []
    if not images:
        return ""
    local = images[0].get("local")
    if local:
        local_path = DATA_DIR / local
        if local_path.exists():
            return f"/{local.replace(chr(92), '/')}"
    return images[0].get("src") or ""


def to_card(product: dict) -> ProductCard:
    return ProductCard(
        handle=product["handle"],
        title=product["title"],
        price=product.get("price"),
        url=product["url"],
        image=image_url(product),
        vendor=product.get("vendor") or "",
        collections=product.get("collections") or [],
        why=snippet(product.get("description_text") or "", title=product.get("title") or ""),
    )


def default_plan(card: ProductCard, ritual_name: str | None) -> UsagePlan:
    return UsagePlan(
        title=ritual_name or "Daily ritual",
        description=(card.why or "Use it the way the label says. Tap how it felt each day — shopping notes, not a prescription."),
        handle=card.handle,
        product_title=card.title,
        image=card.image,
        steps=[
            DayStep(id="use", label="Did you use it today?"),
            DayStep(id="notice", label="How did mood or sleep feel?"),
            DayStep(id="honest", label="Keep this in the ritual?"),
        ],
    )


def parse_plan(raw: object, card: ProductCard, ritual_name: str | None) -> UsagePlan:
    if not isinstance(raw, dict):
        return default_plan(card, ritual_name)
    title = re.sub(r"\s+", " ", str(raw.get("title") or ritual_name or "Daily ritual")).strip()[:48]
    desc = re.sub(r"\s+", " ", str(raw.get("description") or "")).strip()[:280]
    steps_raw = raw.get("steps") or []
    steps: list[DayStep] = []
    if isinstance(steps_raw, list):
        for i, item in enumerate(steps_raw[:3]):
            label = re.sub(r"\s+", " ", str(item if not isinstance(item, dict) else item.get("label") or "")).strip()
            if label:
                steps.append(DayStep(id=f"s{i}", label=label[:90]))
    if not steps:
        return default_plan(card, title)
    return UsagePlan(
        title=title or "Daily ritual",
        description=desc or default_plan(card, title).description,
        handle=card.handle,
        product_title=card.title,
        image=card.image,
        steps=steps,
    )


def one_beat(when: str, handle: str) -> tuple[list[Beat], list[ProductCard]]:
    if handle not in products_by_handle:
        return [], []
    card = to_card(products_by_handle[handle])
    beat = Beat(when=when or "Tonight", product=card)
    return [beat], [card]


def kit_out(name: str, reply: str, beats: tuple[tuple[str, str], ...]) -> ChatOut:
    when, handle = beats[0]
    beat_models, products = one_beat(when, handle)
    plan = parse_plan(None, products[0], name) if products else None
    return ChatOut(
        reply=reply,
        choices=["Start this plan", "Not now"] if products else [],
        ready=bool(products),
        ritual_name=name,
        beats=beat_models,
        products=products,
        plan=plan,
    )


def pick_kit(query: str) -> dict | None:
    q = query.lower()
    for kit in KITS:
        if any(k in q for k in kit["keys"]):
            return kit
    return None


def lexical_match(query: str) -> ChatOut:
    """ponytail: one-SKU fallback if the model is down; not the happy path."""
    kit = pick_kit(query)
    if kit:
        return kit_out(kit["name"], kit["reply"], kit["beats"])
    tokens = [
        t
        for t in re.findall(r"[a-z0-9]+", query.lower())
        if len(t) > 2
        and t
        not in {
            "the",
            "and",
            "for",
            "with",
            "help",
            "me",
            "my",
            "from",
            "that",
            "this",
            "you",
            "your",
            "please",
            "free",
            "tonight",
        }
    ]
    scored: list[tuple[int, dict]] = []
    for product in catalog["products"]:
        blob = " ".join(
            [
                product["title"],
                product.get("vendor") or "",
                " ".join(product.get("collections") or []),
                product.get("description_text") or "",
            ]
        ).lower()
        score = sum(3 if t in product["title"].lower() else 1 for t in tokens if t in blob)
        if score:
            scored.append((score, product))
    scored.sort(key=lambda row: (-row[0], row[1]["title"]))
    if not scored:
        return ChatOut(
            reply="Tell me about mood or sleep and I’ll pick one thing from the GloweUp catalog.",
            choices=["Mood's off", "Can't sleep", "Period-ish", "Skip"],
            ready=False,
        )
    pick = scored[0][1]
    return kit_out(
        "For you",
        "Closest single match from the live catalog. Shopping notes only — not medical advice.",
        (("Tonight", pick["handle"]),),
    )


def clean_choices(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw[:4]:
        text = re.sub(r"\s+", " ", str(item)).strip()
        if text and text not in out:
            out.append(text[:40])
    return out


def pack_from_llm(parsed: dict, *, user_turns: int) -> ChatOut:
    reply = str(parsed.get("reply") or "").strip() or "How's your body tonight?"
    name = parsed.get("ritual_name")
    name = str(name).strip() if name else None
    choices = clean_choices(parsed.get("choices"))
    ready = bool(parsed.get("ready")) and user_turns >= 2

    if not ready:
        return ChatOut(reply=reply, choices=choices or ["Mood's off", "Can't sleep", "Pretty okay"], ready=False)

    handle = ""
    when = "Tonight"
    raw_beats = parsed.get("beats") or []
    if isinstance(raw_beats, list):
        for beat in raw_beats:
            if not isinstance(beat, dict):
                continue
            candidate = str(beat.get("handle") or "")
            if candidate in products_by_handle:
                handle = candidate
                when = str(beat.get("when") or "Tonight").strip() or "Tonight"
                break
    if not handle:
        extra = parsed.get("handles") or []
        if isinstance(extra, list):
            for h in extra:
                if str(h) in products_by_handle:
                    handle = str(h)
                    break
    beat_models, products = one_beat(when, handle)
    if not products:
        return ChatOut(
            reply=reply + " I don't have a catalog match yet — want to tell me about sleep?",
            choices=["Can't sleep", "Sleep's fine", "Skip"],
            ready=False,
        )
    plan = parse_plan(parsed.get("plan"), products[0], name)
    return ChatOut(
        reply=reply,
        choices=["Start this plan", "Not now"],
        ready=True,
        ritual_name=name,
        beats=beat_models,
        products=products,
        plan=plan,
    )


def call_llm(body: ChatIn, api_key: str) -> ChatOut:
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in body.history[-10:]:
        if turn.role in {"user", "assistant"} and turn.content.strip():
            messages.append({"role": turn.role, "content": turn.content.strip()})
    messages.append({"role": "user", "content": body.message.strip()})
    client = OpenAI(api_key=api_key)
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
    completion = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        temperature=0.5,
        messages=messages,
    )
    raw = completion.choices[0].message.content or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"reply": raw, "ready": False, "beats": []}
    user_turns = 1 + sum(1 for t in body.history if t.role == "user")
    return pack_from_llm(parsed, user_turns=user_turns)


@app.get("/api/catalog")
def get_catalog() -> dict:
    return {
        "store": catalog["store"],
        "product_count": catalog["product_count"],
        "collections": catalog["collections"],
        "products": [
            {
                **to_card(p).model_dump(),
                "description": p["description_text"],
                "available": p["available"],
            }
            for p in catalog["products"]
        ],
    }


@app.post("/api/chat", response_model=ChatOut)
def chat(body: ChatIn) -> ChatOut:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key or api_key.startswith("sk-your-"):
        return ChatOut(
            reply="Add an OpenAI key to .env so I can check in with you. Until then: how's mood and sleep tonight?",
            choices=["Mood's off", "Can't sleep", "Period-ish"],
            ready=False,
        )
    try:
        return call_llm(body, api_key)
    except Exception:
        return lexical_match(body.message)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


if IMAGES_DIR.exists():
    app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
