"""
API Routes - Endpoints FastAPI
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.models.models import (
    Plant, EnergyReading, HourlyAggregate,
    AlertLog, AlertRule, Invoice, DailySummary,
    TariffPeriod, SystemSetting, PushSubscription
)
from app.utils.tariffs import get_tariff_rate

router = APIRouter()


# ============================================================
# CENTRALES
# ============================================================
@router.get("/plants")
def get_plants(db: Session = Depends(get_db)):
    plants = db.query(Plant).filter(Plant.is_active == True).all()
    return [
        {"id": p.id, "name": p.name, "code": p.fusionsolar_code, "capacity_kwp": p.capacity_kwp}
        for p in plants
    ]


# ============================================================
# TEMPS RÉEL
# ============================================================
@router.get("/realtime/{plant_id}")
def get_realtime(plant_id: int, db: Session = Depends(get_db)):
    reading = db.query(EnergyReading).filter(
        EnergyReading.plant_id == plant_id
    ).order_by(EnergyReading.timestamp.desc()).first()

    if not reading:
        return {"error": "Aucune donnée disponible"}

    from datetime import timezone, timedelta
    from app.services.collector import _is_frozen
    MOROCCO_TZ = timezone(timedelta(hours=1))
    now_morocco = datetime.now(MOROCCO_TZ).replace(tzinfo=None)
    age_minutes = (now_morocco - reading.timestamp).total_seconds() / 60
    is_offline = age_minutes > 15 or _is_frozen

    return {
        "timestamp": reading.timestamp.isoformat(),
        "pv_power": reading.pv_power,
        "consumption_corrected": reading.consumption_corrected,
        "consumption_raw": reading.consumption_raw,
        "grid_import": reading.grid_import,
        "grid_export": reading.grid_export,
        "self_consumption": reading.self_consumption,
        "tariff_period": reading.tariff_period.value if reading.tariff_period else None,
        "is_offline": is_offline,
        "data_age_minutes": round(age_minutes, 1),
    }


# ============================================================
# HISTORIQUE
# ============================================================
@router.get("/history/{plant_id}")
def get_history(plant_id: int, hours: int = Query(default=24, le=168), date: str = Query(default=None), db: Session = Depends(get_db)):
    from datetime import timezone, timedelta
    MOROCCO_TZ = timezone(timedelta(hours=1))
    now_morocco = datetime.now(MOROCCO_TZ).replace(tzinfo=None)

    if date:
        # Jour spécifique : 00:00 → 23:59
        target = datetime.strptime(date, "%Y-%m-%d")
        since = target.replace(hour=0, minute=0, second=0)
        until = target.replace(hour=23, minute=59, second=59)
    else:
        # Aujourd'hui : depuis 00:00 heure Maroc
        since = now_morocco.replace(hour=0, minute=0, second=0, microsecond=0)
        until = now_morocco

    readings = db.query(EnergyReading).filter(
        EnergyReading.plant_id == plant_id,
        EnergyReading.timestamp >= since,
        EnergyReading.timestamp <= until
    ).order_by(EnergyReading.timestamp.asc()).all()

    return [
        {
            "timestamp": r.timestamp.isoformat(),
            "pv_power": r.pv_power,
            "consumption": r.consumption_corrected,
            "grid_import": r.grid_import,
            "grid_export": r.grid_export,
            "tariff_period": r.tariff_period.value if r.tariff_period else None,
        }
        for r in readings
    ]


# ============================================================
# BILAN JOURNALIER
# ============================================================
@router.get("/daily-summary/{plant_id}")
def get_daily_summary(plant_id: int, date: str = Query(default=None), db: Session = Depends(get_db)):
    from datetime import timezone, timedelta
    MOROCCO_TZ = timezone(timedelta(hours=1))
    now_morocco = datetime.now(MOROCCO_TZ).replace(tzinfo=None)

    if date:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    else:
        target_date = now_morocco.date()

    # Bornes 00:00 → 23:59:59 heure Maroc
    day_start = datetime.combine(target_date, datetime.min.time())
    day_end = datetime.combine(target_date, datetime.max.time())

    aggregates = db.query(HourlyAggregate).filter(
        HourlyAggregate.plant_id == plant_id,
        HourlyAggregate.hour_start >= day_start,
        HourlyAggregate.hour_start <= day_end
    ).all()

    if not aggregates:
        return {"error": "Aucune donnée pour cette date"}

    summary = {
        TariffPeriod.HC:  {"kwh_import": 0, "kwh_export": 0, "kwh_selfuse": 0, "kwh_pv": 0, "kwh_conso": 0, "cost": 0, "savings": 0},
        TariffPeriod.HPL: {"kwh_import": 0, "kwh_export": 0, "kwh_selfuse": 0, "kwh_pv": 0, "kwh_conso": 0, "cost": 0, "savings": 0},
        TariffPeriod.HP:  {"kwh_import": 0, "kwh_export": 0, "kwh_selfuse": 0, "kwh_pv": 0, "kwh_conso": 0, "cost": 0, "savings": 0},
    }

    for agg in aggregates:
        period = agg.tariff_period
        if period and period in summary:
            summary[period]["kwh_import"] += agg.grid_import_kwh or 0
            summary[period]["kwh_export"] += agg.grid_export_kwh or 0
            summary[period]["kwh_selfuse"] += agg.self_consumption_kwh or 0
            summary[period]["kwh_pv"] += agg.pv_energy_kwh or 0
            summary[period]["kwh_conso"] += agg.consumption_kwh or 0
            summary[period]["cost"] += agg.estimated_cost_dh or 0
            summary[period]["savings"] += agg.savings_dh or 0

    total_import = sum(s["kwh_import"] for s in summary.values())
    total_export = sum(s["kwh_export"] for s in summary.values())
    total_pv = sum(s["kwh_pv"] for s in summary.values())
    total_conso = sum(s["kwh_conso"] for s in summary.values())
    total_cost = sum(s["cost"] for s in summary.values())
    total_savings = sum(s["savings"] for s in summary.values())

    return {
        "date": target_date.isoformat(),
        "plant_id": plant_id,
        "total_pv_kwh": round(total_pv, 1),
        "total_consumption_kwh": round(total_conso, 1),
        "total_import_kwh": round(total_import, 1),
        "total_export_kwh": round(total_export, 1),
        "total_cost_dh": round(total_cost, 1),
        "total_savings_dh": round(total_savings, 1),
        "breakdown": {
            period.value: {
                "kwh_import": round(data["kwh_import"], 1),
                "kwh_export": round(data["kwh_export"], 1),
                "kwh_selfuse": round(data["kwh_selfuse"], 1),
                "cost_dh": round(data["cost"], 1),
                "savings_dh": round(data["savings"], 1),
                "tariff_dh_kwh": round(get_tariff_rate(period), 4),
            }
            for period, data in summary.items()
        }
    }


# ============================================================
# ALERTES
# ============================================================
@router.get("/alerts")
def get_alerts(status: str = Query(default="all"), limit: int = Query(default=50, le=200), db: Session = Depends(get_db)):
    query = db.query(AlertLog).join(AlertRule)
    if status != "all":
        query = query.filter(AlertLog.status == status)
    alerts = query.order_by(AlertLog.triggered_at.desc()).limit(limit).all()

    return [
        {
            "id": a.id, "rule": a.rule.name if a.rule else None,
            "severity": a.rule.severity.value if a.rule else None,
            "message": a.message, "measured_value": a.measured_value,
            "threshold_value": a.threshold_value,
            "triggered_at": a.triggered_at.isoformat(),
            "status": a.status.value,
        }
        for a in alerts
    ]


# ============================================================
# BILANS JOURNALIERS
# ============================================================
@router.get("/daily-reports")
def get_daily_reports(limit: int = Query(default=30), db: Session = Depends(get_db)):
    reports = db.query(DailySummary).order_by(DailySummary.date.desc()).limit(limit).all()
    return [
        {
            "date": r.date.strftime("%Y-%m-%d"),
            "total_pv_kwh": r.total_pv_kwh, "total_consumption_kwh": r.total_consumption_kwh,
            "total_import_kwh": r.total_import_kwh, "total_export_kwh": r.total_export_kwh,
            "total_cost_dh": r.total_cost_dh, "total_savings_dh": r.total_savings_dh,
            "export_lost_dh": r.export_lost_dh, "alert_count": r.alert_count,
            "breakdown": {
                "HC": {"import_kwh": r.import_hc_kwh, "cost_dh": r.cost_hc, "savings_dh": r.savings_hc_dh},
                "HPL": {"import_kwh": r.import_hpl_kwh, "cost_dh": r.cost_hpl, "savings_dh": r.savings_hpl_dh},
                "HP": {"import_kwh": r.import_hp_kwh, "cost_dh": r.cost_hp, "savings_dh": r.savings_hp_dh},
            }
        }
        for r in reports
    ]


# ============================================================
# FACTURES
# ============================================================
@router.get("/invoices")
def get_invoices(db: Session = Depends(get_db)):
    invoices = db.query(Invoice).order_by(Invoice.year.desc(), Invoice.month.desc()).all()
    return [
        {
            "id": i.id, "year": i.year, "month": i.month,
            "kwh_hc": i.kwh_hc, "kwh_hpl": i.kwh_hpl, "kwh_hp": i.kwh_hp,
            "kwh_total": i.kwh_total, "total_ttc": i.total_ttc,
            "subscribed_power_kva": i.subscribed_power_kva,
            "subscribed_power_cost": i.subscribed_power_cost,
            "excess_power_penalty": i.excess_power_penalty,
            "meter_rental": i.meter_rental,
            "cost_hc": i.cost_hc, "cost_hpl": i.cost_hpl, "cost_hp": i.cost_hp,
            "tariff_hc": i.tariff_hc, "tariff_hpl": i.tariff_hpl, "tariff_hp": i.tariff_hp,
            "tva_rate": i.tva_rate, "total_ht": i.total_ht,
            "notes": i.notes,
        }
        for i in invoices
    ]


class InvoiceCreate(BaseModel):
    year: int
    month: int
    kwh_hp: Optional[float] = 0
    kwh_hpl: Optional[float] = 0
    kwh_hc: Optional[float] = 0
    subscribed_power_kva: Optional[float] = 260
    excess_power_penalty: Optional[float] = 0
    total_ttc: Optional[float] = 0
    tariff_hp: Optional[float] = 1.19975
    tariff_hpl: Optional[float] = 0.85602
    tariff_hc: Optional[float] = 0.62695
    tva_rate: Optional[float] = 0.18
    notes: Optional[str] = None


@router.post("/invoices")
def create_invoice(inv: InvoiceCreate, db: Session = Depends(get_db)):
    existing = db.query(Invoice).filter(
        Invoice.year == inv.year, Invoice.month == inv.month
    ).first()

    kwh_total = (inv.kwh_hp or 0) + (inv.kwh_hpl or 0) + (inv.kwh_hc or 0)
    cost_hp = (inv.kwh_hp or 0) * inv.tariff_hp
    cost_hpl = (inv.kwh_hpl or 0) * inv.tariff_hpl
    cost_hc = (inv.kwh_hc or 0) * inv.tariff_hc
    total_ht = cost_hp + cost_hpl + cost_hc

    data = {
        "kwh_hp": inv.kwh_hp, "kwh_hpl": inv.kwh_hpl, "kwh_hc": inv.kwh_hc,
        "kwh_total": kwh_total,
        "cost_hp": cost_hp, "cost_hpl": cost_hpl, "cost_hc": cost_hc,
        "subscribed_power_kva": inv.subscribed_power_kva,
        "excess_power_penalty": inv.excess_power_penalty,
        "meter_rental": 397,
        "tariff_hp": inv.tariff_hp, "tariff_hpl": inv.tariff_hpl, "tariff_hc": inv.tariff_hc,
        "total_ht": total_ht, "tva_rate": inv.tva_rate,
        "total_ttc": inv.total_ttc,
        "notes": inv.notes,
    }

    if existing:
        for k, v in data.items():
            setattr(existing, k, v)
        db.commit()
        return {"message": f"Facture {inv.month}/{inv.year} mise à jour", "id": existing.id}
    else:
        record = Invoice(year=inv.year, month=inv.month, **data)
        db.add(record)
        db.commit()
        return {"message": f"Facture {inv.month}/{inv.year} créée", "id": record.id}


@router.delete("/invoices/{invoice_id}")
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        return {"error": "Facture introuvable"}
    db.delete(inv)
    db.commit()
    return {"message": f"Facture {inv.month}/{inv.year} supprimée"}


# ============================================================
# PARAMÈTRES SYSTÈME
# ============================================================
@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    """Récupérer tous les paramètres groupés par catégorie"""
    all_settings = db.query(SystemSetting).order_by(SystemSetting.category).all()

    grouped = {}
    for s in all_settings:
        if s.category not in grouped:
            grouped[s.category] = []
        grouped[s.category].append({
            "key": s.key,
            "value": s.value,
            "label": s.label,
            "unit": s.unit,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None
        })

    return grouped


class SettingUpdate(BaseModel):
    value: str


@router.put("/settings/{key}")
def update_setting(key: str, update: SettingUpdate, db: Session = Depends(get_db)):
    """Modifier un paramètre"""
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not setting:
        return {"error": f"Paramètre '{key}' introuvable"}

    old_value = setting.value
    setting.value = update.value
    setting.updated_at = datetime.utcnow()
    db.commit()

    return {
        "key": key,
        "old_value": old_value,
        "new_value": update.value,
        "message": f"✅ {setting.label} mis à jour: {old_value} → {update.value}"
    }


# ============================================================
# PUSH SUBSCRIPTIONS
# ============================================================
class PushSubscribeRequest(BaseModel):
    subscription: dict


@router.post("/push/subscribe")
def subscribe_push(req: PushSubscribeRequest, db: Session = Depends(get_db)):
    import json
    endpoint = req.subscription.get("endpoint", "")
    existing = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
    if existing:
        existing.is_active = True
        existing.subscription_json = json.dumps(req.subscription)
        db.commit()
        return {"message": "Abonnement push mis à jour"}

    sub = PushSubscription(
        subscription_json=json.dumps(req.subscription),
        endpoint=endpoint,
        is_active=True
    )
    db.add(sub)
    db.commit()
    return {"message": "Abonnement push créé"}


@router.get("/push/vapid-key")
def get_vapid_key():
    from app.config import settings
    return {"publicKey": settings.VAPID_PUBLIC_KEY}


# ============================================================
# DONNÉES SRM RÉELLES
# ============================================================
class SrmDataRequest(BaseModel):
    real_kwh_hp: Optional[float] = None
    real_kwh_hpl: Optional[float] = None
    real_kwh_hc: Optional[float] = None
    real_rdps_kva: Optional[float] = None
    real_rdps_cost: Optional[float] = None
    real_total_ttc: Optional[float] = None


@router.put("/invoices/{invoice_id}/srm")
def update_srm_data(invoice_id: int, req: SrmDataRequest, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        return {"error": "Facture introuvable"}

    if req.real_kwh_hp is not None: inv.real_kwh_hp = req.real_kwh_hp
    if req.real_kwh_hpl is not None: inv.real_kwh_hpl = req.real_kwh_hpl
    if req.real_kwh_hc is not None: inv.real_kwh_hc = req.real_kwh_hc
    if req.real_rdps_kva is not None: inv.real_rdps_kva = req.real_rdps_kva
    if req.real_rdps_cost is not None: inv.real_rdps_cost = req.real_rdps_cost
    if req.real_total_ttc is not None: inv.real_total_ttc = req.real_total_ttc

    inv.real_kwh_total = (inv.real_kwh_hp or 0) + (inv.real_kwh_hpl or 0) + (inv.real_kwh_hc or 0)
    inv.data_source = "real"
    db.commit()

    return {"message": f"Données SRM {inv.month}/{inv.year} mises à jour"}


# ============================================================
# COMPARAISON ESTIMÉ VS RÉEL
# ============================================================
@router.get("/invoices/comparison")
def get_comparison(db: Session = Depends(get_db)):
    invoices = db.query(Invoice).filter(
        Invoice.real_kwh_total != None
    ).order_by(Invoice.year, Invoice.month).all()

    return [
        {
            "period": f"{i.month}/{i.year}",
            "estimated": {
                "kwh_hp": i.kwh_hp, "kwh_hpl": i.kwh_hpl, "kwh_hc": i.kwh_hc,
                "kwh_total": i.kwh_total, "total_ttc": i.total_ttc
            },
            "real": {
                "kwh_hp": i.real_kwh_hp, "kwh_hpl": i.real_kwh_hpl, "kwh_hc": i.real_kwh_hc,
                "kwh_total": i.real_kwh_total, "total_ttc": i.real_total_ttc,
                "rdps_kva": i.real_rdps_kva, "rdps_cost": i.real_rdps_cost
            },
            "ecart": {
                "kwh_total": round((i.kwh_total or 0) - (i.real_kwh_total or 0), 1),
                "total_ttc": round((i.total_ttc or 0) - (i.real_total_ttc or 0), 1)
            }
        }
        for i in invoices
    ]


# ============================================================
# AGRÉGATIONS MENSUELLES / ANNUELLES
# ============================================================
@router.get("/stats/monthly/{plant_id}")
def get_monthly_stats(plant_id: int, year: int = Query(default=2026), db: Session = Depends(get_db)):
    summaries = db.query(DailySummary).filter(
        DailySummary.plant_id == plant_id,
        func.extract('year', DailySummary.date) == year
    ).all()

    months = {}
    for s in summaries:
        m = s.date.month
        if m not in months:
            months[m] = {"pv": 0, "conso": 0, "import": 0, "export": 0, "cost": 0, "savings": 0, "alerts": 0, "days": 0}
        months[m]["pv"] += s.total_pv_kwh or 0
        months[m]["conso"] += s.total_consumption_kwh or 0
        months[m]["import"] += s.total_import_kwh or 0
        months[m]["export"] += s.total_export_kwh or 0
        months[m]["cost"] += s.total_cost_dh or 0
        months[m]["savings"] += s.total_savings_dh or 0
        months[m]["alerts"] += s.alert_count or 0
        months[m]["days"] += 1

    return {"year": year, "months": months}


@router.get("/stats/yearly/{plant_id}")
def get_yearly_stats(plant_id: int, db: Session = Depends(get_db)):
    summaries = db.query(DailySummary).filter(
        DailySummary.plant_id == plant_id
    ).all()

    years = {}
    for s in summaries:
        y = s.date.year
        if y not in years:
            years[y] = {"pv": 0, "conso": 0, "import": 0, "export": 0, "cost": 0, "savings": 0, "alerts": 0, "days": 0}
        years[y]["pv"] += s.total_pv_kwh or 0
        years[y]["conso"] += s.total_consumption_kwh or 0
        years[y]["import"] += s.total_import_kwh or 0
        years[y]["export"] += s.total_export_kwh or 0
        years[y]["cost"] += s.total_cost_dh or 0
        years[y]["savings"] += s.total_savings_dh or 0
        years[y]["alerts"] += s.alert_count or 0
        years[y]["days"] += 1

    return {"years": years}


# ============================================================
# ÉCONOMIES SOLAIRES
# ============================================================
@router.get("/savings/{plant_id}")
def get_solar_savings(plant_id: int, period: str = Query(default="month"), db: Session = Depends(get_db)):
    now = datetime.now()

    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    aggregates = db.query(HourlyAggregate).filter(
        HourlyAggregate.plant_id == plant_id,
        HourlyAggregate.hour_start >= start
    ).all()

    total_savings = sum(a.savings_dh or 0 for a in aggregates)
    total_selfuse = sum(a.self_consumption_kwh or 0 for a in aggregates)
    total_import_cost = sum(a.estimated_cost_dh or 0 for a in aggregates)
    total_export = sum(a.grid_export_kwh or 0 for a in aggregates)

    return {
        "period": period,
        "start": start.isoformat(),
        "total_savings_dh": round(total_savings, 1),
        "total_selfuse_kwh": round(total_selfuse, 1),
        "total_import_cost_dh": round(total_import_cost, 1),
        "total_export_kwh": round(total_export, 1),
        "export_lost_dh": round(total_export * get_tariff_rate(TariffPeriod.HPL), 1)
    }
