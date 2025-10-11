import os
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class LLMConfig(BaseModel):
    """Configuration settings for LLM service"""
    LLM_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "gpt-4o")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "500"))

class AppConfig(BaseModel):
    """Application configuration settings"""
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # LLM configuration
    llm: LLMConfig = LLMConfig()
    
    # Existing configuration from .env
    DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE: str = os.getenv("SUPABASE_SERVICE_ROLE", "")
    BUSINESS_TZ: str = os.getenv("BUSINESS_TZ", "America/Los_Angeles")
    
    # Health check settings
    HEALTH_CHECK_ENABLED: bool = True
    
# Create a global config instance
config = AppConfig()