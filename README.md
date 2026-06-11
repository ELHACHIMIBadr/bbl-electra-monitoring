# BBL-ELECTRA Monitoring 🌞

Système de monitoring solaire et alertes pour ferme agricole.

## Stack

- **Backend**: Python + FastAPI
- **Base de données**: SQLite (dev) / PostgreSQL (prod)
- **Collecte**: FusionSolarPy + APScheduler (toutes les 5 min)
- **Notifications**: Telegram + Email
- **Frontend**: PWA (à venir)

## Installation

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Configuration

Copier `.env.example` vers `.env` et remplir les credentials.

## Lancer

```bash
uvicorn app.main:app --reload
```

API disponible sur `http://localhost:8000`
Documentation Swagger sur `http://localhost:8000/docs`

## Règles d'alertes

| Règle | Créneau | Seuil |
|---|---|---|
| Conso HP | 18h-23h (été) | > 150 kW |
| Conso nocturne (arrosage) | 00h-04h | > 180 kW |
| Conso nocturne (calme) | 04h-07h | > 150 kW |
| Import réseau (plein soleil) | 10h-16h | Conso > PV + 50 kW |
| Import réseau (fin journée) | 16h-18h | Conso > PV + 80 kW |
