import easyocr
import torch
from PIL import Image
from sentence_transformers import SentenceTransformer

# Initialize the model globally to avoid reloading on every function call
# EasyOCR supports passing multiple languages in a list
# 'en' = English, 'es' = Spanish, 'hi' = Hindi
print("Initializing OCR Reader (English, Spanish, Hindi)...")
ocr_reader = easyocr.Reader(['en', 'es', 'hi'], gpu=False)

print("Loading Lightweight Multilingual Embedding Model...")
embedding_model = SentenceTransformer('intfloat/multilingual-e5-small', device='cpu')


def extract_and_embed_text(image_path: str):
    """
    Extracts text from a UI screenshot or wireframe (handling multilingual scripts)
    and generates a single semantic embedding vector.
    """
    # 1. Perform OCR
    # detail=0 returns just the text strings, discarding spatial bounding boxes
    raw_results = ocr_reader.readtext(image_path, detail=0)
    
    # Clean up empty spaces and join text into a coherent string
    cleaned_text = " ".join([text.strip() for text in raw_results if text.strip()])
    
    if not cleaned_text:
        # Fallback if the screen contains no readable text elements
        cleaned_text = "empty screen"
        
    # 2. Format for E5 Model
    # The E5 model family requires queries/documents to be prefixed with a task instruction
    formatted_text = f"query: {cleaned_text}"
    
    # 3. Generate the Embedding Vector
    with torch.no_grad():
        embedding = embedding_model.encode(
            formatted_text, 
            normalize_embeddings=True
        )
        
    # Returns a list of floats ready to be stored or queried in Qdrant
    return cleaned_text, embedding.tolist()


# =====================================================
# EXAMPLE USAGE
# =====================================================
if __name__ == "__main__":
    # Example 1: An English Wireframe
    ux_text, ux_vector = extract_and_embed_text("./wireframes/login_wireframe_en.png")
    print(f"\n--- UX Wireframe Text ---\n{ux_text}")
    
    # Example 2: A Hindi Screenshot of the implemented app
    ui_text, ui_vector = extract_and_embed_text("./screenshots/login_app_hi.png")
    print(f"\n--- UI App Screenshot Text ---\n{ui_text}")
    
    # Calculate Cosine Similarity on CPU
    import numpy as np
    similarity = np.dot(ux_vector, ui_vector)
    print(f"\nCross-Lingual Semantic Match Score: {similarity:.4f}")
