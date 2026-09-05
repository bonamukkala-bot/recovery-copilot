from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    supabase_url: str = ""
    supabase_key: str = ""

    groq_api_key: str = ""

    recovery_admin_api_key: str = ""

    contact_cooldown_minutes: int = 20
    promise_window_hours: int = 24
    max_voice_calls_per_session: int = 20

    environment: str = "development"
    dispatch_mode: str = "mock"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()