import os
import streamlit as st
from streamlit_webrtc import RTCConfiguration


def get_webrtc_config():
    """
    Builds and returns RTCConfiguration for streamlit-webrtc.
    Checks for TURN credentials in Streamlit secrets or environment variables.
    Supports:
      1. Twilio:
         - TWILIO_ACCOUNT_SID
         - TWILIO_AUTH_TOKEN
      2. Metered.ca / Generic TURN:
         - [webrtc] turn_url, turn_username, turn_password
         - or TURN_URL / TURN_URLS, TURN_USERNAME, TURN_PASSWORD
    Falls back to Google public STUN servers.
    """
    ice_servers = [
        {
            "urls": [
                "stun:stun.l.google.com:19302",
                "stun:stun1.l.google.com:19302",
                "stun:stun2.l.google.com:19302",
                "stun:stun3.l.google.com:19302",
                "stun:stun4.l.google.com:19302",
            ]
        }
    ]

    has_turn = False

    # 1. Check Twilio credentials in Streamlit secrets or environment
    twilio_sid = ""
    twilio_token = ""
    try:
        if hasattr(st, "secrets"):
            twilio_sid = st.secrets.get("TWILIO_ACCOUNT_SID", "")
            twilio_token = st.secrets.get("TWILIO_AUTH_TOKEN", "")
    except Exception:
        pass

    if not twilio_sid:
        twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    if not twilio_token:
        twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "")

    if twilio_sid and twilio_token:
        try:
            from streamlit_webrtc import get_twilio_ice_servers

            twilio_servers = get_twilio_ice_servers(twilio_sid, twilio_token)
            return RTCConfiguration({"iceServers": twilio_servers}), True
        except Exception:
            pass

    # 2. Check Generic / Metered.ca TURN credentials
    turn_url = ""
    turn_user = ""
    turn_pass = ""
    try:
        if hasattr(st, "secrets"):
            if "webrtc" in st.secrets:
                webrtc_sec = st.secrets["webrtc"]
                turn_url = webrtc_sec.get("turn_url", "")
                turn_user = webrtc_sec.get("turn_username", "")
                turn_pass = webrtc_sec.get("turn_password", "")

            if not turn_url:
                turn_url = st.secrets.get("TURN_URL") or st.secrets.get("TURN_URLS", "")
                turn_user = st.secrets.get("TURN_USERNAME", "")
                turn_pass = st.secrets.get("TURN_PASSWORD") or st.secrets.get(
                    "TURN_CREDENTIAL", ""
                )
    except Exception:
        pass

    if not turn_url:
        turn_url = os.getenv("TURN_URL", "")
        turn_user = os.getenv("TURN_USERNAME", "")
        turn_pass = os.getenv("TURN_PASSWORD", "")

    if turn_url and turn_user and turn_pass:
        if isinstance(turn_url, str):
            urls = [u.strip() for u in turn_url.split(",") if u.strip()]
        else:
            urls = list(turn_url)

        ice_servers.append(
            {
                "urls": urls,
                "username": turn_user,
                "credential": turn_pass,
            }
        )
        has_turn = True

    return RTCConfiguration({"iceServers": ice_servers}), has_turn
