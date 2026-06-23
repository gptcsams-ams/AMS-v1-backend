import asyncio
from app.core.config import settings
from app.providers.base import DispatchResult


class TwilioProvider:
    def _get_client(self):
        try:
            from twilio.rest import Client
            return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        except ImportError:
            return None

    async def send_whatsapp(self, to: str, body: str) -> DispatchResult:
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
            return DispatchResult(success=False, error_message="Twilio not configured")

        client = self._get_client()
        if not client:
            return DispatchResult(success=False, error_message="twilio package not installed")

        try:
            from twilio.base.exceptions import TwilioRestException
            # Twilio SDK is sync; run in executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            message = await loop.run_in_executor(
                None,
                lambda: client.messages.create(
                    from_=f"whatsapp:{settings.TWILIO_WHATSAPP_FROM}",
                    to=f"whatsapp:{to}",
                    body=body,
                ),
            )
            return DispatchResult(success=True, provider_message_id=message.sid)
        except Exception as exc:
            return DispatchResult(success=False, error_message=str(exc))

    async def send_sms(self, to: str, body: str) -> DispatchResult:
        return DispatchResult(success=False, error_message="Use MSG91 for SMS")

    async def send_email(self, to: str, subject: str, body: str) -> DispatchResult:
        return DispatchResult(success=False, error_message="Twilio does not support Email")
