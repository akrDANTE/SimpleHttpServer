import os
import hashlib

import torch
import torch.nn.functional as F

from PIL import Image

from transformers import AutoProcessor, AutoModel

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct
)

# =====================================================
# CONFIG
# =====================================================

WIREFRAME_DIR = "./wireframes"
QDRANT_PATH = "./qdrant_db"
COLLECTION_NAME = "ux_wireframes_siglip"
MODEL_NAME = "google/siglip-base-patch16-224"
EMBEDDING_SIZE = 768
BATCH_SIZE = 16

# =====================================================
# DEVICE
# =====================================================

DEVICE = torch.device("cpu")

# =====================================================
# MODEL LOADING
# =====================================================

print(f"Loading {MODEL_NAME}...")

processor = AutoProcessor.from_pretrained(MODEL_NAME)
model = AutoModel.from_pretrained(MODEL_NAME)

model.eval()
model.to(DEVICE)

# =====================================================
# QDRANT
# =====================================================

client = QdrantClient(path=QDRANT_PATH)

collections = {c.name for c in client.get_collections().collections}

if COLLECTION_NAME not in collections:
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=EMBEDDING_SIZE,
            distance=Distance.COSINE
        )
    )

# =====================================================
# HELPERS
# =====================================================

def generate_id(path: str) -> int:
    return int(hashlib.md5(path.encode("utf-8")).hexdigest()[:15], 16)

def embed_batch(image_paths):
    images = [Image.open(path).convert("RGB") for path in image_paths]

    inputs = processor(
        images=images,
        return_tensors="pt"
    )

    inputs = {k: v.to(DEVICE) for k, v in inputs.items()}

    with torch.no_grad():
        embeddings = model.get_image_features(pixel_values=inputs["pixel_values"])

    embeddings = F.normalize(embeddings, p=2, dim=1)
    return embeddings.cpu().tolist()

# =====================================================
# INDEX & SEARCH
# =====================================================

def index_wireframes():
    image_paths = []
    for root, _, files in os.walk(WIREFRAME_DIR):
        for file in files:
            if file.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")):
                image_paths.append(os.path.join(root, file))

    print(f"Found {len(image_paths)} images")

    for start in range(0, len(image_paths), BATCH_SIZE):
        batch_paths = image_paths[start:start + BATCH_SIZE]
        vectors = embed_batch(batch_paths)
        points = []

        for path, vector in zip(batch_paths, vectors):
            points.append(
                PointStruct(
                    id=generate_id(path),
                    vector=vector,
                    payload={"filename": os.path.basename(path), "path": path}
                )
            )

        client.upsert(collection_name=COLLECTION_NAME, points=points)
        print(f"Indexed {min(start+BATCH_SIZE, len(image_paths))}/{len(image_paths)}")

    print("Done.")

def search(screenshot_path, top_k=5):
    vector = embed_batch([screenshot_path])[0]
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=top_k
    ).points
    return results

if __name__ == "__main__":
    index_wireframes()
    results = search("./query.png", top_k=5)
    for r in results:
        print(r.score, r.payload["filename"])
