"""
Modèles de données - Tables SQLAlchemy
"""
from sqlalchemy import (
    Column, Integer, Float, String, DateTime, Boolean,
    ForeignKey, Text, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import enum


class TariffPeriod(str, enum.Enum):
    HC = "HC"
    HPL = "HPL"
    HP = "HP"

class AlertSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class AlertStatus(str, enum.Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"

class Season(str, enum.Enum):
    SUMMER = "summer"
    WINTER = "winter"

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    ENGINEER = "engineer"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.ENGINEER)
    is_active = Column(Boolean, default=True)
    receive_alerts = Column(Boolean, default=True)
    telegram_chat_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Plant(Base):
    __tablename__ = "plants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    fusionsolar_code = Column(String(100), unique=True, nullable=False)
    capacity_kwp = Column(Float, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    readings = relationship("EnergyReading", back_populates="plant")
    hourly_aggregates = relationship("HourlyAggregate", back_populates="plant")
    alert_logs = relationship("AlertLog", back_populates="plant")
    daily_summaries = relationship("DailySummary", back_populates="plant")


class EnergyReading(Base):
    __tablename__ = "energy_readings"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    pv_power = Column(Float, nullable=True)
    consumption_raw = Column(Float, nullable=True)
    grid_import_raw = Column(Float, nullable=True)
    consumption_corrected = Column(Float, nullable=True)
    grid_import = Column(Float, nullable=True)
    grid_export = Column(Float, nullable=True)
    self_consumption = Column(Float, nullable=True)
    tariff_period = Column(SQLEnum(TariffPeriod), nullable=True)
    season = Column(SQLEnum(Season), nullable=True)
    plant = relationship("Plant", back_populates="readings")


class HourlyAggregate(Base):
    __tablename__ = "hourly_aggregates"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    hour_start = Column(DateTime, nullable=False, index=True)
    avg_pv_power = Column(Float, nullable=True)
    avg_consumption = Column(Float, nullable=True)
    avg_grid_import = Column(Float, nullable=True)
    avg_grid_export = Column(Float, nullable=True)
    avg_self_consumption = Column(Float, nullable=True)
    pv_energy_kwh = Column(Float, nullable=True)
    consumption_kwh = Column(Float, nullable=True)
    grid_import_kwh = Column(Float, nullable=True)
    grid_export_kwh = Column(Float, nullable=True)
    self_consumption_kwh = Column(Float, nullable=True)
    tariff_period = Column(SQLEnum(TariffPeriod), nullable=True)
    season = Column(SQLEnum(Season), nullable=True)
    estimated_cost_dh = Column(Float, nullable=True)
    savings_dh = Column(Float, nullable=True)
    sample_count = Column(Integer, default=0)
    plant = relationship("Plant", back_populates="hourly_aggregates")


class DailySummary(Base):
    __tablename__ = "daily_summaries"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    date = Column(DateTime, nullable=False, index=True)
    total_pv_kwh = Column(Float, default=0)
    total_consumption_kwh = Column(Float, default=0)
    import_hc_kwh = Column(Float, default=0)
    import_hpl_kwh = Column(Float, default=0)
    import_hp_kwh = Column(Float, default=0)
    total_import_kwh = Column(Float, default=0)
    total_export_kwh = Column(Float, default=0)
    selfuse_hc_kwh = Column(Float, default=0)
    selfuse_hpl_kwh = Column(Float, default=0)
    selfuse_hp_kwh = Column(Float, default=0)
    total_selfuse_kwh = Column(Float, default=0)
    cost_hc = Column(Float, default=0)
    cost_hpl = Column(Float, default=0)
    cost_hp = Column(Float, default=0)
    total_cost_dh = Column(Float, default=0)
    savings_hc_dh = Column(Float, default=0)
    savings_hpl_dh = Column(Float, default=0)
    savings_hp_dh = Column(Float, default=0)
    total_savings_dh = Column(Float, default=0)
    export_lost_dh = Column(Float, default=0)
    fusionsolar_selfprovide = Column(Float, default=0)
    alert_count = Column(Integer, default=0)
    report_sent = Column(Boolean, default=False)
    plant = relationship("Plant", back_populates="daily_summaries")


# ============================================================
# PARAMÈTRES SYSTÈME (modifiables depuis l'UI)
# ============================================================
class SystemSetting(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(String(255), nullable=False)
    label = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False)
    unit = Column(String(20), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Valeurs initiales des paramètres
DEFAULT_SETTINGS = [
    # Tarifs énergie
    {"key": "tarif_hp_ht", "value": "1.19975", "label": "Tarif HP", "category": "tarifs_energie", "unit": "DH/kWh HT"},
    {"key": "tarif_hpl_ht", "value": "0.85602", "label": "Tarif HPL", "category": "tarifs_energie", "unit": "DH/kWh HT"},
    {"key": "tarif_hc_ht", "value": "0.62695", "label": "Tarif HC", "category": "tarifs_energie", "unit": "DH/kWh HT"},
    {"key": "tva_energie", "value": "0.18", "label": "TVA Énergie", "category": "tarifs_energie", "unit": "%"},

    # Puissance souscrite
    {"key": "puissance_souscrite_kva", "value": "260", "label": "Puissance souscrite", "category": "puissance", "unit": "KVA"},
    {"key": "prix_kva_ht", "value": "36.20250", "label": "Prix par KVA", "category": "puissance", "unit": "DH/KVA HT"},
    {"key": "tva_puissance", "value": "0.18", "label": "TVA Puissance", "category": "puissance", "unit": "%"},

    # Location compteur
    {"key": "location_compteur_ht", "value": "397", "label": "Location compteur", "category": "compteur", "unit": "DH HT"},
    {"key": "tva_location", "value": "0.15", "label": "TVA Location", "category": "compteur", "unit": "%"},

    # Entretien compteur
    {"key": "entretien_compteur_ht", "value": "326", "label": "Entretien compteur", "category": "compteur", "unit": "DH HT"},
    {"key": "tva_entretien", "value": "0.20", "label": "TVA Entretien", "category": "compteur", "unit": "%"},

    # RDPS
    {"key": "prix_rdps_kva_ht", "value": "54.30338", "label": "Prix RDPS par KVA", "category": "rdps", "unit": "DH/KVA HT"},
    {"key": "tva_rdps", "value": "0.18", "label": "TVA RDPS", "category": "rdps", "unit": "%"},

    # Correction
    {"key": "power_correction_kw", "value": "48", "label": "Correction puissance", "category": "correction", "unit": "kW"},
]


class AlertRule(Base):
    __tablename__ = "alert_rules"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    rule_code = Column(String(50), unique=True, nullable=False)
    metric = Column(String(50), nullable=False)
    operator = Column(String(10), nullable=False)
    threshold = Column(Float, nullable=False)
    time_start = Column(String(5), nullable=True)
    time_end = Column(String(5), nullable=True)
    severity = Column(SQLEnum(AlertSeverity), default=AlertSeverity.WARNING)
    is_active = Column(Boolean, default=True)
    cooldown_minutes = Column(Integer, default=30)
    notify_telegram = Column(Boolean, default=True)
    notify_email = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    logs = relationship("AlertLog", back_populates="rule")


class AlertLog(Base):
    __tablename__ = "alert_logs"
    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("alert_rules.id"), nullable=False)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    triggered_at = Column(DateTime, default=datetime.utcnow, index=True)
    measured_value = Column(Float, nullable=True)
    threshold_value = Column(Float, nullable=True)
    message = Column(Text, nullable=True)
    status = Column(SQLEnum(AlertStatus), default=AlertStatus.ACTIVE)
    acknowledged_by = Column(String(100), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    rule = relationship("AlertRule", back_populates="logs")
    plant = relationship("Plant", back_populates="alert_logs")


class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    kwh_hc = Column(Float, nullable=True)
    kwh_hpl = Column(Float, nullable=True)
    kwh_hp = Column(Float, nullable=True)
    kwh_total = Column(Float, nullable=True)
    cost_hc = Column(Float, nullable=True)
    cost_hpl = Column(Float, nullable=True)
    cost_hp = Column(Float, nullable=True)
    subscribed_power_kva = Column(Float, nullable=True)
    subscribed_power_cost = Column(Float, nullable=True)
    excess_power_penalty = Column(Float, nullable=True)
    meter_rental = Column(Float, nullable=True)
    tariff_hc = Column(Float, nullable=True)
    tariff_hpl = Column(Float, nullable=True)
    tariff_hp = Column(Float, nullable=True)
    total_ht = Column(Float, nullable=True)
    tva_rate = Column(Float, default=0.18)
    total_ttc = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Données réelles SRM (saisie manuelle)
    real_kwh_hp = Column(Float, nullable=True)
    real_kwh_hpl = Column(Float, nullable=True)
    real_kwh_hc = Column(Float, nullable=True)
    real_kwh_total = Column(Float, nullable=True)
    real_rdps_kva = Column(Float, nullable=True)
    real_rdps_cost = Column(Float, nullable=True)
    real_total_ttc = Column(Float, nullable=True)
    data_source = Column(String(20), default="estimated")  # estimated / real


# ============================================================
# PUSH SUBSCRIPTIONS
# ============================================================
class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    subscription_json = Column(Text, nullable=False)
    endpoint = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
