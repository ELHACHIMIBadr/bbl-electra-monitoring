"""
Notifications - Push PWA + Email
"""
import smtplib
import json
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings
from app.database import SessionLocal
import logging

logger = logging.getLogger(__name__)


def send_alert(message: str, telegram: bool = False, email: bool = True):
    """Envoyer une alerte via Push + Email"""
    # Push PWA
    send_push(message)

    # Email
    if email:
        send_email("🚨 Alerte BBL-ELECTRA Monitoring", message)


# ============================================================
# PUSH PWA
# ============================================================
def send_push(message: str):
    """Envoyer notification push à tous les abonnés"""
    try:
        from pywebpush import webpush, WebPushException
        from app.models.models import PushSubscription

        vapid_private = settings.VAPID_PRIVATE_KEY
        vapid_email = settings.VAPID_EMAIL

        if not vapid_private:
            return 0

        db = SessionLocal()
        try:
            subs = db.query(PushSubscription).filter(PushSubscription.is_active == True).all()
            if not subs:
                return 0

            # Nettoyer le message HTML pour le push
            clean_msg = message.replace("<b>", "").replace("</b>", "")
            # Extraire le titre (première ligne)
            lines = clean_msg.strip().split("\n")
            title = lines[0][:80] if lines else "BBL-ELECTRA"
            body = "\n".join(lines[1:4]) if len(lines) > 1 else message[:200]

            payload = json.dumps({"title": title, "body": body, "url": "/"})

            sent = 0
            for sub in subs:
                try:
                    sub_info = json.loads(sub.subscription_json)
                    webpush(
                        subscription_info=sub_info,
                        data=payload,
                        vapid_private_key=vapid_private,
                        vapid_claims={"sub": f"mailto:{vapid_email}"}
                    )
                    sent += 1
                except WebPushException as e:
                    if hasattr(e, 'response') and e.response and e.response.status_code in (404, 410):
                        sub.is_active = False
                except Exception:
                    pass

            db.commit()
            if sent:
                logger.info(f"📱 Push envoyé à {sent} abonnés")
            return sent
        finally:
            db.close()
    except ImportError:
        logger.warning("⚠️ pywebpush non installé")
        return 0
    except Exception as e:
        logger.error(f"❌ Push error: {e}")
        return 0


# ============================================================
# EMAIL
# ============================================================
def send_email(subject: str, body: str):
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        return False

    recipients = [r.strip() for r in settings.EMAIL_RECIPIENTS if r.strip()]
    if not recipients:
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = settings.SMTP_USER
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject

        html_body = f"""
        <html>
        <body style="font-family: 'Segoe UI', Arial, sans-serif; padding: 20px; background: #f5f5f5;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
                <div style="background: linear-gradient(135deg, #e8860c, #f59e0b); padding: 20px 24px;">
                    <h2 style="color: white; margin: 0; font-size: 18px;">⚡ BBL-ELECTRA Monitoring</h2>
                    <p style="color: rgba(255,255,255,0.85); margin: 4px 0 0; font-size: 13px;">FERME OUM AZZA-BBL</p>
                </div>
                <div style="padding: 24px;">
                    <pre style="margin: 0; white-space: pre-wrap; font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333;">{body}</pre>
                </div>
                <div style="padding: 16px 24px; background: #f9fafb; text-align: center;">
                    <p style="color: #999; font-size: 11px; margin: 0;">Message automatique — BBL-ELECTRA Monitoring v1.0</p>
                </div>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"✅ Email envoyé à {', '.join(recipients)}")
        return True

    except Exception as e:
        logger.error(f"❌ Email exception: {e}")
        return False


# ============================================================
# BILAN JOURNALIER
# ============================================================
def send_daily_report(report: dict):
    message = f"""📊 <b>Bilan du {report['date']}</b>
━━━━━━━━━━━━━━━━━━━━━━━━
⚡ Production PV :      {report['total_pv']:.0f} kWh
🏭 Conso estimée :      {report['total_consumption']:.0f} kWh
📥 Import réseau :       {report['total_import']:.0f} kWh
📤 Export réseau :       {report['total_export']:.0f} kWh
━━━━━━━━━━━━━━━━━━━━━━━━
💰 Coût réseau :         {report['total_cost']:.0f} DH
☀️ Économisé PV :        {report['total_savings']:.0f} DH
⚠️ Alertes :             {report['alert_count']}"""

    send_alert(message, email=True)
