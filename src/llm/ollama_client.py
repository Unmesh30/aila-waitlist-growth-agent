"""
Ollama client - local LLM interface.

Connects to local Ollama instance for reply generation.
"""

import requests
from typing import Dict, Any, Optional

from ..utils.logger import get_logger
from config.settings import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT

logger = get_logger(__name__)


class OllamaClient:
    """Client for interacting with local Ollama instance."""

    def __init__(self, host: str = None, model: str = None):
        """
        Initialize Ollama client.

        Args:
            host: Ollama host URL (default from settings)
            model: Model name (default from settings)
        """
        self.host = host or OLLAMA_HOST
        self.model = model or OLLAMA_MODEL
        self.generate_url = f"{self.host}/api/generate"

        logger.info(f"Ollama client initialized: {self.host} (model: {self.model})")

    def check_connection(self) -> bool:
        """
        Check if Ollama is running and accessible.

        Returns:
            True if connected, False otherwise
        """
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code == 200:
                logger.info("Ollama connection successful")
                return True
            else:
                logger.error(f"Ollama returned status {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Cannot connect to Ollama at {self.host}: {e}")
            return False

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 300,
    ) -> Optional[str]:
        """
        Generate text using Ollama.

        Args:
            prompt: User prompt
            system: Optional system message
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text or None on error
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }

        if system:
            payload["system"] = system

        try:
            logger.debug(f"Generating with Ollama (temp={temperature}, max_tokens={max_tokens})")

            response = requests.post(
                self.generate_url,
                json=payload,
                timeout=OLLAMA_TIMEOUT,
            )

            response.raise_for_status()

            data = response.json()
            generated_text = data.get("response", "").strip()

            logger.debug(f"Generated {len(generated_text)} characters")

            return generated_text

        except requests.exceptions.Timeout:
            logger.error(f"Ollama request timed out after {OLLAMA_TIMEOUT}s")
            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama request failed: {e}")
            return None

        except Exception as e:
            logger.error(f"Unexpected error during generation: {e}")
            return None


def test_ollama_connection() -> bool:
    """
    Test Ollama connection and model availability.

    Returns:
        True if Ollama is ready, False otherwise
    """
    logger.info("Testing Ollama connection...")

    client = OllamaClient()

    if not client.check_connection():
        logger.error("Ollama is not running or not accessible")
        logger.error(f"Make sure Ollama is running at {OLLAMA_HOST}")
        logger.error(f"Run: ollama serve")
        return False

    # Try a simple generation
    test_response = client.generate(
        prompt="Say 'OK' if you can read this.",
        temperature=0.1,
        max_tokens=10,
    )

    if test_response:
        logger.info(f"Ollama test successful: {test_response}")
        return True
    else:
        logger.error("Ollama test failed - could not generate response")
        logger.error(f"Make sure model '{OLLAMA_MODEL}' is installed")
        logger.error(f"Run: ollama pull {OLLAMA_MODEL}")
        return False
