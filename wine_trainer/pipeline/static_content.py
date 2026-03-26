"""
static_content.py – Pre-written generic sections for the Wine Mastery Training Guide.

These sections are universal — identical quality for every restaurant, every run,
zero tokens spent. Injected by claude_analyzer.py into Section 2.
"""

# ─────────────────────────────────────────────────────────────────────────────
HOW_WINE_IS_MADE = """
### How Wine Is Made — and Why It Matters

Wine begins in the vineyard, not the winery. Grapes absorb the character of their soil, climate, and the decisions of the grower all season long. At harvest, those grapes are crushed and their juice is exposed to yeast — naturally present on grape skins or added by the winemaker — which converts sugar into alcohol and carbon dioxide. That single transformation, fermentation, is the heart of winemaking. Everything else is craft and intention.

**White wine** is made from juice separated from the grape skins almost immediately after crushing. This is why white wine is clear even when made from red-skinned grapes: the colour and tannins live in the skin. Whites ferment cool and fast, preserving freshness and fruit.

**Red wine** ferments with the skins still in contact with the juice — sometimes for days, sometimes weeks. The skins leach colour, tannin, and texture into the wine. This is why reds feel different in the mouth: richer, drier, more structured.

**Rosé** sits in between. The winemaker allows brief skin contact — hours, not days — to extract just enough colour and a whisper of tannin before separating the juice. Most rosé is made this way rather than by blending red and white.

**Sparkling wine** undergoes a second fermentation, either in the bottle (Champagne method, which creates fine, persistent bubbles) or in a pressurised tank (Prosecco method, which creates softer, larger bubbles). The trapped CO₂ from that second fermentation becomes the fizz.

**Dessert and fortified wines** are made by either stopping fermentation early (leaving residual sugar) or adding grape spirit mid-fermentation to kill the yeast, preserving both sweetness and boosting alcohol. Port and Madeira are made this way.

Understanding *how* a wine is made helps you answer guests' questions with confidence and choose the right bottle for the right moment.

---

**3 Stories to Share with Guests**

> *"Did you know that Champagne gets its bubbles from a second fermentation inside the bottle? The yeast works for months in the dark, and then the dead yeast cells are frozen in the bottle neck and shot out under pressure — a process called disgorgement. Every glass you drink has been on quite a journey."*

> *"The colour of rosé tells you almost nothing about sweetness. A dark salmon rosé from Provence is often bone dry, while a pale blush from California can be quite sweet. The only way to know is to taste — which is exactly what I'd recommend."*

> *"Tannin is the reason a young Barolo can feel almost uncomfortable to drink. It's the same compound in black tea that makes your mouth feel dry. But with age, tannins soften and integrate — the wine opens up like a person who just needed a little time."*
"""

# ─────────────────────────────────────────────────────────────────────────────
WINE_VOCABULARY = """
### 50 Wine Vocabulary Words

- **Acidity** — The refreshing tartness in wine that makes your mouth water; essential for balance and food pairing.
- **Appellation** — A legally defined wine-growing region whose name appears on the label (e.g. Bordeaux, Napa Valley).
- **Aromas** — The smells detected in a wine by nosing the glass before tasting.
- **Astringency** — The drying, gripping sensation on the gums caused by tannins reacting with saliva.
- **Barrel fermented** — Wine fermented inside oak barrels rather than stainless steel tanks, adding texture and vanilla notes.
- **Biodynamic** — A farming philosophy treating the vineyard as a self-sustaining ecosystem, following lunar and cosmic cycles.
- **Blanc de Blancs** — Champagne or sparkling wine made exclusively from white grapes (usually Chardonnay).
- **Blanc de Noirs** — Sparkling wine made from red-skinned grapes (Pinot Noir or Pinot Meunier) with minimal skin contact.
- **Body** — The weight and fullness of wine in the mouth; described as light, medium, or full.
- **Bouquet** — The complex aromas that develop with age in a wine, distinct from primary fruit aromas.
- **Brix** — A measurement of sugar content in grapes at harvest; higher Brix generally means riper, more alcoholic wine.
- **Brut** — A dry sparkling wine style with very little residual sugar (typically under 12g/L).
- **Cava** — Spanish sparkling wine made using the traditional Champagne method, primarily in Catalonia.
- **Cépage** — French term for grape variety (e.g. "quel cépage?" means "which grape variety?").
- **Chaptalization** — The addition of sugar before fermentation to boost alcohol in cool vintages (legal in some regions).
- **Claret** — Traditional British term for red Bordeaux wine.
- **Climat** — A specific, named vineyard plot in Burgundy with its own microclimate and soil characteristics.
- **Clone** — A genetically identical cutting from a single vine, selected for specific traits like yield or flavour.
- **Cru** — French for "growth"; refers to a classified vineyard or estate of recognised quality.
- **Cuvée** — A specific blend or batch of wine; signals a curated selection when seen on a label.
- **Demi-sec** — A medium-dry to medium-sweet sparkling wine style.
- **Disgorgement** — The process of removing yeast sediment from a bottle of traditional-method sparkling wine.
- **Dosage** — A mixture of wine and sugar added after disgorgement to set a sparkling wine's final sweetness level.
- **Dry** — A wine with little or no perceptible sweetness; residual sugar typically below 4g/L.
- **Finish** — The flavours and sensations that linger after swallowing; a long finish indicates quality.
- **Flinty** — A mineral aroma reminiscent of struck steel or wet stone, often used to describe Chablis or Sancerre.
- **Fortified** — Wine with grape spirit added, raising alcohol to 15–22% ABV; e.g. Port, Sherry, Madeira.
- **Grower Champagne** — Champagne produced and bottled by the same grower who farmed the grapes; often terroir-driven.
- **Jeroboam** — A large-format bottle holding 3 litres (equivalent to 4 standard bottles).
- **Late Harvest** — Grapes left on the vine beyond normal harvest to concentrate sugars; used for sweet wines.
- **Lees** — Dead yeast cells left after fermentation; ageing on lees adds richness and complexity.
- **Maceration** — Soaking grape skins in juice or wine to extract colour, tannin, and flavour.
- **Malolactic fermentation** — A secondary process converting sharp malic acid into softer lactic acid, adding creaminess.
- **Minerality** — A tasting term for earthy, stony, or saline sensations; linked to soil composition.
- **Négociant** — A wine merchant who buys grapes or wine from growers, then blends and bottles under their own label.
- **Non-vintage (NV)** — Wine blended from multiple years; used in Champagne and fortified wines for consistency.
- **Oak** — Barrels used to age wine; imparts vanilla, toast, spice, and coconut while softening texture.
- **Off-dry** — A wine with a hint of sweetness, just perceptible but not overtly sweet.
- **Old vine / Vieilles vignes** — Grapes from vines typically over 25–30 years old; often more concentrated and complex.
- **Oxidation** — Exposure to oxygen; intentional in some wines (Sherry, Madeira) but a fault in fresh whites.
- **Pét-nat** — Short for Pétillant Naturel; a lightly sparkling wine bottled before fermentation is complete.
- **Phylloxera** — A root-destroying aphid that devastated European vineyards in the 19th century.
- **Residual sugar (RS)** — The natural grape sugar remaining after fermentation; measured in grams per litre.
- **Sommelier** — A trained wine professional responsible for selecting, storing, and serving wine in a restaurant.
- **Tannin** — Naturally occurring polyphenols from grape skins, seeds, and stems; create a drying, grippy sensation.
- **Terroir** — The complete natural environment of a vineyard: soil, climate, topography, and human tradition.
- **Varietal** — A wine named after and made primarily from a single grape variety (e.g. a "Chardonnay").
- **Vendange** — French for "harvest"; the annual grape-picking season, typically August–October in the Northern Hemisphere.
- **Vintage** — The year the grapes were harvested; indicates a wine's age and that season's growing conditions.
- **Yield** — The amount of fruit produced per hectare; lower yields generally mean more concentrated, complex wine.
"""

# ─────────────────────────────────────────────────────────────────────────────
WINE_PAIRING_PRINCIPLES = """
### Wine Pairing — Core Principles

Great wine pairing comes down to a handful of rules that work every time. Once your team understands these, they can confidently pair any wine to any dish.

**Match weight with weight.** Light food calls for light wine; rich food calls for fuller wine. A delicate steamed fish needs a crisp Chablis, not an oaky Chardonnay that will overwhelm it. A butter-braised lobster can handle that Chardonnay beautifully. Neither the food nor the wine should dominate.

**Acidity cuts richness.** A high-acid wine (Champagne, Sauvignon Blanc, Riesling) acts like a squeeze of lemon on a plate — it refreshes the palate and makes rich, creamy, or fatty food feel lighter. This is why Champagne with fish and chips works so well.

**Tannin and fat are friends; tannin and fish are not.** The tannins in a Cabernet Sauvignon bind to proteins in fat — in a well-marbled steak, this is magical. With fish or shellfish, those same tannins can react and create an unpleasant metallic taste. Stick to whites, rosés, or low-tannin reds with seafood.

**Sweet wine with sweet food — but the wine must be sweeter.** If you serve a dry red with a dessert, the wine tastes thin and sour by contrast. A Sauternes with crème brûlée works because the wine is at least as sweet as the food.

**Salt enhances sweetness.** Salty food (blue cheese, charcuterie, oysters) makes sweet wine taste less sweet and more balanced. This is the magic behind Sauternes and Roquefort — one of gastronomy's great classic pairings.

**Regional pairings almost always work.** Food and wine that evolved together over centuries tend to pair naturally. When in doubt, think regionally.

---

**Pairing with Asian and Spiced Food**

Aromatic, spiced, and Asian cuisines are among the most rewarding to pair with wine. The key is to embrace contrast rather than fight it.

*Off-dry or aromatic whites are your best friends.* A Gewurztraminer, an off-dry Riesling, or a Pinot Gris from Alsace have enough sweetness and perfume to stand alongside chilli heat, lemongrass, ginger, and soy without being overwhelmed. The slight sweetness counterpoints heat — the same reason people drink mango lassi with curry.

*Avoid high tannins and high alcohol.* Both amplify the perception of heat in spiced dishes. Choose lighter reds (Pinot Noir, Gamay), chilled reds, or whites and rosés.

*Sparkling wine is underrated here.* The bubbles and acidity in Champagne, Crémant, or Prosecco act as a palate cleanser between bites of complex, layered dishes. It is one of the most versatile styles across pan-Asian menus.

*Umami-rich dishes love umami-rich wines.* Aged wines with savoury, earthy qualities — a mature red Burgundy, an aged white Rioja — complement soy-braised meats, miso, and fermented flavours beautifully.
"""
