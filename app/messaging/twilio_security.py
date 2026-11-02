"""Twilio signature calculation and verification utilities."""

import base64
import hashlib
import hmac
from typing import Mapping


def compute_twilio_signature(url: str, params: Mapping[str, str], auth_token: str) -> str:
    """Compute Twilio HMAC-SHA1 signature for a URL and POST parameters.
    
    Twilio signature algorithm:
    1. Take the full URL (including scheme and host).
    2. Sort POST parameters alphabetically by key.
    3. Append each key and its value to the URL string.
    4. Sign the resulting string using HMAC-SHA1 with the Auth Token.
    5. Base64-encode the signature.
    """
    data = url
    for key in sorted(params.keys()):
        data += f"{key}{params[key]}"
    mac = hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode("utf-8")


def verify_twilio_signature(
    url: str,
    params: Mapping[str, str],
    signature: str | None,
    auth_token: str,
    alternate_url: str | None = None,
) -> bool:
    """Validate incoming X-Twilio-Signature against computed signature."""
    if not signature or not auth_token:
        return False
    expected = compute_twilio_signature(url, params, auth_token)
    if hmac.compare_digest(expected, signature):
        return True
    if alternate_url:
        expected_alt = compute_twilio_signature(alternate_url, params, auth_token)
        if hmac.compare_digest(expected_alt, signature):
            return True
    return False
