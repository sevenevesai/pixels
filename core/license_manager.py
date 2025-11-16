"""
Simple license key validation system.
Keys are HMAC-based for security without heavy crypto dependencies.
"""
import hashlib
import hmac
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

# Secret key - CHANGE THIS to your own random string!
# Keep this secret and don't publish it publicly
SECRET_KEY = b"Seveneves_Pixels_2025_Replace_This_With_Random_String"


class LicenseManager:
    """Manages license key validation and storage."""
    
    def __init__(self, settings):
        self.settings = settings
        
    def is_licensed(self) -> bool:
        """Check if app is licensed."""
        key = self.settings.get("license/key", "")
        if not key:
            return False
        return self.validate_key(key)[0]
    
    def get_license_info(self) -> Tuple[bool, str, str]:
        """
        Get license information.
        Returns: (is_valid, email, expiry_date)
        """
        key = self.settings.get("license/key", "")
        if not key:
            return (False, "", "")
        
        is_valid, email, expiry = self.validate_key(key)
        return (is_valid, email, expiry)
    
    def set_license_key(self, key: str) -> Tuple[bool, str]:
        """
        Set and validate license key.
        Returns: (success, message)
        """
        key = key.strip()
        if not key:
            return (False, "Please enter a license key")
        
        is_valid, email, expiry = self.validate_key(key)
        
        if is_valid:
            self.settings.set("license/key", key)
            return (True, f"License activated successfully!\nEmail: {email}\nExpiry: {expiry}")
        else:
            return (False, "Invalid license key. Please check and try again.")
    
    def remove_license(self):
        """Remove stored license key."""
        self.settings.set("license/key", "")
    
    @staticmethod
    def validate_key(key: str) -> Tuple[bool, str, str]:
        """
        Validate a license key.
        Format: BASE64(email|expiry_date|hmac_signature)
        Returns: (is_valid, email, expiry_date)
        """
        try:
            # Decode from base64
            decoded = base64.b64decode(key.encode()).decode()
            parts = decoded.split('|')
            
            if len(parts) != 3:
                return (False, "", "")
            
            email, expiry, signature = parts
            
            # Verify signature
            message = f"{email}|{expiry}".encode()
            expected_sig = hmac.new(SECRET_KEY, message, hashlib.sha256).hexdigest()
            
            if signature != expected_sig:
                return (False, "", "")
            
            # Check expiry (format: YYYY-MM-DD or "lifetime")
            if expiry.lower() != "lifetime":
                try:
                    expiry_date = datetime.strptime(expiry, "%Y-%m-%d")
                    if expiry_date < datetime.now():
                        return (False, "", "")
                except ValueError:
                    return (False, "", "")
            
            return (True, email, expiry)
            
        except Exception as e:
            print(f"License validation error: {e}")
            return (False, "", "")
    
    @staticmethod
    def generate_key(email: str, expiry: str = "lifetime") -> str:
        """
        Generate a license key.
        expiry: "lifetime" or date in format "YYYY-MM-DD"
        This method should only be used by you for generating keys.
        """
        message = f"{email}|{expiry}".encode()
        signature = hmac.new(SECRET_KEY, message, hashlib.sha256).hexdigest()
        
        key_data = f"{email}|{expiry}|{signature}"
        key = base64.b64encode(key_data.encode()).decode()
        
        return key