import httpx
from app.core.config import settings
from app.providers.base import DispatchResult


class SendGridProvider:
    BASE_URL = "https://api.sendgrid.com/v3"

    async def send_email(self, to: str, subject: str, body: str) -> DispatchResult:
        from_email = getattr(settings, "SENDGRID_FROM_EMAIL", None) or settings.EMAIL_FROM
        if not settings.SENDGRID_API_KEY or not from_email:
            return DispatchResult(success=False, error_message="SendGrid not configured")

        html = (
            '<html><body style="font-family:Arial,sans-serif;">'
            + body.replace("\n", "<br>")
            + "</body></html>"
        )
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.post(
                    f"{self.BASE_URL}/mail/send",
                    headers={"Authorization": f"Bearer {settings.SENDGRID_API_KEY}"},
                    json={
                        "personalizations": [{"to": [{"email": to}]}],
                        "from":    {"email": from_email},
                        "subject": subject,
                        "content": [{"type": "text/html", "value": html}],
                        "tracking_settings": {
                            "open_tracking":  {"enable": True},
                            "click_tracking": {"enable": False},
                        },
                    },
                )
                msg_id = resp.headers.get("X-Message-Id")
                if resp.status_code == 202:
                    return DispatchResult(success=True, provider_message_id=msg_id)
                return DispatchResult(
                    success=False,
                    error_message=resp.text[:300],
                )
            except Exception as exc:
                return DispatchResult(success=False, error_message=str(exc))

    async def send_sms(self, to: str, body: str) -> DispatchResult:
        return DispatchResult(success=False, error_message="SendGrid does not support SMS")

    async def send_whatsapp(self, to: str, body: str) -> DispatchResult:
        return DispatchResult(success=False, error_message="SendGrid does not support WhatsApp")
