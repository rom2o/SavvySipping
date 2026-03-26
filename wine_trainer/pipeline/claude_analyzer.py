"""
claude_analyzer.py – Five-call Claude pipeline for SavvySipping.

Generic sections (vocabulary, wine basics, pairing) injected from static_content.py.

Call 1a → claude-opus-4-6  (max_tokens=4000)
    Course Overview only — 2-3 paragraphs, restaurant-specific welcome.

Call 1b → claude-opus-4-6  (max_tokens=16000, multi-turn)
    Section 3: All wine tasting notes. Needs Call 1a context for tone consistency.

Call 1c → claude-opus-4-6  (max_tokens=16000, INDEPENDENT — not multi-turn)
    Sections 4–7: Regions, Sales Scripts, Notes for Management.
    Only needs the wine list — no tasting notes context required.
    Saves ~13,000 input tokens vs. carrying the full multi-turn chain.

Call 1B → claude-opus-4-6  (max_tokens=4000)
    Cheat Sheet only.

Call 2  → claude-sonnet-4-6  (max_tokens=6000)
    Knowledge Test (21 MCQ + 3 scenarios) and Answer Key.
"""

import os
import re
import logging
import anthropic

from .static_content import HOW_WINE_IS_MADE, WINE_VOCABULARY, WINE_PAIRING_PRINCIPLES
from .wine_selector import maybe_select_wines
logger = logging.getLogger(__name__)

PERSONA = """
You are a Master Sommelier and hospitality training expert with 20+ years of
experience designing wine education programmes for fine-dining and casual
restaurants worldwide. You write in a clear, engaging, authoritative voice
that motivates wait staff while remaining accessible to beginners.

Your training materials are:
• Accurate and specific (grape varieties, regions, production methods)
• Rich with guest-facing stories and memorable anecdotes
• Full of practical, word-for-word scripts staff can use at the table
• Organised so staff can find what they need fast during a busy service
"""

# ─────────────────────────────────────────────────────────────────────────────
# CALL 1a – Course Overview only (2-3 paragraphs)
# ─────────────────────────────────────────────────────────────────────────────
CALL1A_PROMPT = """
You are creating the Wine Mastery Training Guide for **{restaurant_name}**, a {cuisine_style} restaurant.
The audience is {staff_description}.

Wine list extracted from their PDF:

{wine_list_text}

════════════════════════════════════════════════════════════════════════════════
PRODUCE THE COURSE OVERVIEW ONLY — nothing else.
════════════════════════════════════════════════════════════════════════════════

# Wine Mastery Training Guide — {restaurant_name}
### Front-of-House Staff Training

---

## 1. Course Overview

Write 2–3 paragraphs welcoming staff to the programme. Mention {restaurant_name} by name.
Explain why wine knowledge matters specifically for this restaurant's style and guests.
Describe how the guide is structured and estimate the read time.

---

End your response after the Course Overview. Do not write anything further.
"""

# ─────────────────────────────────────────────────────────────────────────────
# CALL 1b – Section 3: Tasting Notes (multi-turn, needs tone context from 1a)
# ─────────────────────────────────────────────────────────────────────────────
CALL1B_CONTINUATION = """
Continue the Wine Mastery Training Guide for **{restaurant_name}**.
The introduction is written above. Now produce Section 3 only.
Do NOT repeat anything already written. Start directly with the Section 3 heading.

---

## 3. Module 1 — Our Wine Styles & Tasting Notes

Group ALL wines from the wine list into style groups:
Crisp Whites | Aromatic Whites | Rich Whites | Rare Whites | Rosé |
Champagne & Sparkling | Light Reds | Medium Reds | Full-Bodied Reds | Dessert & Fortified

Use EXACTLY this 3-line format for every wine — no more, no less:

**Producer, Vintage, Region** | $Price
- *Grapes:* X. *Taste:* [10 words max — key flavours only]. *Pairs with:* [2–3 foods].
- *Guest profile:* [one short phrase]. *Upsell to:* [specific wine or "the bottle"].

Skip any style group with no wines. Include every wine on the list.
End cleanly after the last style group. Do NOT begin Section 4.
"""

# ─────────────────────────────────────────────────────────────────────────────
# CALL 1c – Sections 4–7: Regions, Sales, Notes (INDEPENDENT — wine list only)
# ─────────────────────────────────────────────────────────────────────────────
CALL1C_PROMPT = """
You are completing the Wine Mastery Training Guide for **{restaurant_name}**, a {cuisine_style} restaurant.
The audience is {staff_description}.

Wine list:

{wine_list_text}

════════════════════════════════════════════════════════════════════════════════
PRODUCE SECTIONS 4, 5, AND 7 ONLY. Start directly with the Section 4 heading.
════════════════════════════════════════════════════════════════════════════════

## 4. Module 2 — Regions & Stories

For each wine region on the list write EXACTLY:
- 2 sentences on geography, climate, and defining wine character
- 1 guest-ready story or memorable fact (2 sentences max)
- Which of our wines come from here (list the names)

Only include regions actually present on the wine list. Keep each entry tight.

---

## 5. Module 3 — Sales & Upsell Techniques

### Word-for-Word Upsell Scripts
For each style group present on our list: EXACTLY 2 sentences in first person.
> *"Script goes here."*

Include one Coravin script (if applicable) and one script for "the guest who doesn't drink wine."

### 5 Golden Rules for Selling Wine at {restaurant_name}
Numbered 1–5. **Bold the rule name.** 1–2 sentences each. No padding.

---

## 7. Notes for Management
Flag typos, misclassified wines, or inconsistencies in the wine list.
Bullet points only. Be specific. Maximum 10 bullets.

---

FORMATTING: Markdown headings (##, ###), bold, quoted scripts: > *"like this"*
Stick to the length limits. This is the final section of the guide.
"""

# ─────────────────────────────────────────────────────────────────────────────
# CALL 1B – Cheat Sheet
# ─────────────────────────────────────────────────────────────────────────────
CALL1B_PROMPT = """
You have just written a full wine training guide for **{restaurant_name}**.
Now produce ONLY the one-page Cheat Sheet that staff keep in their apron pocket.

Here is a summary of the wine list and training content:

{training_summary}

════════════════════════════════════════════════════════════════════════════════
PRODUCE THE CHEAT SHEET ONLY — nothing else.
════════════════════════════════════════════════════════════════════════════════

# Wine Cheat Sheet — {restaurant_name}
*Print this. Keep it in your apron pocket.*

---

### Wine Styles at a Glance
Markdown table: | Style | Key Wines | Best Paired With | Glass Price Range |
Include ALL style groups present on the wine list.

---

### Quick Upsell Map
For every by-the-glass wine → suggest the bottle or premium upgrade.
- **[Entry wine] by the glass** → [Premium wine] ([short reason])

---

### Coravin Pour Wines
Table: | Wine | Style | Glass Price |
One sentence on when to mention Coravin to guests.

---

### Key Vocabulary (Quick Version)
Inline, pipe-separated: **Term** = 3-word definition | **Term** = definition | …
Cover at least 12 terms.

---

### If a Guest Asks Something You Don't Know
> *"That's a great question — let me find out for you right now."*

RULES: Be concise. Use real wine names from the list. No padding or filler.
"""

# ─────────────────────────────────────────────────────────────────────────────
# CALL 2 – Knowledge Test + Answer Key
# ─────────────────────────────────────────────────────────────────────────────
CALL2_PROMPT = """
Create a wine knowledge test for wait staff at **{restaurant_name}**, a {cuisine_style} restaurant.

Training content summary:
{training_summary}

════════════════════════════════════════════════════════════════════════════════
PRODUCE TWO DOCUMENTS separated by the heading "# Answer Key"
════════════════════════════════════════════════════════════════════════════════

# Wine Knowledge Test — {restaurant_name}

## Instructions
Circle the correct answer. For Scenarios, write 2–3 sentences.
Time: 30 minutes. Pass mark: 70% (15/21).

---

## Section A: Multiple Choice (21 Questions)

**EASY (7)** — terminology, NV, Coravin, grape varieties
**MEDIUM (7)** — regions, pairing logic, upsell scenarios
**HARD (7)** — specific wines, vintages, premium bottles

Format:
**Q1. [Question]**
A) ...   B) ...   C) ...   D) ...

---

## Section B: Service Scenarios

**Scenario 1:** [Guest situation]
*Your response:* _______________

**Scenario 2:** [Pairing challenge or complaint]
*Your response:* _______________

**Scenario 3:** [Premium upsell opportunity]
*Your response:* _______________

---

# Answer Key

*(Manager copy — do not give to staff before the test)*

## Section A Answers

| Q | Answer | Explanation |
|---|--------|-------------|
| 1 | X) ... | ...         |

(all 21 rows)

## Section B Model Answers

**Scenario 1 — Model Answer:** (3–4 sentences)
**Scenario 2 — Model Answer:** (3–4 sentences)
**Scenario 3 — Model Answer:** (3–4 sentences)

RULES: Reference actual wines from the list. No answers visible in staff copy.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────
def analyze_wine_list(
    wine_list_text: str,
    restaurant_name: str,
    cuisine_style: str,
    staff_description: str,
    api_key: str = None,
) -> dict:
    wine_list_text = maybe_select_wines(wine_list_text)
    resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not resolved_key:
        raise ValueError("No Anthropic API key provided. Set ANTHROPIC_API_KEY in .env")

    client = anthropic.Anthropic(api_key=resolved_key)

    base_user_msg = CALL1A_PROMPT.format(
        restaurant_name=restaurant_name,
        cuisine_style=cuisine_style,
        staff_description=staff_description,
        wine_list_text=wine_list_text,
    )

    # ── Call 1a: Course Overview (2-3 paragraphs only) ────────────────────────
    logger.info("Call 1a starting — Course Overview (claude-opus-4-6, max_tokens=4000)…")
    r1a = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4000,
        system=PERSONA,
        messages=[{"role": "user", "content": base_user_msg}],
    )
    part1_md = r1a.content[0].text.strip()
    logger.info(f"Call 1a complete — {len(part1_md):,} chars | stop={r1a.stop_reason}")
    if r1a.stop_reason == "max_tokens":
        logger.warning("⚠️  Call 1a hit token limit.")

    # Inject static generic content to complete Section 2
    static_section2 = (
        "\n\n## 2. Introduction to Wine Basics\n\n" +
        HOW_WINE_IS_MADE +
        "\n\n---\n\n" +
        WINE_VOCABULARY +
        "\n\n---\n\n" +
        WINE_PAIRING_PRINCIPLES
    )
    part1_full = part1_md + static_section2
    logger.info(f"Section 2 assembled with static content — {len(part1_full):,} chars total")

    # ── Call 1b: Section 3 — tasting notes (multi-turn for tone consistency) ──
    logger.info("Call 1b starting — Section 3 tasting notes (claude-opus-4-6, max_tokens=16000)…")
    r1b_train = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=16000,
        system=PERSONA,
        messages=[
            {"role": "user",      "content": base_user_msg},
            {"role": "assistant", "content": part1_md},
            {"role": "user",      "content": CALL1B_CONTINUATION.format(
                restaurant_name=restaurant_name,
            )},
        ],
    )
    part2_md = r1b_train.content[0].text.strip()
    logger.info(f"Call 1b complete — {len(part2_md):,} chars | stop={r1b_train.stop_reason}")
    if r1b_train.stop_reason == "max_tokens":
        logger.warning("⚠️  Call 1b hit token limit — Section 3 may be truncated.")

    # ── Call 1c: Sections 4–7 — INDEPENDENT (wine list only, no tasting notes) ─
    logger.info("Call 1c starting — Sections 4–7 (claude-opus-4-6, max_tokens=16000)…")
    r1c = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=16000,
        system=PERSONA,
        messages=[{"role": "user", "content": CALL1C_PROMPT.format(
            restaurant_name=restaurant_name,
            cuisine_style=cuisine_style,
            staff_description=staff_description,
            wine_list_text=wine_list_text,
        )}],
    )
    part3_md = r1c.content[0].text.strip()
    logger.info(f"Call 1c complete — {len(part3_md):,} chars | stop={r1c.stop_reason}")
    if r1c.stop_reason == "max_tokens":
        logger.warning("⚠️  Call 1c hit token limit — Sections 4–7 may be truncated.")

    # Assemble the full training guide
    training_md = part1_full + "\n\n" + part2_md + "\n\n" + part3_md
    logger.info(f"Training Guide assembled — {len(training_md):,} chars total")

    # ── Call 1B: Cheat Sheet ──────────────────────────────────────────────────
    logger.info("Call 1B starting — Cheat Sheet (claude-opus-4-6, max_tokens=4000)…")
    r1b = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4000,
        system=PERSONA,
        messages=[{"role": "user", "content": CALL1B_PROMPT.format(
            restaurant_name=restaurant_name,
            training_summary=training_md[:6000],
        )}],
    )
    cheat_md = r1b.content[0].text.strip()
    logger.info(f"Call 1B complete — {len(cheat_md):,} chars | stop={r1b.stop_reason}")

    # ── Call 2: MCQ + Answer Key ──────────────────────────────────────────────
    logger.info("Call 2 starting — Knowledge Test (claude-sonnet-4-6, max_tokens=6000)…")
    r2 = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=6000,
        system=PERSONA,
        messages=[{"role": "user", "content": CALL2_PROMPT.format(
            restaurant_name=restaurant_name,
            cuisine_style=cuisine_style,
            training_summary=training_md[:5000],
        )}],
    )
    call2_text = r2.content[0].text.strip()
    logger.info(f"Call 2 complete — {len(call2_text):,} chars")

    m = re.compile(r"^#{1,2}\s+answer\s+key", re.IGNORECASE | re.MULTILINE).search(call2_text)
    mcq_md = call2_text[:m.start()].strip() if m else call2_text
    key_md = call2_text[m.start():].strip() if m else ""

    logger.info(f"Training: {len(training_md):,} | Cheat: {len(cheat_md):,} | "
                f"MCQ: {len(mcq_md):,} | Key: {len(key_md):,}")

    return {
        "training_guide": training_md,
        "cheat_sheet":    cheat_md,
        "knowledge_test": mcq_md,
        "answer_key":     key_md,
    }
