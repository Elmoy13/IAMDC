from fastapi import APIRouter

from app.api.v1 import agency, brand, brand_agent, brands_crud, chat, conversations, drafts, images, messages, posts, product, temp_files, webhook

router = APIRouter(prefix="/api/v1")

router.include_router(webhook.router)
router.include_router(messages.router)
router.include_router(images.router)
router.include_router(conversations.router)
router.include_router(brand_agent.router)
router.include_router(brand.router)
router.include_router(product.router)
router.include_router(chat.router)
router.include_router(posts.posts_router)
router.include_router(posts.templates_router)
router.include_router(temp_files.router)
router.include_router(brands_crud.router)
router.include_router(agency.router)
router.include_router(drafts.router)
