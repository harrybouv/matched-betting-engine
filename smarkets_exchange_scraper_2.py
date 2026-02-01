# smarkets_exchange_scraper.py
import csv, os, time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = "https://smarkets.com/sport/football"
OUTFILE = "CSV Files/smarkets_exchange_scraper.csv"

def to_float(txt: str):
    """Safe float parse, returns None on failure/blank."""
    if not txt:
        return None
    txt = txt.strip()
    try:
        return float(txt)
    except ValueError:
        return None

# --- Launch browser & open page ---
driver = webdriver.Chrome()
driver.get(URL)

# Let the first screen populate
time.sleep(1.0)

# Ensure base containers are present (tolerant wait)
try:
    WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.teams"))
    )
except Exception:
    pass

# OPTIONAL: light scroll to load a bit more content (no pyautogui needed here)
for _ in range(5):
    driver.execute_script("window.scrollBy(0, 800);")
    time.sleep(0.3)

# Find all match "cards" by anchoring on the teams block,
# then walking up to the nearest container and scraping odds within that container.
team_blocks = driver.find_elements(By.CSS_SELECTOR, "div.teams")

matches = []

for teams in team_blocks:
    names_text = teams.text.strip()
    if not names_text:
        continue

    # Expect exactly two lines: Home, Away
    parts = [p.strip() for p in names_text.split("\n") if p.strip()]
    if len(parts) != 2:
        continue
    home, away = parts[0], parts[1]

    # The nearest card-like ancestor that contains the odds grid as well.
    # This is intentionally broad but local to this teams block.
    card = teams.find_element(
        By.XPATH,
        "./ancestor::*[div[contains(@class,'teams')]][1]"
    )

    # Within THIS card, collect the three outcome rows' BUY/LAY odds.
    # BUY = back, SELL = lay
    buy_spans  = card.find_elements(By.CSS_SELECTOR, "span.price.tick.buy.enabled.formatted-price.numeric-value")
    sell_spans = card.find_elements(By.CSS_SELECTOR, "span.price.tick.sell.enabled.formatted-price.numeric-value")

    # We expect three outcomes (Home, Draw, Away). If not, skip this card.
    if len(buy_spans) < 3 or len(sell_spans) < 3:
        continue

    # Parse the first three values only (Home, Draw, Away in listing order)
    home_back = to_float(buy_spans[0].text)
    draw_back = to_float(buy_spans[1].text)
    away_back = to_float(buy_spans[2].text)

    home_lay  = to_float(sell_spans[0].text)
    draw_lay  = to_float(sell_spans[1].text)
    away_lay  = to_float(sell_spans[2].text)

    # Require all six to exist; if any missing, skip to keep alignment perfect.
    vals = [home_back, draw_back, away_back, home_lay, draw_lay, away_lay]
    if any(v is None for v in vals):
        continue

    matches.append({
        "Home Team": home,
        "Away Team": away,
        "Home Back Odds": home_back,
        "Home Lay Odds": home_lay,
        "Draw Back Odds": draw_back,
        "Draw Lay Odds": draw_lay,
        "Away Back Odds": away_back,
        "Away Lay Odds": away_lay,
    })

driver.quit()

# Print preview
if matches:
    for m in matches[:12]:
        print(f"{m['Home Team']} vs {m['Away Team']}")
        print(f"  Home  B/L: {m['Home Back Odds']} / {m['Home Lay Odds']}")
        print(f"  Draw  B/L: {m['Draw Back Odds']} / {m['Draw Lay Odds']}")
        print(f"  Away  B/L: {m['Away Back Odds']} / {m['Away Lay Odds']}")
        print("-" * 40)
else:
    print("No matches found — nothing to print.")

# Save CSV
os.makedirs("CSV Files", exist_ok=True)
fieldnames = [
    "Home Team", "Away Team",
    "Home Back Odds", "Home Lay Odds",
    "Draw Back Odds", "Draw Lay Odds",
    "Away Back Odds", "Away Lay Odds",
]
with open(OUTFILE, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(matches)

print("Saved", len(matches), "rows to", OUTFILE)
