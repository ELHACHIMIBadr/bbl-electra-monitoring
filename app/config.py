"""
Configuration - Chargement des variables d'environnement
"""
from dotenv import load_dotenv
import os

load_dotenv()


class Settings:
    # FusionSolar
    FUSIONSOLAR_USER: str = os.getenv("FUSIONSOLAR_USER", "")
    FUSIONSOLAR_PASSWORD: str = os.getenv("FUSIONSOLAR_PASSWORD", "")
    FUSIONSOLAR_SUBDOMAIN: str = os.getenv("FUSIONSOLAR_SUBDOMAIN", "uni001eu5")

    # Northbound API
    NORTHBOUND_USER: str = os.getenv("NORTHBOUND_USER", "")
    NORTHBOUND_SYSTEM_CODE: str = os.getenv("NORTHBOUND_SYSTEM_CODE", "")
    NORTHBOUND_BASE_URL: str = os.getenv("NORTHBOUND_BASE_URL", "")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./bbl_monitoring.db")

    # Centrale cible
    TARGET_PLANT_ID: str = os.getenv("TARGET_PLANT_ID", "NE=159911543")
    TARGET_PLANT_NAME: str = os.getenv("TARGET_PLANT_NAME", "FERME OUM AZZA-BBL")
    TARGET_PLANT_CAPACITY_KWP: float = float(os.getenv("TARGET_PLANT_CAPACITY_KWP", "480"))

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Email
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    EMAIL_RECIPIENTS: list = os.getenv("EMAIL_RECIPIENTS", "").split(",")

    # Correction Factor
    POWER_CORRECTION_KW: float = float(os.getenv("POWER_CORRECTION_KW", "48"))
    ENERGY_CORRECTION_KWH: float = float(os.getenv("ENERGY_CORRECTION_KWH", "1145"))

    # Tarifs énergie (DH/kWh HT)
    TARIF_HP_HT: float = float(os.getenv("TARIF_HP_HT", "1.19975"))
    TARIF_HPL_HT: float = float(os.getenv("TARIF_HPL_HT", "0.85602"))
    TARIF_HC_HT: float = float(os.getenv("TARIF_HC_HT", "0.62695"))
    TVA_ENERGIE: float = float(os.getenv("TVA_ENERGIE", "0.18"))

    # Puissance souscrite
    PUISSANCE_SOUSCRITE_KVA: float = float(os.getenv("PUISSANCE_SOUSCRITE_KVA", "260"))
    PRIX_KVA_HT: float = float(os.getenv("PRIX_KVA_HT", "36.20250"))
    TVA_PUISSANCE: float = float(os.getenv("TVA_PUISSANCE", "0.18"))

    # Location compteur
    LOCATION_COMPTEUR_HT: float = float(os.getenv("LOCATION_COMPTEUR_HT", "397"))
    TVA_LOCATION: float = float(os.getenv("TVA_LOCATION", "0.15"))

    # Entretien compteur
    ENTRETIEN_COMPTEUR_HT: float = float(os.getenv("ENTRETIEN_COMPTEUR_HT", "326"))
    TVA_ENTRETIEN: float = float(os.getenv("TVA_ENTRETIEN", "0.20"))

    # RDPS
    PRIX_RDPS_KVA_HT: float = float(os.getenv("PRIX_RDPS_KVA_HT", "54.30338"))
    TVA_RDPS: float = float(os.getenv("TVA_RDPS", "0.18"))

    # App
    APP_ENV: str = os.getenv("APP_ENV", "development")
    COLLECT_INTERVAL_MINUTES: int = int(os.getenv("COLLECT_INTERVAL_MINUTES", "5"))

    # VAPID (Push notifications)
    VAPID_PRIVATE_KEY: str = os.getenv("VAPID_PRIVATE_KEY", "")
    VAPID_PUBLIC_KEY: str = os.getenv("VAPID_PUBLIC_KEY", "")
    VAPID_EMAIL: str = os.getenv("VAPID_EMAIL", "admin@bbl-electra.com")


settings = Settings()
