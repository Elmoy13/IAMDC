from fastapi import HTTPException, status


class ChannelNotFoundError(HTTPException):
    def __init__(self, detail: str = "Channel not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class ConversationNotFoundError(HTTPException):
    def __init__(self, detail: str = "Conversation not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class ContactNotFoundError(HTTPException):
    def __init__(self, detail: str = "Contact not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class MetaSendError(HTTPException):
    def __init__(self, detail: str = "Failed to send message via Meta Graph API"):
        super().__init__(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)


class AIProviderError(HTTPException):
    def __init__(self, detail: str = "AI provider returned an error"):
        super().__init__(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)


class ImageGenerationError(HTTPException):
    def __init__(self, detail: str = "Image generation failed"):
        super().__init__(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)


class WebhookVerificationError(HTTPException):
    def __init__(self, detail: str = "Webhook verification failed"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
