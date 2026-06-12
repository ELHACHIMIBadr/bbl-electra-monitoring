"""
Collector - Collecte périodique des données FusionSolar
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.services.fusionsolar import fusionsolar_service
from app.models.models import Plant, EnergyReading, HourlyAggregate
from app.utils.tariffs import (
    get_tariff_period, get_season, correct_power,
    calculate_grid_flows, get_tariff_rate
)
from app.config import settings
from app.database import SessionLocal
from app.services.rules_engine import evaluate_rules
import logging

# Maroc = UTC+1
MOROCCO_TZ = timezone(timedelta(hours=1))

def now_morocco():
    return datetime.now(MOROCCO_TZ).replace(tzinfo=None)

# Cache pour détecter les données figées
_last_pv_values = []  # Historique des dernières valeurs PV avec timestamps
_is_frozen = False    # True si données figées (centrale hors ligne)
_frozen_since = None  # Timestamp exact du début du figement

def _check_frozen_data(pv_power: float) -> bool:
    """Détecte si FusionSolar retourne des données figées (centrale hors ligne)"""
    global _last_pv_values, _is_frozen, _frozen_since
    now = now_morocco()
    hour = now.hour

    _last_pv_values.append((now, round(pv_power, 1)))
    if len(_last_pv_values) > 4:
        _last_pv_values.pop(0)

    # Vérifier seulement pendant les heures de jour (7h-19h)
    if 7 <= hour <= 19 and len(_last_pv_values) >= 3:
        last_3_vals = [v for _, v in _last_pv_values[-3:]]
        if len(set(last_3_vals)) == 1 and last_3_vals[-1] > 5:
            if not _is_frozen:
                # Premier déclenchement — on remonte au 1er sample figé
                _frozen_since = _last_pv_values[-3][0]  # timestamp du 1er des 3 identiques
                logger.warning(f"🔴 Figement détecté depuis {_frozen_since.strftime('%H:%M')}")
            _is_frozen = True
            return True

    # Si PV est nul en plein jour → hors ligne
    if 9 <= hour <= 16 and pv_power < 1:
        if not _is_frozen:
            _frozen_since = now
        _is_frozen = True
        return True

    # Données valides → réinitialiser
    if _is_frozen:
        logger.info(f"✅ Centrale de nouveau en ligne après figement depuis {_frozen_since}")
    _is_frozen = False
    _frozen_since = None
    return False

logger = logging.getLogger(__name__)


def collect_data():
    logger.info("⏰ Début de la collecte...")
    db = SessionLocal()

    try:
        if not fusionsolar_service.connect():
            logger.error("❌ Impossible de se connecter à FusionSolar")
            return

        plant = _get_or_create_target_plant(db)
        if not plant:
            logger.error("❌ Centrale cible introuvable")
            return

        reading = _collect_plant_data(db, plant)
        if reading:
            evaluate_rules(reading, db)

        db.commit()
        logger.info("✅ Collecte terminée")

    except Exception as e:
        logger.error(f"❌ Erreur collecte: {e}")
        db.rollback()
    finally:
        fusionsolar_service.disconnect()
        db.close()


def _get_or_create_target_plant(db: Session) -> Plant:
    plant = db.query(Plant).filter(
        Plant.fusionsolar_code == settings.TARGET_PLANT_ID
    ).first()

    if not plant:
        plant = Plant(
            name=settings.TARGET_PLANT_NAME,
            fusionsolar_code=settings.TARGET_PLANT_ID,
            capacity_kwp=settings.TARGET_PLANT_CAPACITY_KWP,
            is_active=True
        )
        db.add(plant)
        db.commit()
        db.refresh(plant)
        logger.info(f"✅ Centrale créée: {plant.name}")

    return plant


def _collect_plant_data(db: Session, plant: Plant) -> EnergyReading:
    data = fusionsolar_service.get_realtime_data(plant.fusionsolar_code)
    if not data:
        logger.warning(f"⚠️ Pas de données pour {plant.name}")
        return None

    now = now_morocco()
    tariff_period = get_tariff_period(now)
    season = get_season(now)

    consumption_corrected = correct_power(
        data["consumption_raw"],
        settings.POWER_CORRECTION_KW
    )

    grid_import, grid_export, self_consumption = calculate_grid_flows(
        data["pv_power"],
        consumption_corrected
    )

    # Détecter données figées — NE PAS stocker si hors ligne
    frozen = _check_frozen_data(data["pv_power"])
    if frozen:
        logger.warning(f"⚠️ Données figées — centrale hors ligne. Collecte ignorée (PV: {data['pv_power']} kW)")
        _purge_frozen_data(db, plant)  # Purger les données corrompues
        _send_offline_alert(db, plant)
        return None  # ← On ne sauvegarde rien

    reading = EnergyReading(
        plant_id=plant.id,
        timestamp=now,
        pv_power=data["pv_power"],
        consumption_raw=data["consumption_raw"],
        grid_import_raw=data.get("grid_import_raw", 0),
        consumption_corrected=consumption_corrected,
        grid_import=grid_import,
        grid_export=grid_export,
        self_consumption=self_consumption,
        tariff_period=tariff_period,
        season=season
    )
    db.add(reading)

    logger.info(
        f"📊 {plant.name} | PV: {data['pv_power']:.1f} kW | "
        f"Conso: {consumption_corrected:.1f} kW | "
        f"Import: {grid_import:.1f} kW | Export: {grid_export:.1f} kW | "
        f"Autoconso: {self_consumption:.1f} kW | {tariff_period.value}"
    )

    _update_hourly_aggregate(db, plant, reading)
    return reading


def _purge_frozen_data(db, plant):
    """
    Purge les EnergyReading et HourlyAggregate corrompus
    depuis le début du figement (_frozen_since).
    Exécuté seulement au premier cycle de détection.
    """
    global _frozen_since
    if not _frozen_since:
        return

    # Purger une seule fois par événement de figement
    # (on vérifie si des données existent encore depuis frozen_since)
    corrupted_readings = db.query(EnergyReading).filter(
        EnergyReading.plant_id == plant.id,
        EnergyReading.timestamp >= _frozen_since
    ).count()

    if corrupted_readings == 0:
        return  # Déjà purgé

    # Supprimer les readings figés
    deleted_r = db.query(EnergyReading).filter(
        EnergyReading.plant_id == plant.id,
        EnergyReading.timestamp >= _frozen_since
    ).delete()

    # Supprimer les agrégats horaires affectés
    frozen_hour = _frozen_since.replace(minute=0, second=0, microsecond=0)
    deleted_a = db.query(HourlyAggregate).filter(
        HourlyAggregate.plant_id == plant.id,
        HourlyAggregate.hour_start >= frozen_hour
    ).delete()

    # Recalculer l'agrégat de l'heure du début du figement
    # (cette heure peut avoir des données valides AVANT le figement)
    valid_readings = db.query(EnergyReading).filter(
        EnergyReading.plant_id == plant.id,
        EnergyReading.timestamp >= frozen_hour,
        EnergyReading.timestamp < _frozen_since
    ).all()

    if valid_readings:
        n = len(valid_readings)
        from app.utils.tariffs import get_tariff_rate
        agg = HourlyAggregate(
            plant_id=plant.id,
            hour_start=frozen_hour,
            avg_pv_power=sum(r.pv_power for r in valid_readings) / n,
            avg_consumption=sum(r.consumption_corrected for r in valid_readings) / n,
            avg_grid_import=sum(r.grid_import for r in valid_readings) / n,
            avg_grid_export=sum(r.grid_export for r in valid_readings) / n,
            avg_self_consumption=sum(r.self_consumption for r in valid_readings) / n,
            sample_count=n,
            tariff_period=valid_readings[0].tariff_period,
            season=valid_readings[0].season
        )
        agg.pv_energy_kwh = agg.avg_pv_power * (n / 12)  # Pondéré par le temps réel
        agg.consumption_kwh = agg.avg_consumption * (n / 12)
        agg.grid_import_kwh = agg.avg_grid_import * (n / 12)
        agg.grid_export_kwh = agg.avg_grid_export * (n / 12)
        agg.self_consumption_kwh = agg.avg_self_consumption * (n / 12)
        tariff = get_tariff_rate(agg.tariff_period, db)
        agg.estimated_cost_dh = agg.grid_import_kwh * tariff
        agg.savings_dh = agg.self_consumption_kwh * tariff
        db.add(agg)
        logger.info(f"✅ Agrégat {frozen_hour.strftime('%H:%M')} recalculé avec {n} samples valides")

    logger.warning(
        f"🗑️ Purge données figées: {deleted_r} readings + {deleted_a} agrégats "
        f"supprimés depuis {_frozen_since.strftime('%H:%M')}"
    )


def _send_offline_alert(db, plant):
    """Envoyer une alerte centrale hors ligne avec heure exacte"""
    from app.models.models import AlertRule, AlertLog, AlertStatus
    from app.services.notifications import send_alert
    from datetime import timedelta
    now = now_morocco()
    rule = db.query(AlertRule).filter(AlertRule.rule_code == 'PLANT_OFFLINE').first()
    if not rule or not rule.is_active:
        return
    cooldown_time = now - timedelta(minutes=rule.cooldown_minutes)
    recent = db.query(AlertLog).filter(
        AlertLog.rule_id == rule.id,
        AlertLog.triggered_at > cooldown_time
    ).first()
    if recent:
        return

    # Heure exacte du figement
    since_str = _frozen_since.strftime('%H:%M') if _frozen_since else now.strftime('%H:%M')
    msg = f"{since_str} — Centrale hors ligne · Vérifier smartLogger ou 4G"
    alert_log = AlertLog(
        rule_id=rule.id,
        plant_id=plant.id,
        triggered_at=now,
        measured_value=0,
        threshold_value=0,
        message=msg,
        status=AlertStatus.ACTIVE
    )
    db.add(alert_log)
    send_alert(msg, rule.notify_telegram, rule.notify_email)
    logger.warning(f"🚨 {msg}")


def _update_hourly_aggregate(db: Session, plant: Plant, reading: EnergyReading):
    hour_start = reading.timestamp.replace(minute=0, second=0, microsecond=0)

    aggregate = db.query(HourlyAggregate).filter(
        HourlyAggregate.plant_id == plant.id,
        HourlyAggregate.hour_start == hour_start
    ).first()

    if not aggregate:
        aggregate = HourlyAggregate(
            plant_id=plant.id,
            hour_start=hour_start,
            avg_pv_power=0, avg_consumption=0,
            avg_grid_import=0, avg_grid_export=0,
            avg_self_consumption=0,
            sample_count=0,
            tariff_period=reading.tariff_period,
            season=reading.season
        )
        db.add(aggregate)

    n = aggregate.sample_count
    aggregate.avg_pv_power = _update_avg(aggregate.avg_pv_power, reading.pv_power, n)
    aggregate.avg_consumption = _update_avg(aggregate.avg_consumption, reading.consumption_corrected, n)
    aggregate.avg_grid_import = _update_avg(aggregate.avg_grid_import, reading.grid_import, n)
    aggregate.avg_grid_export = _update_avg(aggregate.avg_grid_export, reading.grid_export, n)
    aggregate.avg_self_consumption = _update_avg(aggregate.avg_self_consumption, reading.self_consumption, n)
    aggregate.sample_count = n + 1

    # kWh = moyenne × fraction d'heure réelle (sample_count/12 car 12 samples = 1h complète)
    fraction = (n + 1) / 12
    aggregate.pv_energy_kwh = aggregate.avg_pv_power * fraction
    aggregate.consumption_kwh = aggregate.avg_consumption * fraction
    aggregate.grid_import_kwh = aggregate.avg_grid_import * fraction
    aggregate.grid_export_kwh = aggregate.avg_grid_export * fraction
    aggregate.self_consumption_kwh = aggregate.avg_self_consumption * fraction

    # Coût import — tarifs lus depuis la DB
    tariff = get_tariff_rate(aggregate.tariff_period, db)
    aggregate.estimated_cost_dh = aggregate.grid_import_kwh * tariff

    # Économies solaires = autoconsommation × tarif de la tranche
    aggregate.savings_dh = aggregate.self_consumption_kwh * tariff


def _update_avg(current_avg: float, new_value: float, count: int) -> float:
    if current_avg is None:
        current_avg = 0
    if count == 0:
        return new_value
    return (current_avg * count + new_value) / (count + 1)
