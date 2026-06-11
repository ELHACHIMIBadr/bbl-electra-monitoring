"""
Bilans automatiques - B2 Journalier / B3 Mensuel
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.models import (
    Plant, HourlyAggregate, DailySummary, AlertLog, TariffPeriod
)
from app.utils.tariffs import get_tariff_rate
from app.services.notifications import send_alert
from app.config import settings
from app.database import SessionLocal
import logging

logger = logging.getLogger(__name__)


# ============================================================
# B2 — BILAN JOURNALIER (à 00:00)
# ============================================================
def generate_daily_report():
    logger.info("📊 Génération du bilan journalier...")
    db = SessionLocal()

    try:
        yesterday = (datetime.now() - timedelta(days=1)).date()
        yesterday_start = datetime.combine(yesterday, datetime.min.time())
        yesterday_end = datetime.combine(yesterday, datetime.max.time())

        plant = db.query(Plant).filter(
            Plant.fusionsolar_code == settings.TARGET_PLANT_ID
        ).first()

        if not plant:
            logger.error("❌ Centrale introuvable")
            return

        aggregates = db.query(HourlyAggregate).filter(
            HourlyAggregate.plant_id == plant.id,
            HourlyAggregate.hour_start >= yesterday_start,
            HourlyAggregate.hour_start <= yesterday_end
        ).all()

        if not aggregates:
            logger.warning("⚠️ Pas de données pour le bilan")
            return

        totals = {
            TariffPeriod.HC:  {"import": 0, "export": 0, "selfuse": 0, "pv": 0, "conso": 0, "cost": 0, "savings": 0},
            TariffPeriod.HPL: {"import": 0, "export": 0, "selfuse": 0, "pv": 0, "conso": 0, "cost": 0, "savings": 0},
            TariffPeriod.HP:  {"import": 0, "export": 0, "selfuse": 0, "pv": 0, "conso": 0, "cost": 0, "savings": 0},
        }

        for agg in aggregates:
            period = agg.tariff_period
            if period and period in totals:
                totals[period]["import"] += agg.grid_import_kwh or 0
                totals[period]["export"] += agg.grid_export_kwh or 0
                totals[period]["selfuse"] += agg.self_consumption_kwh or 0
                totals[period]["pv"] += agg.pv_energy_kwh or 0
                totals[period]["conso"] += agg.consumption_kwh or 0
                totals[period]["cost"] += agg.estimated_cost_dh or 0
                totals[period]["savings"] += agg.savings_dh or 0

        total_pv = sum(t["pv"] for t in totals.values())
        total_conso = sum(t["conso"] for t in totals.values())
        total_import = sum(t["import"] for t in totals.values())
        total_export = sum(t["export"] for t in totals.values())
        total_selfuse = sum(t["selfuse"] for t in totals.values())
        total_cost = sum(t["cost"] for t in totals.values())
        total_savings = sum(t["savings"] for t in totals.values())
        export_lost_dh = total_export * get_tariff_rate(TariffPeriod.HPL)

        alert_count = db.query(func.count(AlertLog.id)).filter(
            AlertLog.plant_id == plant.id,
            AlertLog.triggered_at >= yesterday_start,
            AlertLog.triggered_at <= yesterday_end
        ).scalar() or 0

        summary = DailySummary(
            plant_id=plant.id, date=yesterday_start,
            total_pv_kwh=total_pv, total_consumption_kwh=total_conso,
            import_hc_kwh=totals[TariffPeriod.HC]["import"],
            import_hpl_kwh=totals[TariffPeriod.HPL]["import"],
            import_hp_kwh=totals[TariffPeriod.HP]["import"],
            total_import_kwh=total_import, total_export_kwh=total_export,
            selfuse_hc_kwh=totals[TariffPeriod.HC]["selfuse"],
            selfuse_hpl_kwh=totals[TariffPeriod.HPL]["selfuse"],
            selfuse_hp_kwh=totals[TariffPeriod.HP]["selfuse"],
            total_selfuse_kwh=total_selfuse,
            cost_hc=totals[TariffPeriod.HC]["cost"],
            cost_hpl=totals[TariffPeriod.HPL]["cost"],
            cost_hp=totals[TariffPeriod.HP]["cost"],
            total_cost_dh=total_cost,
            savings_hc_dh=totals[TariffPeriod.HC]["savings"],
            savings_hpl_dh=totals[TariffPeriod.HPL]["savings"],
            savings_hp_dh=totals[TariffPeriod.HP]["savings"],
            total_savings_dh=total_savings,
            export_lost_dh=export_lost_dh,
            alert_count=alert_count, report_sent=True
        )
        db.add(summary)
        db.commit()

        date_str = yesterday.strftime("%d/%m/%Y")
        message = f"""📊 <b>Bilan du {date_str} — FERME OUM AZZA</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚡ Production PV :           {total_pv:.0f} kWh
🏭 Consommation estimée :   {total_conso:.0f} kWh
☀️ Autoconsommation :        {total_selfuse:.0f} kWh

━━━━━━━━ Import réseau ━━━━━━━━
📥 HC  (nuit) :     {totals[TariffPeriod.HC]['import']:.0f} kWh → {totals[TariffPeriod.HC]['cost']:.0f} DH
📥 HPL (jour) :     {totals[TariffPeriod.HPL]['import']:.0f} kWh → {totals[TariffPeriod.HPL]['cost']:.0f} DH
📥 HP  (pointe) :   {totals[TariffPeriod.HP]['import']:.0f} kWh → {totals[TariffPeriod.HP]['cost']:.0f} DH
   Total import :   {total_import:.0f} kWh → {total_cost:.0f} DH

━━━━━━━━ Export réseau ━━━━━━━━
📤 Export :          {total_export:.0f} kWh → {export_lost_dh:.0f} DH perdus

━━━━━━ Économies solaires ━━━━━━
☀️ HC  :  {totals[TariffPeriod.HC]['selfuse']:.0f} kWh → {totals[TariffPeriod.HC]['savings']:.0f} DH
☀️ HPL :  {totals[TariffPeriod.HPL]['selfuse']:.0f} kWh → {totals[TariffPeriod.HPL]['savings']:.0f} DH
☀️ HP  :  {totals[TariffPeriod.HP]['selfuse']:.0f} kWh → {totals[TariffPeriod.HP]['savings']:.0f} DH
   Total économisé : {total_savings:.0f} DH

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 Coût réseau du jour :      {total_cost:.0f} DH
☀️ Économisé grâce au PV :   {total_savings:.0f} DH
📤 Perdu en export :          {export_lost_dh:.0f} DH
⚠️ Alertes déclenchées :      {alert_count}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

        send_alert(message, telegram=True, email=True)
        logger.info(f"✅ Bilan du {date_str} envoyé")

    except Exception as e:
        logger.error(f"❌ Erreur bilan journalier: {e}")
        db.rollback()
    finally:
        db.close()


# ============================================================
# B3 — FACTURE MENSUELLE ESTIMÉE (1er de chaque mois à 00:00)
# ============================================================
def generate_monthly_invoice():
    logger.info("🧾 Génération de la facture mensuelle estimée...")
    db = SessionLocal()

    try:
        # Mois précédent
        today = datetime.now()
        first_of_month = today.replace(day=1)
        last_month_end = first_of_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)

        month_name = last_month_end.strftime("%B %Y")
        month_str = last_month_end.strftime("%m/%Y")

        plant = db.query(Plant).filter(
            Plant.fusionsolar_code == settings.TARGET_PLANT_ID
        ).first()

        if not plant:
            logger.error("❌ Centrale introuvable")
            return

        # Somme des bilans journaliers du mois
        summaries = db.query(DailySummary).filter(
            DailySummary.plant_id == plant.id,
            DailySummary.date >= last_month_start,
            DailySummary.date <= last_month_end
        ).all()

        # Si pas de bilans journaliers, calculer depuis les agrégats horaires
        if summaries:
            hp_kwh = sum(s.import_hp_kwh or 0 for s in summaries)
            hpl_kwh = sum(s.import_hpl_kwh or 0 for s in summaries)
            hc_kwh = sum(s.import_hc_kwh or 0 for s in summaries)
            total_export = sum(s.total_export_kwh or 0 for s in summaries)
            total_pv = sum(s.total_pv_kwh or 0 for s in summaries)
            total_savings = sum(s.total_savings_dh or 0 for s in summaries)
            total_alerts = sum(s.alert_count or 0 for s in summaries)
            nb_jours = len(summaries)
        else:
            # Fallback: calculer depuis les agrégats horaires
            aggregates = db.query(HourlyAggregate).filter(
                HourlyAggregate.plant_id == plant.id,
                HourlyAggregate.hour_start >= last_month_start,
                HourlyAggregate.hour_start <= last_month_end
            ).all()

            hp_kwh = sum(a.grid_import_kwh or 0 for a in aggregates if a.tariff_period == TariffPeriod.HP)
            hpl_kwh = sum(a.grid_import_kwh or 0 for a in aggregates if a.tariff_period == TariffPeriod.HPL)
            hc_kwh = sum(a.grid_import_kwh or 0 for a in aggregates if a.tariff_period == TariffPeriod.HC)
            total_export = sum(a.grid_export_kwh or 0 for a in aggregates)
            total_pv = sum(a.pv_energy_kwh or 0 for a in aggregates)
            total_savings = sum(a.savings_dh or 0 for a in aggregates)
            total_alerts = 0
            nb_jours = (last_month_end - last_month_start).days + 1

        # ============================================================
        # CALCUL FACTURE
        # ============================================================

        # Énergie
        energie_hp = hp_kwh * settings.TARIF_HP_HT
        energie_hpl = hpl_kwh * settings.TARIF_HPL_HT
        energie_hc = hc_kwh * settings.TARIF_HC_HT
        energie_ht = energie_hp + energie_hpl + energie_hc
        energie_ttc = energie_ht * (1 + settings.TVA_ENERGIE)

        # Puissance souscrite
        puissance_ht = settings.PUISSANCE_SOUSCRITE_KVA * settings.PRIX_KVA_HT
        puissance_ttc = puissance_ht * (1 + settings.TVA_PUISSANCE)

        # Location compteur
        location_ttc = settings.LOCATION_COMPTEUR_HT * (1 + settings.TVA_LOCATION)

        # Entretien compteur
        entretien_ttc = settings.ENTRETIEN_COMPTEUR_HT * (1 + settings.TVA_ENTRETIEN)

        # Total (sans RDPS)
        total_ttc = energie_ttc + puissance_ttc + location_ttc + entretien_ttc

        total_kwh = hp_kwh + hpl_kwh + hc_kwh

        # Prix RDPS par KVA pour info
        rdps_prix_ttc = settings.PRIX_RDPS_KVA_HT * (1 + settings.TVA_RDPS)

        # ============================================================
        # MESSAGE
        # ============================================================
        message = f"""🧾 <b>FACTURE ESTIMÉE — {month_str}</b>
<b>FERME OUM AZZA-BBL</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 Période : {last_month_start.strftime('%d/%m')} → {last_month_end.strftime('%d/%m/%Y')}
📊 Données collectées : {nb_jours} jours

━━━━━━━ Consommation réseau ━━━━━━━
⚡ HP  (pointe) :   {hp_kwh:.0f} kWh × {settings.TARIF_HP_HT} = {energie_hp:.0f} DH HT
⚡ HPL (jour) :     {hpl_kwh:.0f} kWh × {settings.TARIF_HPL_HT} = {energie_hpl:.0f} DH HT
⚡ HC  (nuit) :     {hc_kwh:.0f} kWh × {settings.TARIF_HC_HT} = {energie_hc:.0f} DH HT
   Sous-total énergie HT :     {energie_ht:.0f} DH
   TVA 18% :                    {energie_ht * settings.TVA_ENERGIE:.0f} DH
   <b>Énergie TTC :               {energie_ttc:.0f} DH</b>

━━━━━━━━ Frais fixes ━━━━━━━━
🔌 Puissance souscrite :  {settings.PUISSANCE_SOUSCRITE_KVA:.0f} KVA × {settings.PRIX_KVA_HT:.2f} × 1.18 = {puissance_ttc:.0f} DH
📟 Location compteur :    {settings.LOCATION_COMPTEUR_HT:.0f} × 1.15 = {location_ttc:.0f} DH
🔧 Entretien compteur :   {settings.ENTRETIEN_COMPTEUR_HT:.0f} × 1.20 = {entretien_ttc:.0f} DH

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>TOTAL ESTIMÉ (hors RDPS) : {total_ttc:.0f} DH TTC</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━━━━━ Bilan solaire du mois ━━━━━━━
☀️ Production PV totale :    {total_pv:.0f} kWh
📤 Export réseau (perdu) :   {total_export:.0f} kWh
💰 Économisé grâce au PV :  {total_savings:.0f} DH
⚠️ Alertes sur le mois :     {total_alerts}

━━━━━━━━ ACTION REQUISE ━━━━━━━━
⚠️ <b>Merci de vérifier avec les données réelles SRM :</b>
   1. Relevé HP / HPL / HC du compteur SRM
   2. Vérifier s'il y a eu un RDPS (dépassement puissance souscrite)
      → Prix RDPS : {rdps_prix_ttc:.2f} DH TTC par KVA dépassé
   3. Comparer avec notre estimation pour calibrer le système
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

        send_alert(message, telegram=True, email=True)
        logger.info(f"✅ Facture estimée {month_str} envoyée")

    except Exception as e:
        logger.error(f"❌ Erreur facture mensuelle: {e}")
        db.rollback()
    finally:
        db.close()
