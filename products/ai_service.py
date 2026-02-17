"""
AI Service for generating product descriptions and embeddings.
Handles vision model processing, text generation, and vector embeddings.
Uses LangChain + Ollama for local embeddings (nomic-embed-text model).
"""
import os
import base64
import json
import logging
from pathlib import Path
from typing import List, Dict, Any

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)


class AIService:
    """
    Orchestrates AI operations for product documents and embeddings.
    Uses LangChain + Ollama for local embeddings (nomic-embed-text).
    """
    
    def __init__(self):
        groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.ollama_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
        self.embedding_model = "nomic-embed-text"
        self.embedding_dim = 768
        
        # --- Groq client (vision) ---
        self.groq_client = None
        if groq_api_key:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=groq_api_key)
                logger.info("Groq client initialized for vision processing")
            except Exception as e:
                logger.error(f"Failed to initialize Groq client: {e}")
        else:
            logger.warning("GROQ_API_KEY not set - vision processing will be skipped")
        
        # --- Ollama embeddings (LangChain) ---
        self.embeddings = None
        try:
            from langchain_ollama import OllamaEmbeddings
            self.embeddings = OllamaEmbeddings(
                model=self.embedding_model,
                base_url=self.ollama_url,
            )
            logger.info(f"LangChain OllamaEmbeddings initialized - {self.embedding_model}")
            self._pull_model_if_needed()
        except Exception as e:
            logger.error(f"Failed to initialize OllamaEmbeddings: {e}")
    
    # ------------------------------------------------------------------
    # Ollama helpers
    # ------------------------------------------------------------------
    
    def _pull_model_if_needed(self):
        """Auto-pull nomic-embed-text model if not already available."""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                
                if not any(self.embedding_model in name for name in model_names):
                    logger.info(f"Pulling model {self.embedding_model}...")
                    pull_resp = requests.post(
                        f"{self.ollama_url}/api/pull",
                        json={"name": self.embedding_model},
                        timeout=300,
                    )
                    if pull_resp.status_code == 200:
                        logger.info(f"Successfully pulled {self.embedding_model}")
                    else:
                        logger.warning(f"Failed to pull model: {pull_resp.text}")
                else:
                    logger.info(f"Model {self.embedding_model} already available")
        except Exception as e:
            logger.warning(f"Could not verify/pull model: {e}")
    
    def _check_ollama_connection(self) -> bool:
        """Check if Ollama API is accessible."""
        try:
            resp = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Ollama connection failed: {e}")
            return False
    
    # ------------------------------------------------------------------
    # Vision processing
    # ------------------------------------------------------------------
    
    def process_product_images(self, product_images: List) -> str:
        """
        Process product images with vision model.
        Returns combined description or a fallback message.
        
        Gracefully handles:
        - Missing Groq API key
        - Missing image files on disk
        - API errors
        """
        if not product_images:
            return "No product images available for analysis."
        
        if not self.groq_client:
            logger.warning("Groq client not available - skipping vision processing")
            return "Vision analysis unavailable (Groq API key not configured)."
        
        vision_descriptions = []
        
        for idx, image in enumerate(product_images[:3]):
            try:
                # Check that the physical file actually exists
                image_path = image.image.path
                if not os.path.isfile(image_path):
                    logger.warning(f"Image file not found on disk: {image_path}")
                    vision_descriptions.append(
                        f"Image {idx+1}: [file missing - {image.alt_text or 'no alt text'}]"
                    )
                    continue
                
                description = self._process_single_image(image_path)
                vision_descriptions.append(f"Image {idx+1}: {description}")
            except Exception as e:
                logger.error(f"Error processing image {idx}: {e}")
                vision_descriptions.append(f"Image {idx+1}: [processing error]")
        
        return "\n".join(vision_descriptions) if vision_descriptions else "Unable to process product images."
    
    def _process_single_image(self, image_path: str) -> str:
        """
        Process a single image via Groq vision API.
        """
        with open(image_path, 'rb') as f:
            image_data = base64.standard_b64encode(f.read()).decode('utf-8')
        
        extension = Path(image_path).suffix.lower()
        media_types = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp',
        }
        media_type = media_types.get(extension, 'image/jpeg')
        
        prompt = (
            "Analyze this product image. Provide a SHORT description (less than 10 lines) including:\n"
            "- What product type is this? (e.g., smartphone, laptop)\n"
            "- Visible specs or features (color, size, material, unique features)\n"
            "- Design tier (budget/mid-range/premium)\n"
            "Be concise and factual. Only describe what's visible."
        )
        
        completion = self.groq_client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{image_data}"},
                        },
                    ],
                }
            ],
            temperature=0.3,
            max_completion_tokens=200,
            top_p=0.9,
        )
        
        return completion.choices[0].message.content
    
    # ------------------------------------------------------------------
    # Embedding generation
    # ------------------------------------------------------------------
    
    def generate_embedding(self, text_content: str) -> List[float]:
        """
        Generate 768-dim vector embedding via LangChain + Ollama (nomic-embed-text).
        Returns a zero-vector as fallback on any error.
        """
        try:
            if not self.embeddings:
                logger.error("OllamaEmbeddings not initialized - returning zero vector")
                return [0.0] * self.embedding_dim
            
            embedding = self.embeddings.embed_query(text_content)
            
            if embedding and len(embedding) == self.embedding_dim:
                logger.info(f"Generated {len(embedding)}-dim embedding via LangChain+Ollama")
                return embedding
            else:
                logger.error(
                    f"Invalid embedding dimensions: expected {self.embedding_dim}, "
                    f"got {len(embedding) if embedding else 0}"
                )
                return [0.0] * self.embedding_dim
        
        except requests.exceptions.Timeout:
            logger.error("Ollama API timeout - ensure Ollama server is running")
            return [0.0] * self.embedding_dim
        except requests.exceptions.ConnectionError:
            logger.error(f"Cannot connect to Ollama at {self.ollama_url}")
            return [0.0] * self.embedding_dim
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return [0.0] * self.embedding_dim
    
    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    
    def get_embedding_metadata(self, product) -> Dict[str, Any]:
        """Extract metadata for embedding record."""
        return {
            'product_id': str(product.id),
            'product_title': product.title,
            'brand': product.brand or 'Unknown',
            'category': product.category.name,
            'price': float(product.price),
            'currency': product.currency,
            'rating': product.rating_avg,
            'rating_count': product.rating_count,
            'in_stock': product.stock_quantity > 0,
            'image_count': product.images.count(),
            'attribute_count': product.attributes.count(),
            'embedding_model': self.embedding_model,
            'embedding_dimension': self.embedding_dim,
            'embedding_source': 'ollama_local',
            'ollama_url': self.ollama_url,
            'generated_at': str(timezone.now()),
        }
