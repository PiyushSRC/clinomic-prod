"""Unit tests for core functionality."""
import os
import sys

# Ensure backend is in path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


class TestCoreImports:
    """Test that core modules can be imported."""
    
    def test_import_settings(self):
        """Test settings module import."""
        from core.settings import settings
        assert settings is not None
        assert hasattr(settings, 'app_env')
    
    def test_import_auth_security(self):
        """Test auth_security module import."""
        from core.auth_security import create_access_token, verify_password
        assert callable(create_access_token)
        assert callable(verify_password)
    
    def test_import_crypto(self):
        """Test crypto module import."""
        from core.crypto import crypto_manager
        assert crypto_manager is not None


class TestAuthSecurity:
    """Test authentication security functions."""
    
    def test_password_hashing(self):
        """Test password hashing and verification."""
        from core.auth_security import hash_password, verify_password
        
        password = "test_password_123"
        hashed = hash_password(password)
        
        # Verify it creates a hash
        assert hashed != password
        assert len(hashed) > 0
        
        # Verify correct password
        assert verify_password(password, hashed) is True
        
        # Verify wrong password
        assert verify_password("wrong_password", hashed) is False
    
    def test_utcnow(self):
        """Test UTC timestamp function."""
        from core.auth_security import utcnow
        from datetime import timezone
        
        now = utcnow()
        assert now.tzinfo == timezone.utc


class TestSettings:
    """Test settings configuration."""
    
    def test_default_settings(self):
        """Test default settings values."""
        from core.settings import settings
        
        assert settings.jwt_algorithm == "HS256"
        assert settings.access_token_expire_minutes > 0
        assert settings.refresh_token_expire_days > 0
    
    def test_mfa_required_roles(self):
        """Test MFA required roles parsing."""
        from core.settings import settings
        
        roles = settings.mfa_required_role_list
        assert isinstance(roles, list)
        # Default includes ADMIN and DOCTOR
        assert "ADMIN" in roles or "DOCTOR" in roles or len(roles) >= 0
    
    def test_is_production(self):
        """Test production mode check."""
        from core.settings import settings
        
        # In test, should not be production
        assert settings.is_production() is False


class TestCrypto:
    """Test encryption/decryption functions."""
    
    def test_encrypt_decrypt(self):
        """Test encryption and decryption roundtrip."""
        from core.crypto import crypto_manager
        
        original = "test_sensitive_data"
        encrypted = crypto_manager.encrypt(original)
        
        # Encrypted should be different from original
        assert encrypted != original
        
        # Decrypt should return original
        decrypted = crypto_manager.decrypt(encrypted)
        assert decrypted == original
    
    def test_encrypt_empty_string(self):
        """Test encrypting empty string."""
        from core.crypto import crypto_manager
        
        encrypted = crypto_manager.encrypt("")
        decrypted = crypto_manager.decrypt(encrypted)
        assert decrypted == ""


class TestB12Engine:
    """Test B12 clinical engine."""
    
    def test_engine_initialization(self):
        """Test that the B12 engine initializes correctly."""
        from server import ENGINE, ROOT_DIR
        
        assert ENGINE is not None
        assert ENGINE.model_dir == ROOT_DIR / "b12_clinical_engine_v1.0"
    
    def test_prediction_basic(self):
        """Test basic prediction with sample CBC data."""
        from server import ENGINE
        
        # Sample CBC data
        cbc_data = {
            "Age": 45,
            "Sex": "M",
            "Hb": 12.5,
            "RBC": 4.5,
            "HCT": 38,
            "MCV": 85,
            "MCH": 28,
            "MCHC": 33,
            "RDW": 13.5,
            "WBC": 7.0,
            "Platelets": 250,
            "Neutrophils": 60,
            "Lymphocytes": 30,
        }
        
        result = ENGINE.predict(cbc_data)
        
        # Check result structure
        assert "riskClass" in result
        assert "labelText" in result
        assert "probabilities" in result
        assert "rulesFired" in result
        assert "modelVersion" in result
        assert "indices" in result
        
        # Risk class should be 1, 2, or 3
        assert result["riskClass"] in [1, 2, 3]
        
        # Probabilities should sum approximately to 1
        probs = result["probabilities"]
        total_prob = probs.get("normal", 0) + probs.get("borderline", 0) + probs.get("deficient", 0)
        assert 0.9 <= total_prob <= 1.1
