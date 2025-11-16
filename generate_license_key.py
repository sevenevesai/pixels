#!/usr/bin/env python3
"""
License Key Generator for Pixels Toolkit
KEEP THIS FILE PRIVATE - DO NOT DISTRIBUTE
"""
import sys
from datetime import datetime, timedelta
from core.license_manager import LicenseManager


def generate_key():
    """Interactive license key generator."""
    print("=" * 60)
    print("Pixels Toolkit - License Key Generator")
    print("=" * 60)
    print()
    
    # Get email
    email = input("Enter customer email: ").strip()
    if not email or '@' not in email:
        print("❌ Invalid email address")
        return
    
    # Get expiry
    print("\nExpiry options:")
    print("1. Lifetime")
    print("2. 1 Year")
    print("3. Custom date (YYYY-MM-DD)")
    
    choice = input("\nSelect option (1-3): ").strip()
    
    if choice == "1":
        expiry = "lifetime"
    elif choice == "2":
        expiry_date = datetime.now() + timedelta(days=365)
        expiry = expiry_date.strftime("%Y-%m-%d")
    elif choice == "3":
        expiry = input("Enter expiry date (YYYY-MM-DD): ").strip()
        # Validate date
        try:
            datetime.strptime(expiry, "%Y-%m-%d")
        except ValueError:
            print("❌ Invalid date format")
            return
    else:
        print("❌ Invalid option")
        return
    
    # Generate key
    key = LicenseManager.generate_key(email, expiry)
    
    print("\n" + "=" * 60)
    print("✅ License Key Generated Successfully!")
    print("=" * 60)
    print(f"\nEmail:  {email}")
    print(f"Expiry: {expiry}")
    print(f"\nLicense Key:\n{key}")
    print("\n" + "=" * 60)
    print("\nSend this key to the customer via email.")
    print("They can activate it via Help > Enter License Key")
    print("=" * 60)


if __name__ == "__main__":
    try:
        generate_key()
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        sys.exit(0)