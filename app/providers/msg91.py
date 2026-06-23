import httpx
from app.core.config import settings
from app.providers.base import DispatchResult


class MSG91Provider:
    BASE_URL = "https://api.msg91.com/api/v5"

    async def send_sms(self, to: str, body: str) -> DispatchResult:
        if not settings.MSG91_API_KEY or not settings.MSG91_SENDER_ID:
            return DispatchResult(success=False, error_message="MSG91 not configured")

        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.post(
                    f"{self.BASE_URL}/flow/",
                    headers={
                        "authkey": settings.MSG91_API_KEY,
                        "Content-Type": "application/json",
                    },
                    json={
                        "flow_id": getattr(settings, "MSG91_FLOW_ID", ""),
                        "sender":  settings.MSG91_SENDER_ID,
                        "mobiles": to.replace("+", ""),  # MSG91 format: no leading +
                        "VAR1":    body,
                    },
                )
                data = resp.json()
                if resp.status_code == 200 and data.get("type") == "success":
                    return DispatchResult(
                        success=True,
                        provider_message_id=data.get("request_id"),
                    )
                return DispatchResult(
                    success=False,
                    error_message=data.get("message", "MSG91 error"),
                )
            except Exception as exc:
                return DispatchResult(success=False, error_message=str(exc))

    async def send_whatsapp(self, to: str, body: str) -> DispatchResult:
        return DispatchResult(success=False, error_message="MSG91 does not support WhatsApp")

    async def send_email(self, to: str, subject: str, body: str) -> DispatchResult:
        return DispatchResult(success=False, error_message="MSG91 does not support Email")
