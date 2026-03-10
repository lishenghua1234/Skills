import os
from google import genai
from google.genai import types

def test_generation():
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    # List of possible models to test
    models_to_test = [
        'gemini-3.1-flash-image-preview',
        'nano-banana-pro-preview',
        'gemini-2.0-flash-exp-image-generation'
    ]
    
    for model_name in models_to_test:
        print(f"Testing model: {model_name}")
        try:
            response = client.models.generate_images(
                model=model_name,
                prompt="A cute cat on a spaceship",
                config=types.GenerateImagesConfig(number_of_images=1)
            )
            print(f"SUCCESS with {model_name}")
            return
        except Exception as e:
            print(f"FAILED with {model_name}: {e}")

if __name__ == "__main__":
    test_generation()
