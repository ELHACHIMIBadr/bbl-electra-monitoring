"""
Service FusionSolar - Connexion et récupération des données
Utilise FusionSolarPy (compte utilisateur normal)
"""
from fusion_solar_py.client import FusionSolarClient
from app.config import settings
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class FusionSolarService:
    """Client pour récupérer les données FusionSolar"""

    def __init__(self):
        self.client = None
        self.plant_ids = []

    def connect(self):
        """Se connecter à FusionSolar"""
        try:
            self.client = FusionSolarClient(
                settings.FUSIONSOLAR_USER,
                settings.FUSIONSOLAR_PASSWORD,
                huawei_subdomain=settings.FUSIONSOLAR_SUBDOMAIN
            )
            self.plant_ids = self.client.get_plant_ids()
            logger.info(f"✅ Connecté à FusionSolar — {len(self.plant_ids)} centrales trouvées")
            return True
        except Exception as e:
            logger.error(f"❌ Échec connexion FusionSolar: {e}")
            return False

    def disconnect(self):
        """Se déconnecter proprement"""
        if self.client:
            try:
                self.client.log_out()
                logger.info("🔒 Déconnexion FusionSolar")
            except Exception:
                pass

    def get_plant_list(self) -> list:
        """Récupérer la liste des centrales"""
        try:
            stations = self.client.get_station_list()
            return stations
        except Exception as e:
            logger.error(f"Erreur get_plant_list: {e}")
            return []

    def get_realtime_data(self, plant_id: str) -> dict:
        """
        Récupérer les données temps réel d'une centrale
        Inclut les totaux journaliers et les économies solaires
        """
        try:
            plant_data = self.client.get_plant_stats(plant_id)
            last = self.client.get_last_plant_data(plant_data)

            # Détecter si la centrale est hors ligne
            # FusionSolar retourne status=1 (online) ou status=0 (offline)
            station_status = last.get("stationStatus") or last.get("status") or last.get("connectStatus")
            if isinstance(station_status, dict):
                station_status = station_status.get("value")
            
            # Aussi: si productPower est None/absent = hors ligne
            pv_raw = last.get("productPower")
            is_offline = (pv_raw is None) or (station_status is not None and str(station_status) in ['0', '2', '3'])

            # Récupérer les économies solaires depuis FusionSolar
            # selfProvide = kWh autoconsommés (valeur monétaire disponible via station)
            solar_savings_kwh = last.get("totalSelfUsePower", 0)
            if isinstance(solar_savings_kwh, dict):
                solar_savings_kwh = solar_savings_kwh.get("value", 0)
            solar_savings_kwh = float(solar_savings_kwh) if solar_savings_kwh else 0

            # Revenus du jour depuis FusionSolar (DH)
            # Disponible via selfProvide ou day_income selon l'endpoint
            solar_savings_dh = last.get("selfProvide", 0)
            if isinstance(solar_savings_dh, dict):
                solar_savings_dh = solar_savings_dh.get("value", 0)
            solar_savings_dh = float(solar_savings_dh) if solar_savings_dh else 0

            result = {
                "timestamp": datetime.now(),
                "plant_id": plant_id,
                # Instantané (kW)
                "pv_power": self._extract_value(last.get("productPower")),
                "consumption_raw": self._extract_value(last.get("usePower")),
                "on_grid_power": self._extract_value(last.get("onGridPower")),
                "grid_import_raw": self._extract_value(last.get("disGridPower")),
                "self_use_power": self._extract_value(last.get("selfUsePower")),
                "charge_power": self._extract_value(last.get("chargePower")),
                "discharge_power": self._extract_value(last.get("dischargePower")),
                "meter_active_power": self._extract_value(last.get("meterActivePower")),
                # Totaux journaliers (kWh)
                "total_pv_today": self._to_float(last.get("totalProductPower")),
                "total_consumption_today": self._to_float(last.get("totalUsePower")),
                "total_grid_import_today": self._to_float(last.get("totalBuyPower")),
                "total_grid_export_today": self._to_float(last.get("totalOnGridPower")),
                "total_self_use_today": self._to_float(last.get("totalSelfUsePower")),
                # Économies solaires
                "solar_savings_kwh": solar_savings_kwh,
                "solar_savings_dh": solar_savings_dh,
                # Ratios
                "self_use_ratio": self._to_float(last.get("selfUsePowerRatioByProduct")),
                "grid_ratio": self._to_float(last.get("buyPowerRatio")),
                # Status
                "is_offline": is_offline,
                "station_status": station_status,
            }

            logger.info(
                f"📊 {plant_id} — PV: {result['pv_power']:.1f} kW | "
                f"Conso: {result['consumption_raw']:.1f} kW | "
                f"Offline: {is_offline} | Status: {station_status} | "
                f"Économies solaires: {result['solar_savings_dh']:.0f} DH"
            )
            logger.debug(f"🔍 Clés FusionSolar disponibles: {list(last.keys())}")

            return result

        except Exception as e:
            logger.error(f"Erreur get_realtime_data ({plant_id}): {e}")
            return {}

    def _extract_value(self, data) -> float:
        """Extraire la valeur numérique d'un champ temps réel FusionSolar"""
        if data is None:
            return 0.0
        if isinstance(data, dict):
            val = data.get("value")
            return float(val) if val is not None else 0.0
        if isinstance(data, (int, float)):
            return float(data)
        return 0.0

    def _to_float(self, data) -> float:
        """Convertir un champ en float"""
        if data is None:
            return 0.0
        if isinstance(data, dict):
            val = data.get("value", data)
            return float(val) if val is not None else 0.0
        try:
            return float(data)
        except (TypeError, ValueError):
            return 0.0


# Singleton
fusionsolar_service = FusionSolarService()
