from pydantic import BaseModel


class GenerateImageRequest(BaseModel):
    prompt: str
    context_image: str  # base64-encoded PNG (logo with transparency)


class GenerateImageResponse(BaseModel):
    image_data_url: str  # data:image/png;base64,...
