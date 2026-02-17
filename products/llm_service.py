from groq import Groq
import os
from dotenv import load_dotenv
import base64
from pathlib import Path

load_dotenv()

def get_image_base64(image_path):
    """
    Convert image file to base64 string.
    
    Args:
        image_path: Path to image file (e.g., '/path/to/image.jpg')
        
    Returns:
        base64 encoded string
    """
    with open(image_path, 'rb') as image_file:
        return base64.standard_b64encode(image_file.read()).decode('utf-8')

def get_image_media_type(image_path):
    """
    Determine media type from file extension.
    
    Args:
        image_path: Path to image file
        
    Returns:
        Media type string (e.g., 'image/jpeg')
    """
    extension = Path(image_path).suffix.lower()
    media_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp'
    }
    return media_types.get(extension, 'image/jpeg')

def text_about_image(image_path=None):
    """
    Generate description of an image using Groq vision API.
    
    Args:
        image_path: Local path to image file (e.g., 'media/products/2026/01/iqoo_neo9.jpg')
                   If None, uses default test image
    
    Returns:
        Text description of the image
    """
    if image_path is None:
        # Default test image path (relative to manage.py)
        image_path = '../media/products/2026/01/iqoo_neo9.jpg'
    
    # Ensure path exists
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    # Convert to base64
    image_data = get_image_base64(image_path)
    media_type = get_image_media_type(image_path)
    
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    completion = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Describe the image in detail for use in an e-commerce AI system. "
                            "Mention visible objects, materials, colors, and any distinguishing features. "
                            "Be factual and concise."
                        )
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_data}"
                        }
                    }
                ]
            }
        ],
        temperature=1,
        max_completion_tokens=1024,
        top_p=1,
        stream=False,
        stop=None,
    )

    return completion.choices[0].message


if __name__ == "__main__":
    try:
        response = text_about_image()
        print("Image Description:")
        print(response.content)
    except FileNotFoundError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Error: {e}")