"""
Push Notifications - Service d'envoi via Web Push API
"""
from pywebpush import webpush, WebPushException
from sqlalchemy.orm import Session
from app.models.models import PushSubscription
from app.config import settings
import json
import logging

logger = logging.getLogger(__name__)


def send_push_notification(db: Session, title: str, body: str, url: str = "/"):
    """Envoyer une notification push à tous les abonnés"""
    subscriptions = db.query(PushSubscription).filter(PushSubscription.is_active == True).all()

    if not subscriptions:
        logger.info("📱 Aucun abonné push")
        return 0

    vapid_private = settings.VAPID_PRIVATE_KEY
    vapid_email = settings.VAPID_EMAIL

    if not vapid_private or not vapid_email:
        logger.warning("⚠️ VAPID keys non configurées — push désactivé")
        return 0

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "tag": "bbl-alert"
    })

    sent = 0
    for sub in subscriptions:
        try:
            subscription_info = json.loads(sub.subscription_json)
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=vapid_private,
                vapid_claims={"sub": f"mailto:{vapid_email}"}
            )
            sent += 1
        except WebPushException as e:
            logger.error(f"❌ Push failed for {sub.id}: {e}")
            if e.response and e.response.status_code in (404, 410):
                sub.is_active = False
                db.commit()
        except Exception as e:
            logger.error(f"❌ Push error: {e}")

    logger.info(f"📱 Push envoyé à {sent}/{len(subscriptions)} abonnés")
    return sent
