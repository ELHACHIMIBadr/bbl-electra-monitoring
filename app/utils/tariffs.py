"""
Tarifs ONEE - Calculs des périodes et coûts
Les tarifs sont lus depuis la base de données (SystemSetting)
pour être cohérents avec les paramètres modifiables via l'UI.
"""
from datetime import datetime
from app.models.models import TariffPeriod, Season
import logging

logger = logging.getLogger(__name__)

# Tarifs par défaut (fallback si DB indisponible)
TARIFFS_DEFAULT = {
    TariffPeriod.HC:  0.62695 * 1.18,   # 0.7398 DH/kWh TTC
    TariffPeriod.HPL: 0.85602 * 1.18,   # 1.0101 DH/kWh TTC
    TariffPeriod.HP:  1.19975 * 1.18,   # 1.4157 DH/kWh TTC
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


def get_tariffs_from_db(db=None) -> dict:
    """
    Lire les tarifs depuis la base de données SystemSetting.
    Retourne les tarifs TTC (HT × TVA).
    Fallback sur les valeurs hardcodées si DB indisponible.
    """
    if db is None:
        return TARIFFS_DEFAULT

    try:
        from app.models.models import SystemSetting
        settings_map = {
            s.key: float(s.value)
            for s in db.query(SystemSetting).filter(
                SystemSetting.key.in_([
                    'tarif_hp_ht', 'tarif_hpl_ht', 'tarif_hc_ht', 'tva_energie'
                ])
            ).all()
        }

        hp_ht  = settings_map.get('tarif_hp_ht',  1.19975)
        hpl_ht = settings_map.get('tarif_hpl_ht', 0.85602)
        hc_ht  = settings_map.get('tarif_hc_ht',  0.62695)
        tva    = settings_map.get('tva_energie',   0.18)

        return {
            TariffPeriod.HC:  hc_ht  * (1 + tva),
            TariffPeriod.HPL: hpl_ht * (1 + tva),
            TariffPeriod.HP:  hp_ht  * (1 + tva),
        }
    except Exception as e:
        logger.warning(f"⚠️ Impossible de lire les tarifs DB, fallback hardcodé: {e}")
        return TARIFFS_DEFAULT


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


def get_tariff_rate(period: TariffPeriod, db=None) -> float:
    """Retourne le tarif TTC pour une période donnée."""
    tariffs = get_tariffs_from_db(db)
    return tariffs[period]


def calculate_cost(kwh: float, period: TariffPeriod, db=None) -> float:
    return kwh * get_tariff_rate(period, db)


def correct_power(raw_kw: float, correction: float = 48.0) -> float:
    """Applique la correction -48 kW sur la consommation brute."""
    return max(0, raw_kw - correction)


def calculate_grid_flows(pv_kw: float, consumption_corrected_kw: float):
    """
    Calcule les flux réseau depuis les valeurs corrigées.
    Import = consommation corrigée - PV (si conso > PV)
    Export = PV - consommation corrigée (si PV > conso)
    """
    if consumption_corrected_kw >= pv_kw:
        grid_import = consumption_corrected_kw - pv_kw
        grid_export = 0.0
        self_consumption = pv_kw
    else:
        grid_import = 0.0
        grid_export = pv_kw - consumption_corrected_kw
        self_consumption = consumption_corrected_kw

    return grid_import, grid_export, self_consumption
