from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DispatchResult:
    success:             bool
    provider_message_id: str | None = None
    error_message:       str | None = None


class BaseNotificationProvider(ABC):
    @abstractmethod
    async def send_sms(self, to: str, body: str) -> DispatchResult: ...

    @abstractmethod
    async def send_whatsapp(self, to: str, body: str) -> DispatchResult: ...

    @abstractmethod
    async def send_email(self, to: str, subject: str, body: str) -> DispatchResult: ...
