## matched-betting-engine
Python tools used for modelling matched betting and free bet optimisation from an expected-value and risk perspective
This project focuses on EV, varience and capital discipline rather than ad-hoc caluclators or manual spreadsheets


## Overview

The code attatched contains small, modular scripts used to:
- compute matched bet and free bet returns
- analyse bookmaker vs exchange odds
- rank opportunities by expected value
The emphasis was on reliability and accuracy rather than large scale automation

## Context

The project was built to exploit betting sites' free bonuses an simoultaneaously develop knowledge about:
- expected value vs varience
- risk control
- decision making under uncertainty
- Python libraries including; numpy, pandas, requests, beautifulsoup

## Key Components

- 'match_calc.py'; core matched betting calculations (liability, stake sizing, net profit)
- 'free_bet_optimiser.py'; optimisation logic for free bets under different odds and exchange assumptions
- 'skybet_scraper.py', 'betfair_exchange_scrape_2.py', 'smarkets_exchange_scraper_2.py'; Small data collection scripts, designed to scrape individual sites

## Current Limitations

- All scripts must be used individually in order to work properly, should use combined interface
- No live betting or automation
- Market dynamics and execution effects are both simplified
  

## Potential Extensions

Future work would focus on stress-testing and validation rather than feature expansion
- Monte Carlo simulations to assess return distributions and drawdowns
- Adding additional bookmakers to utilise more offers
- Refactorign scripts into a unified interface to improve tool utilisation and repeatability
