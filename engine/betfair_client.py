# betfair_client.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple
import os

USE_REAL_BETFAIR = False  # <

@dataclass
class LayQuote:
    lay_price: float
    lay_size: float  # money available at that lay price


def get_best_lay(market_id: str, selection_id: int) -> LayQuote:
    """
    Returns best lay price + size for a runner.
    - Stub returns a plausible price so the UI works now.
    - Replace with Betfair API call when you're ready.
    """
    if not USE_REAL_BETFAIR:
        # Simple stub: you can edit this to match what you usually see
        return LayQuote(lay_price=2.56, lay_size=250.0)


    import betfairlightweight  # type: ignore

    username = os.environ["BETFAIR_USERNAME"]
    password = os.environ["BETFAIR_PASSWORD"]
    app_key = os.environ["BETFAIR_APP_KEY"]
    certs = os.environ["BETFAIR_CERTS_DIR"]

    trading = betfairlightweight.APIClient(username, password, app_key=app_key, certs=certs)
    trading.login()

    market_books = trading.betting.list_market_book(
        market_ids=[market_id],
        price_projection=betfairlightweight.filters.price_projection(price_data=["EX_BEST_OFFERS"])
    )
    if not market_books:
        raise ValueError("Market not found / no market book returned.")

    book = market_books[0]
    runner = next((r for r in book.runners if int(r.selection_id) == int(selection_id)), None)
    if runner is None:
        raise ValueError("selectionId not found in market.")

    atl = runner.ex.available_to_lay
    if not atl:
        raise ValueError("No lay offers available for this runner.")

    best = atl[0]
    return LayQuote(lay_price=float(best.price), lay_size=float(best.size))