"""
Tarifs ONEE - Calculs des périodes et coûts
"""
from datetime import datetime
from app.models.models import TariffPeriod, Season


# ============================================================
# TARIFS (DH/kWh TTC)
# ============================================================
TARIFFS = {
    TariffPeriod.HC:  0.6269 * 1.18,    # 0.7397 DH/kWh TTC
    TariffPeriod.HPL: 0.85602 * 1.18,   # 1.0101 DH/kWh TTC
    TariffPeriod.HP:  1.1997 * 1.18,    # 1.4157 DH/kWh TTC
}

SCHEDULES = {
    Season.WINTER: {
        TariffPeriod.HP:  (17, 22),
        TariffPeriod.HPL: (7, 17),
        TariffPeriod.HC:  (22, 7),
    },
    Season.SUMMER: {
        TariffPeriod.HP:  (18, 23),
        TariffPeriod.HPL: (7, 18),
        TariffPeriod.HC:  (23, 7),
    }
}


def get_season(dt: datetime = None) -> Season:
    if dt is None:
        dt = datetime.now()
    month = dt.month
    if 5 <= month <= 9:
        return Season.SUMMER
    return Season.WINTER


def get_tariff_period(dt: datetime = None) -> TariffPeriod:
    if dt is None:
        dt = datetime.now()

    season = get_season(dt)
    hour = dt.hour
    schedule = SCHEDULES[season]

    hp_start, hp_end = schedule[TariffPeriod.HP]
    if hp_start <= hour < hp_end:
        return TariffPeriod.HP

    hpl_start, hpl_end = schedule[TariffPeriod.HPL]
    if hpl_start <= hour < hpl_end:
        return TariffPeriod.HPL

    return TariffPeriod.HC


def get_tariff_rate(period: TariffPeriod) -> float:
    return TARIFFS[period]


def calculate_cost(kwh: float, period: TariffPeriod) -> float:
    return kwh * TARIFFS[period]


def correct_power(raw_kw: float, correction: float = 48.0) -> float:
    return max(0, raw_kw - correction)


def calculate_grid_flows(pv_kw: float, consumption_corrected_kw: float):
    if consumption_corrected_kw >= pv_kw:
        grid_import = consumption_corrected_kw - pv_kw
        grid_export = 0.0
        self_consumption = pv_kw
    else:
        grid_import = 0.0
        grid_export = pv_kw - consumption_corrected_kw
        self_consumption = consumption_corrected_kw

    return grid_import, grid_export, self_consumption
