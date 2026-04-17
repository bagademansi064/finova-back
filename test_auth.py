import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.conf import settings
settings.ALLOWED_HOSTS.append('testserver')

from django.test import Client
from users.models import User, EmailVerificationOTP
from django.core import mail

client = Client()

print("\n--- 1. Testing Registration ---")
register_data = {
    "username": "testuser123",
    "email": "test@finova.com",
    "password": "StrongPassword123!",
    "password_confirm": "StrongPassword123!",
    "pan_card": "ABCDE1234F"
}
res = client.post('/api/users/register/', data=json.dumps(register_data), content_type='application/json')
print("Register Status:", res.status_code)
print("Register Response:", res.json())

user = User.objects.get(email="test@finova.com")
print(f"Assigned Finova ID: {user.finova_id}")

print("\n--- 2. Testing Email Verification ---")
otp_obj = EmailVerificationOTP.objects.get(user=user)
otp_code = otp_obj.otp
print("Simulated finding OTP:", otp_code)

verify_data = {
    "email": "test@finova.com",
    "otp": otp_code
}
res2 = client.post('/api/users/verify-email/', data=json.dumps(verify_data), content_type='application/json')
print("Verify Status:", res2.status_code)
print("Verify Response:", res2.json())

print("\n--- 3. Testing Finova ID Login ---")
login_data = {
    "finova_id": user.finova_id,
    "password": "StrongPassword123!"
}
res3 = client.post('/api/users/login/', data=json.dumps(login_data), content_type='application/json')
print("Login Status:", res3.status_code)
print("Login Response Keys:", list(res3.json().keys()) if res3.status_code == 200 else res3.json())
