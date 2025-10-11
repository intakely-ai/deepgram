import json
import logging
import asyncio
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
import aiohttp

from app.core.config import config

logger = logging.getLogger(__name__)

class LLMService(ABC):
    """Abstract base class for LLM services"""
    
    @abstractmethod
    async def generate_response(self, 
                          prompt: str, 
                          history: List[Dict[str, str]], 
                          system_prompt: Optional[str] = None,
                          temperature: Optional[float] = None,
                          max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """
        Generate a response from the LLM based on prompt and conversation history
        
        Args:
            prompt: The current user input
            history: List of prior conversation turns [{"role": "user|assistant", "content": "..."}]
            system_prompt: Optional override for system instructions
            temperature: Optional temperature parameter (creativity)
            max_tokens: Optional max tokens for response
            
        Returns:
            Dict containing the LLM response and any additional metadata
        """
        pass


class OpenAIService(LLMService):
    """Implementation of LLMService using OpenAI's API"""
    
    def __init__(self):
        self.api_key = config.llm.LLM_API_KEY
        self.model = config.llm.LLM_MODEL_NAME
        self.default_temperature = config.llm.LLM_TEMPERATURE
        self.default_max_tokens = config.llm.LLM_MAX_TOKENS
        self.api_url = "https://api.openai.com/v1/chat/completions"
        
    async def generate_response(self, 
                          prompt: str, 
                          history: List[Dict[str, str]],
                          system_prompt: Optional[str] = None,
                          temperature: Optional[float] = None,
                          max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """Generate a response using OpenAI's Chat Completion API"""
        
        # Format messages for OpenAI
        messages = []
        
        # Add system prompt if provided
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            
        # Add conversation history
        messages.extend(history)
        
        # Add current user prompt
        messages.append({"role": "user", "content": prompt})
        
        # Prepare request payload
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.default_temperature,
            "max_tokens": max_tokens or self.default_max_tokens,
            "response_format": {"type": "json_object"}
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"OpenAI API error: {response.status} - {error_text}")
                        return {
                            "success": False,
                            "error": f"API error: {response.status}",
                            "raw_response": error_text
                        }
                    
                    data = await response.json()
                    content = data["choices"][0]["message"]["content"]
                    
                    # Try to parse JSON response
                    try:
                        parsed_content = json.loads(content)
                        return {
                            "success": True,
                            "raw_response": content,
                            "parsed_response": parsed_content
                        }
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse OpenAI response as JSON: {content}")
                        return {
                            "success": False,
                            "raw_response": content,
                            "error": "Failed to parse response as JSON"
                        }
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }


# Singleton instance
_llm_service = None

def get_llm_service() -> LLMService:
    """Get the LLM service instance"""
    global _llm_service
    if _llm_service is None:
        _llm_service = OpenAIService()
    return _llm_service