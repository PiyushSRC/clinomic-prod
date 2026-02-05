import hashlib
from pathlib import Path
from app.ml.engine import engine

MODEL_HASHES = {
    "stage1.pkl": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", # Empty hash placeholder
}

def verify_model_integrity(model_path: Path) -> bool:
    if not model_path.exists():
        return False
    
    # Calculate SHA256
    sha256_hash = hashlib.sha256()
    with open(model_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
            
    expected = MODEL_HASHES.get(model_path.name)
    return sha256_hash.hexdigest() == expected

def init_ml():
    """
    Called by lifespan manager.
    """
    engine.load_models()
    # If using verify:
    # if not verify_model_integrity(...): raise StartupError
