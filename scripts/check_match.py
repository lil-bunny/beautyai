import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import lexical_match, pack_from_llm

deo = {p.handle for p in lexical_match("aluminum-free deodorant").products}
assert deo == {"grapefruit-lemon-deodorant-cream"}, deo

period = lexical_match("I'm in period week — cramps, mood, bloating.")
assert period.ritual_name == "Luteal soft landing", period.ritual_name
assert len(period.products) == 1
assert period.products[0].handle == "hormone-harmony-balance-pms-pmdd-mood-post-pill-health"

sleep = lexical_match("help me sleep")
assert sleep.products[0].handle == "magnesium-oil-spray-unscented"

early = pack_from_llm(
    {
        "reply": "How's sleep?",
        "ready": True,
        "beats": [{"when": "Tonight", "handle": "magnesium-oil-spray-unscented"}],
    },
    user_turns=1,
)
assert not early.ready and not early.products

ready = pack_from_llm(
    {
        "reply": "Start here.",
        "ready": True,
        "beats": [
            {"when": "Tonight", "handle": "magnesium-oil-spray-unscented"},
            {"when": "Also", "handle": "feminism-rose-chai-superbrew"},
        ],
    },
    user_turns=2,
)
assert ready.ready and len(ready.products) == 1
assert ready.products[0].handle == "magnesium-oil-spray-unscented"
assert ready.plan and ready.plan.handle == "magnesium-oil-spray-unscented"
assert ready.plan.steps
print("lexical_match ok")
