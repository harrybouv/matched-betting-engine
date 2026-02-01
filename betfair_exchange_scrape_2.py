import csv
from selenium import webdriver
from selenium.webdriver.common.by import By
import time

# Launch browser
driver = webdriver.Chrome()
driver.get('https://www.betfair.com/exchange/plus/en/football-betting-1')

time.sleep(0.5)  # wait for JavaScript to load

# Find the odds and team names
odds_elements = driver.find_elements(By.CSS_SELECTOR, 'label.Zs3u5.AUP11.Qe-26')
name_elements = driver.find_elements(By.CSS_SELECTOR, 'li.name')

# Extract text
odds = [float(o.text.strip()) for o in odds_elements if o.text.strip()]
names = [n.text.strip() for n in name_elements if n.text.strip()]

driver.quit()

# Pair teams and odds (Betfair Exchange shows Back/Lay for Home, Draw, Away = 6 odds per match)
matches = []
pairs = min(len(names) // 2, len(odds) // 6)
for i in range(pairs):
    base = i * 6
    home = names[i * 2]
    away = names[i * 2 + 1]

    home_back = odds[base + 0]
    home_lay  = odds[base + 1]
    draw_back = odds[base + 2]
    draw_lay  = odds[base + 3]
    away_back = odds[base + 4]
    away_lay  = odds[base + 5]

    matches.append({
        'Home Team': home,
        'Away Team': away,
        'Home Back Odds': home_back,
        'Home Lay Odds': home_lay,
        'Draw Back Odds': draw_back,
        'Draw Lay Odds': draw_lay,
        'Away Back Odds': away_back,
        'Away Lay Odds': away_lay,
    })

# Print results nicely (aligned B/L for each outcome)
if matches:
    for m in matches:
        print(f"{m['Home Team']} vs {m['Away Team']}")
        print(f"  Home  B/L: {m['Home Back Odds']} / {m['Home Lay Odds']}")
        print(f"  Draw  B/L: {m['Draw Back Odds']} / {m['Draw Lay Odds']}")
        print(f"  Away  B/L: {m['Away Back Odds']} / {m['Away Lay Odds']}")
        print("-" * 40)
else:
    print("No matches found — nothing to print.")

# Save CSV safely (avoid index error if empty)
filename = 'CSV Files/betfair_exchange_scraper.csv'
fieldnames = [
    'Home Team', 'Away Team',
    'Home Back Odds', 'Home Lay Odds',
    'Draw Back Odds', 'Draw Lay Odds',
    'Away Back Odds', 'Away Lay Odds'
]

with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(matches)

print('Saved', len(matches), 'rows to', filename)
