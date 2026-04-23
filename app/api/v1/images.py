from fastapi import APIRouter, Depends

from app.middleware.auth import get_current_user
from app.schemas.image import GenerateImageRequest, GenerateImageResponse
from app.services import image_service

router = APIRouter(prefix="/images", tags=["images"])


@router.post("/generate", response_model=GenerateImageResponse)
async def generate_image(
    payload: GenerateImageRequest,
    _user: dict = Depends(get_current_user),
) -> GenerateImageResponse:
    """Generate an image with Vertex AI Imagen 3 and composite the user's logo."""
    data_url = await image_service.generate_image_with_logo(
        prompt=payload.prompt,
        context_image_b64=payload.context_image,
    )
    return GenerateImageResponse(image_data_url=data_url)
