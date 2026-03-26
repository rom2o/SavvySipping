import re
import logging

MAX_TRAINING_WINES = 70
LARGE_LIST_THRESHOLD = 25_000

MAIN_CATEGORIES = {
    'Sparkling & Champagne': [
        'sparkling', 'champagne', 'prosecco', 'cava', 'sekt', 'crémant', 'cremant'
    ],
    'White Wines': [
        'riesling', 'chardonnay', 'sauvignon', 'semillon', 'pinot gris',
        'pinot grigio', 'chenin', 'viognier', 'marsanne', 'roussanne',
        'white', 'chablis', 'gewürz', 'gewurz', 'grüner', 'gruner',
        'vermentino', 'albariño', 'albarino', 'fiano', 'garganega',
        'blanc', 'alternative white'
    ],
    'Rosé & Orange': [
        'rosé', 'rose', 'orange', 'chilled red'
    ],
    'Red Wines': [
        'pinot noir', 'cabernet', 'shiraz', 'syrah', 'merlot', 'grenache',
        'tempranillo', 'nebbiolo', 'sangiovese', 'gamay', 'malbec',
        'barolo', 'brunello', 'bordeaux', 'rhône', 'rhone', 'côte', 'cote',
        'alternative red', 'italian red', 'penfold', 'henschke'
    ],
    'Sweet & Fortified': [
        'sweet', 'fortified', 'dessert', 'sauternes', 'tokaji',
        'port', 'sherry', 'muscat', 'topaque', 'madeira', 'tawny', 'icewine'
    ],
}

IGNORE_SECTIONS = [
    'whisky', 'whiskey', 'cognac', 'armagnac', 'calvados',
    'digestif', 'eau de vie', 'beer', 'cocktail',
    'half bottle', 'large format'
]


def maybe_select_wines(wine_text):
    if len(wine_text) <= LARGE_LIST_THRESHOLD:
        return wine_text

    logging.info(
        f"Large wine list ({len(wine_text):,} chars) — selecting "
        f"{MAX_TRAINING_WINES} representative wines for training."
    )
    selected = _select(wine_text)

    if len(selected) < 2_000:
        logging.warning(
            f"Smart selection returned only {len(selected)} chars — "
            f"falling back to truncation at {LARGE_LIST_THRESHOLD:,} chars."
        )
        cap = wine_text[:LARGE_LIST_THRESHOLD]
        last_nl = cap.rfind('\n')
        return cap[:last_nl] if last_nl > 0 else cap

    logging.info(f"Wine selection complete — {len(selected):,} chars.")
    return selected


def _select(wine_text):
    category_wines = {cat: [] for cat in MAIN_CATEGORIES}
    current_category = None
    skip = False

    for line in wine_text.split('\n'):
        s = line.strip()
        if not s:
            continue

        if _is_header(s):
            lower = s.lower()
            if any(ig in lower for ig in IGNORE_SECTIONS):
                skip = True
                current_category = None
                continue
            new_cat = _categorize(lower)
            if new_cat is not None:
                current_category = new_cat
                skip = False
            continue

        if skip or current_category is None:
            continue

        price = _price(s)
        if price and len(s) > 15:
            category_wines[current_category].append((s, price))

    active = [(cat, wines) for cat, wines in category_wines.items() if wines]
    if not active:
        logging.warning("Wine selector: no wines parsed — fallback will trigger.")
        return ""

    per_cat = MAX_TRAINING_WINES // len(active)
    remainder = MAX_TRAINING_WINES % len(active)

    parts = []
    for i, (cat, wines) in enumerate(active):
        take = per_cat + (1 if i < remainder else 0)
        chosen = sorted(wines, key=lambda x: x[1])[:take]
        parts.append(f'\n{cat}')
        parts.extend(text for text, _ in chosen)

    return '\n'.join(parts)


def _is_header(line):
    if re.search(r'\b\d{2,5}\s*$', line):
        return False
    if len(line) > 100 or len(line.strip()) < 3:
        return False
    if re.match(r'^(NV|MV|\d{4})\b', line.strip()):
        return False
    return True


def _categorize(lower):
    for cat, keywords in MAIN_CATEGORIES.items():
        if any(kw in lower for kw in keywords):
            return cat
    return None


def _price(line):
    m = re.search(r'\b(\d{2,5})\s*$', line)
    if m:
        p = int(m.group(1))
        if 10 <= p <= 50_000:
            return p
    return None
