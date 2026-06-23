class NotificationError(Exception):
    pass


class TemplateNotFoundError(NotificationError):
    def __init__(self, trigger: str, channel: str):
        super().__init__(f"No active template for {trigger}/{channel}")
        self.trigger = trigger
        self.channel = channel


class NotificationRuleDisabledError(NotificationError):
    def __init__(self, trigger: str, channel: str):
        super().__init__(f"Notification rule disabled for {trigger}/{channel}")


class NotificationOutsideWindowError(NotificationError):
    def __init__(self, trigger: str, channel: str):
        super().__init__(f"Outside allowed send window for {trigger}/{channel}")


class RecipientNotFoundError(NotificationError):
    def __init__(self, channel: str):
        super().__init__(f"No usable contact for channel {channel}")


class ProviderDispatchError(NotificationError):
    pass
