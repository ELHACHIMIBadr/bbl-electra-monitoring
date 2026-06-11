"""
Moteur de Règles - Évaluation des alertes
Règles définies avec BBL-ELECTRA pour la ferme
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.models import (
    EnergyReading, AlertRule, AlertLog, AlertSeverity, AlertStatus,
    HourlyAggregate
)
from app.services.notifications import send_alert
from app.utils.tariffs import get_season
from app.models.models import Season
import logging

logger = logging.getLogger(__name__)


# ============================================================
# DÉFINITION DES RÈGLES
# ============================================================
RULES = [
    {
        "code": "HP_INSTANT",
        "name": "Consommation élevée en Heures de Pointe",
        "description": "La consommation dépasse 150 kW pendant les heures de pointe",
        "severity": AlertSeverity.CRITICAL,
        "cooldown_minutes": 30,
    },
    {
        "code": "NIGHT_WATERING",
        "name": "Consommation nocturne élevée (arrosage)",
        "description": "La consommation dépasse 180 kW entre 00h et 04h",
        "severity": AlertSeverity.WARNING,
        "cooldown_minutes": 30,
    },
    {
        "code": "NIGHT_CALM",
        "name": "Consommation nocturne anormale (période calme)",
        "description": "La consommation dépasse 150 kW entre 04h et 07h",
        "severity": AlertSeverity.CRITICAL,
        "cooldown_minutes": 15,
    },
    {
        "code": "GRID_IMPORT_PEAK_SUN",
        "name": "Import réseau excessif (plein soleil)",
        "description": "L'import réseau dépasse 50 kW entre 10h et 16h",
        "severity": AlertSeverity.WARNING,
        "cooldown_minutes": 30,
    },
    {
        "code": "GRID_IMPORT_LATE_SUN",
        "name": "Import réseau excessif (fin de journée)",
        "description": "L'import réseau dépasse 80 kW entre 16h et 18h",
        "severity": AlertSeverity.WARNING,
        "cooldown_minutes": 30,
    },
    {
        "code": "EXPORT_EXCESSIVE",
        "name": "Export réseau excessif",
        "description": "L'énergie exportée au réseau dépasse 50 kWh cumulés sur la journée",
        "severity": AlertSeverity.WARNING,
        "cooldown_minutes": 120,
    },
]


def evaluate_rules(reading: EnergyReading, db: Session):
    """
    Évaluer toutes les règles pour un relevé donné
    """
    now = reading.timestamp
    hour = now.hour
    season = get_season(now)

    hp_start = 18 if season == Season.SUMMER else 17
    hp_end = 23 if season == Season.SUMMER else 22

    alerts_triggered = []

    # --- R1: HP > 150 kW ---
    if hp_start <= hour < hp_end:
        if reading.consumption_corrected > 150:
            alert = _trigger_alert(
                db, reading, "HP_INSTANT",
                reading.consumption_corrected, 150,
                f"🔴 ALERTE HP | Conso: {reading.consumption_corrected:.0f} kW "
                f"(seuil: 150 kW) | {now.strftime('%H:%M')}"
            )
            if alert:
                alerts_triggered.append(alert)

    # --- R2: Nuit arrosage (00h-04h) > 180 kW ---
    if 0 <= hour < 4:
        if reading.consumption_corrected > 180:
            alert = _trigger_alert(
                db, reading, "NIGHT_WATERING",
                reading.consumption_corrected, 180,
                f"🟠 ALERTE NUIT | Conso: {reading.consumption_corrected:.0f} kW "
                f"(seuil: 180 kW) | Arrosage actif {now.strftime('%H:%M')}"
            )
            if alert:
                alerts_triggered.append(alert)

    # --- R3: Nuit calme (04h-07h) > 150 kW ---
    if 4 <= hour < 7:
        if reading.consumption_corrected > 150:
            alert = _trigger_alert(
                db, reading, "NIGHT_CALM",
                reading.consumption_corrected, 150,
                f"🔴 ALERTE NUIT | Conso: {reading.consumption_corrected:.0f} kW "
                f"(seuil: 150 kW) | Période calme {now.strftime('%H:%M')} "
                f"— Vérifier si une pompe tourne!"
            )
            if alert:
                alerts_triggered.append(alert)

    # --- R4: Import réseau plein soleil (10h-16h) > 50 kW ---
    if 10 <= hour < 16:
        if reading.grid_import > 50:
            alert = _trigger_alert(
                db, reading, "GRID_IMPORT_PEAK_SUN",
                reading.grid_import, 50,
                f"🟠 IMPORT RÉSEAU | {reading.grid_import:.0f} kW importés "
                f"(seuil: 50 kW) | PV: {reading.pv_power:.0f} kW | "
                f"Conso: {reading.consumption_corrected:.0f} kW | {now.strftime('%H:%M')}"
            )
            if alert:
                alerts_triggered.append(alert)

    # --- R5: Import réseau fin journée (16h-18h) > 80 kW ---
    if 16 <= hour < hp_start:
        if reading.grid_import > 80:
            alert = _trigger_alert(
                db, reading, "GRID_IMPORT_LATE_SUN",
                reading.grid_import, 80,
                f"🟠 IMPORT RÉSEAU | {reading.grid_import:.0f} kW importés "
                f"(seuil: 80 kW) | PV: {reading.pv_power:.0f} kW | "
                f"Conso: {reading.consumption_corrected:.0f} kW | {now.strftime('%H:%M')}"
            )
            if alert:
                alerts_triggered.append(alert)

    # --- R6: Export cumulé > 50 kWh (pas de restriction horaire) ---
    cumul_export = _get_daily_cumul_export(db, reading.plant_id, now)
    if cumul_export > 50:
        alert = _trigger_alert(
            db, reading, "EXPORT_EXCESSIVE",
            cumul_export, 50,
            f"🟠 EXPORT RÉSEAU | {cumul_export:.0f} kWh exportés aujourd'hui "
            f"(seuil: 50 kWh) | Export instantané: {reading.grid_export:.0f} kW | "
            f"PV: {reading.pv_power:.0f} kW | Conso: {reading.consumption_corrected:.0f} kW | "
            f"{now.strftime('%H:%M')}"
        )
        if alert:
            alerts_triggered.append(alert)

    if alerts_triggered:
        logger.warning(f"⚠️ {len(alerts_triggered)} alerte(s) déclenchée(s)")

    return alerts_triggered


def _get_daily_cumul_export(db: Session, plant_id: int, now: datetime) -> float:
    """
    Calculer l'export cumulé du jour en kWh
    Somme des grid_export_kwh de chaque HourlyAggregate du jour
    """
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    result = db.query(
        func.coalesce(func.sum(HourlyAggregate.grid_export_kwh), 0)
    ).filter(
        HourlyAggregate.plant_id == plant_id,
        HourlyAggregate.hour_start >= today_start
    ).scalar()

    return float(result)


def _trigger_alert(
    db: Session,
    reading: EnergyReading,
    rule_code: str,
    measured: float,
    threshold: float,
    message: str
) -> AlertLog | None:
    """
    Déclencher une alerte si le cooldown est respecté
    """
    rule = db.query(AlertRule).filter(AlertRule.rule_code == rule_code).first()
    if not rule or not rule.is_active:
        return None

    cooldown_time = reading.timestamp - timedelta(minutes=rule.cooldown_minutes)

    recent_alert = db.query(AlertLog).filter(
        AlertLog.rule_id == rule.id,
        AlertLog.plant_id == reading.plant_id,
        AlertLog.triggered_at > cooldown_time
    ).first()

    if recent_alert:
        return None

    alert_log = AlertLog(
        rule_id=rule.id,
        plant_id=reading.plant_id,
        triggered_at=reading.timestamp,
        measured_value=measured,
        threshold_value=threshold,
        message=message,
        status=AlertStatus.ACTIVE
    )
    db.add(alert_log)

    send_alert(message, rule.notify_telegram, rule.notify_email)

    logger.warning(f"🚨 {message}")
    return alert_log


def init_rules(db: Session):
    """Initialiser les règles dans la base de données"""
    for rule_def in RULES:
        existing = db.query(AlertRule).filter(
            AlertRule.rule_code == rule_def["code"]
        ).first()

        if not existing:
            rule = AlertRule(
                name=rule_def["name"],
                description=rule_def["description"],
                rule_code=rule_def["code"],
                metric="grid_export",
                operator=">",
                threshold=0,
                severity=rule_def["severity"],
                cooldown_minutes=rule_def["cooldown_minutes"],
                is_active=True
            )
            db.add(rule)
            logger.info(f"   ✅ Règle créée: {rule_def['name']}")

    db.commit()
    logger.info("✅ Règles d'alertes initialisées")
