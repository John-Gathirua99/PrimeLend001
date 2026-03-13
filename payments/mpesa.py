
import base64
import datetime
import logging

import requests
from django.conf import settings
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


# ── Auth ──────────────────────────────────────────────────────
def get_access_token() -> str:
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(
        url,
        auth=HTTPBasicAuth(
            settings.MPESA_CONSUMER_KEY.strip(),
            settings.MPESA_CONSUMER_SECRET.strip(),
        ),
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _stk_password_and_timestamp():
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    raw = f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}"
    password = base64.b64encode(raw.encode()).decode()
    return password, timestamp


# ── Format phone to 2547XXXXXXXX ─────────────────────────────
def _format_phone(phone: str) -> str:
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("+"):
        phone = phone[1:]
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    return phone


# ── STK Push ─────────────────────────────────────────────────
def stk_push(phone: str, amount: int, reference: str, description: str) -> dict:
    """
    Trigger Lipa na M-Pesa STK push.
    Returns full Safaricom response dict.
    Raises on network/auth error.
    """
    phone = _format_phone(phone)
    access_token = get_access_token()
    password, timestamp = _stk_password_and_timestamp()

    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password":          password,
        "Timestamp":         timestamp,
        "TransactionType":   "CustomerPayBillOnline",
        "Amount":            int(amount),
        "PartyA":            phone,
        "PartyB":            settings.MPESA_SHORTCODE,
        "PhoneNumber":       phone,
        "CallBackURL":       settings.MPESA_CALLBACK_URL,
        "AccountReference":  reference[:12],   # max 12 chars
        "TransactionDesc":   description[:13], # max 13 chars
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }

    response = requests.post(
        settings.STK_PUSH_URL,
        json=payload,
        headers=headers,
        timeout=30,
    )

    logger.info(f"STK push [{phone} KES {amount}] → {response.status_code}: {response.text}")
    response.raise_for_status()
    return response.json()


# ── STK Push Status Query ─────────────────────────────────────
def query_stk_status(checkout_request_id: str) -> dict:
    """Check the status of an STK push transaction."""
    access_token = get_access_token()
    password, timestamp = _stk_password_and_timestamp()

    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password":          password,
        "Timestamp":         timestamp,
        "CheckoutRequestID": checkout_request_id,
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }

    response = requests.post(
        "https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query",
        json=payload,
        headers=headers,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


# ── B2C Payment (Disbursement / Withdrawal) ───────────────────
def b2c_payment(phone: str, amount, reference: str) -> dict:
    """
    Send money from business to customer (disbursements & withdrawals).
    Currently sandbox stub — swap URL + security credential for production.
    """
    phone = _format_phone(phone)

    # In sandbox this is a stub — real B2C needs SecurityCredential (encrypted)
    # See: https://developer.safaricom.co.ke/APIs/BusinessToCustomer
    try:
        access_token = get_access_token()

        payload = {
            "InitiatorName":      getattr(settings, "MPESA_INITIATOR_NAME", "testapi"),
            "SecurityCredential": getattr(settings, "MPESA_SECURITY_CREDENTIAL", ""),
            "CommandID":          "BusinessPayment",
            "Amount":             int(amount),
            "PartyA":             settings.MPESA_SHORTCODE,
            "PartyB":             phone,
            "Remarks":            reference,
            "QueueTimeOutURL":    getattr(settings, "MPESA_B2C_TIMEOUT_URL",  settings.MPESA_CALLBACK_URL),
            "ResultURL":          getattr(settings, "MPESA_B2C_RESULT_URL",   settings.MPESA_CALLBACK_URL),
            "Occassion":          reference,
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json",
        }

        b2c_url = getattr(
            settings, "MPESA_B2C_URL",
            "https://sandbox.safaricom.co.ke/mpesa/b2c/v1/paymentrequest"
        )

        response = requests.post(b2c_url, json=payload, headers=headers, timeout=30)
        logger.info(f"B2C [{phone} KES {amount}] → {response.status_code}: {response.text}")
        response.raise_for_status()
        return response.json()

    except Exception as e:
        logger.error(f"B2C payment failed for {phone}: {e}")
        raise