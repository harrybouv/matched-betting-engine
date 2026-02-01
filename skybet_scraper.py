import csv
from selenium import webdriver
from selenium.webdriver.common.by import By
import time
import pyautogui

# --- helper: robust fractional/decimal → decimal float ---
def to_decimal(odds_text: str):
    """
    Convert SkyBet odds text to decimal.
    Handles:
      - fractional like '13/8', '17/20'
      - Unicode fraction slash '⁄'
      - 'EVS' (evens) -> 2.0
      - already-decimal like '2.75'
    Returns float or None if unparsable.
    """
    t = odds_text.strip().upper().replace(" ", "")
    if not t:
        return None

    # evens
    if t in {"EVS", "EVEN", "EVENS"}:
        return 2.0

    # sometimes unicode fraction slash appears
    t = t.replace("⁄", "/")

    # plain decimal
    try:
        if "/" not in t:
            return float(t)
    except ValueError:
        pass

    # fractional a/b
    if "/" in t:
        try:
            a, b = t.split("/", 1)
            num = float(a)
            den = float(b)
            if den == 0:
                return None
            return 1.0 + (num / den)
        except Exception:
            return None

    return None


# Launch browser
driver = webdriver.Chrome()
driver.get('https://skybet.com/football/s-1')

time.sleep(2)

# accept cookies
accept_btn = driver.find_element(By.ID, "onetrust-accept-btn-handler")
accept_btn.click()
time.sleep(0.5)

# *** keep your exact mouse-move + wheel scrolling ***
pyautogui.moveTo(742, 381)
for i in range(35):
    pyautogui.scroll(-100)  # negative = scroll down
    time.sleep(0.05)

time.sleep(5)

# Re-grab after scrolling
odds_elements = driver.find_elements(
    By.XPATH, "//button//span[contains(normalize-space(text()), '/')]"
)
name_elements = driver.find_elements(
    By.XPATH, "//p[contains(@class,'teamNameLabel')]"
)

# Extract text → decimals (conversion only changed / hardened)
odds = []
for o in odds_elements:
    dec = to_decimal(o.text)
    if dec is not None:
        odds.append(dec)

names = [n.text.strip() for n in name_elements if n.text.strip()]

driver.quit()

# (optional while testing)
print("counts → names:", len(names), "odds:", len(odds))

matches = []
pairs = min(len(names) // 2, len(odds) // 3)

# hard-cap names so they can't outrun odds
names = names[: pairs * 2]

for i in range(pairs):
    base = i * 3
    home = names[i * 2]
    away = names[i * 2 + 1]

    home_back = odds[base + 0]
    draw_back = odds[base + 1]
    away_back = odds[base + 2]

    matches.append({
        'Home Team': home,
        'Away Team': away,
        'Home Back Odds': home_back,
        'Draw Back Odds': draw_back,
        'Away Back Odds': away_back,
    })

# de-dup by (home, away)
seen = set()
unique_matches = []
for m in matches:
    key = (m['Home Team'].lower(), m['Away Team'].lower())
    if key not in seen:
        seen.add(key)
        unique_matches.append(m)
matches = unique_matches

# Print results nicely
if matches:
    for m in matches:
        print(f"{m['Home Team']} vs {m['Away Team']}")
        print(f"  Home: {m['Home Back Odds']}")
        print(f"  Draw: {m['Draw Back Odds']}")
        print(f"  Away: {m['Away Back Odds']}")
        print("-" * 40)
else:
    print("No matches found — nothing to print.")

# Save CSV
filename = 'CSV Files/skybet_scraper.csv'
fieldnames = [
    'Home Team', 'Away Team',
    'Home Back Odds',
    'Draw Back Odds',
    'Away Back Odds',
]

with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(matches)

print('Saved', len(matches), 'rows to', filename)
print("counts → names:", len(names), "odds:", len(odds))
