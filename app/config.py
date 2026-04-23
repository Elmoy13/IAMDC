from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Supabase ─────────────────────────────────────────
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    # ── Database ─────────────────────────────────────────
    database_url: str

    # ── Meta / Facebook ──────────────────────────────────
    meta_verify_token: str
    meta_app_secret: str
    meta_app_id: str = ""
    meta_oauth_redirect_uri: str = "https://api.bacachitofeliz.org/api/v1/oauth/meta/callback"
    meta_oauth_scopes: str = (
        "pages_messaging,"
        "pages_manage_metadata,"
        "pages_show_list,"
        "instagram_manage_messages,"
        "business_management,"
        "public_profile"
    )

    # ── AI Provider toggle ───────────────────────────────
    ai_provider: str = "gemini"  # "gemini" | "bedrock"

    # ── Google Gemini ────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # ── AWS Bedrock (AI chat + template generation) ────────────────
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_session_token: str = ""
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    template_model_id: str = "amazon.nova-pro-v1:0"  # model used for HTML template generation

    # ── Agent-specific models (Brand Strategy Agent pipeline) ─────
    agent_vision_model: str = "us.amazon.nova-pro-v1:0"       # logo/product analysis
    agent_slide_model: str = "zai.glm-5"                      # per-slide text generation
    agent_director_model: str = "zai.glm-5"                   # creative director vision
    agent_fallback_chain: str = "zai.glm-5,zai.glm-4.7,us.amazon.nova-pro-v1:0"

    # ── Google Cloud / Vertex AI ─────────────────────────
    gcp_project_id: str = ""
    gcp_location: str = "us-central1"
    gcp_service_account_json: str = ""

    # ── fal.ai (Flux Kontext Pro) ────────────────────────
    fal_key: str = ""
    api_base_url: str = "http://localhost:8000"

    # ── Image Search (free APIs) ──────────────────────────
    unsplash_access_key: str = ""
    pexels_api_key: str = ""

    # ── Pinecone (futuro) ────────────────────────────────
    pinecone_api_key: str = ""
    pinecone_index: str = ""

    # ── Encryption ───────────────────────────────────────
    encryption_key: str = ""  # Fernet key (44-char base64). Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

    # ── App ──────────────────────────────────────────────
    log_level: str = "INFO"
    environment: str = "development"
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"


settings = Settings()  # type: ignore[call-arg]
