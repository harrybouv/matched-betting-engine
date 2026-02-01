
def calc_free(BO, BS, LO, E):
    LS = (BS * (BO - 1)) / (LO - (E / 100))  # Lay Stake
    LL = LS * (LO - 1)  # Lay Liability
    BP = BO * BS - BS - LL  # Back Profit
    LP = LS * (1 - (E / 100))  # Lay Profit
    GP = min(BP, LP)  # Guaranteed Profit

    R = GP / BS  # Rate of Extraction

    return {
        "lay_stake": LS,
        "liability": LL,
        "back_profit": BP,
        "lay_profit": LP,
        "guaranteed_profit": GP,
        "extraction_rate": R,
    }

def calc_cash(BO, BS, LO, E):
    LS = (BS * (BO )) / (LO - (E / 100))  # Lay Stake
    LL =LS * (LO - 1)  # Lay Liability
    BP = (BO - 1) * BS - LL  # Back Profit
    LP = (-BS) + LS * (1 - E/100)  # Lay Profit
    GP = min(BP, LP)  # Guaranteed Profit

    R = GP / BS  # Rate of Extraction

    return {
        "lay_stake": LS,
        "liability": LL,
        "back_profit": BP,
        "lay_profit": LP,
        "guaranteed_profit": GP,
        "extraction_rate": R,
    }

