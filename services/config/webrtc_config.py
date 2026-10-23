import os
import json
import urllib.request
import streamlit as st
from streamlit_webrtc import RTCConfiguration


def _search_dict_case_insensitive(d, *target_keys):
    """Search a dictionary or AttrDict case-insensitively, including 1 level of nested dicts."""
    target_lower = {k.lower() for k in target_keys}

    # 1. Check top-level
    if hasattr(d, "items"):
        for k, v in d.items():
            if k.lower() in target_lower and v:
                return str(v).strip()

    # 2. Check 1 level of nested dictionaries
    if hasattr(d, "items"):
        for _, sub in d.items():
            if hasattr(sub, "items"):
                for sk, sv in sub.items():
                    if sk.lower() in target_lower and sv:
                        return str(sv).strip()

    return ""


def _get_secret_val(*target_keys):
    """Retrieve secret from st.secrets or os.environ using case-insensitive key search."""
    # Check st.secrets
    try:
        if hasattr(st, "secrets") and st.secrets is not None:
            val = _search_dict_case_insensitive(st.secrets, *target_keys)
            if val:
                return val
    except Exception:
        pass

    # Check os.environ
    for k, v in os.environ.items():
        for target in target_keys:
            if k.lower() == target.lower() and v:
                return str(v).strip()

    return ""


def _get_all_secret_keys():
    """List all detected top-level secret keys without leaking values."""
    keys = []
    try:
        if hasattr(st, "secrets") and st.secrets is not None:
            for k in st.secrets.keys():
                keys.append(str(k))
    except Exception:
        pass
    return keys


@st.cache_data(ttl=1800)
def _fetch_metered_ice_servers(domain: str, api_key: str):
    domain = domain.replace("https://", "").replace("http://", "").strip().rstrip("/")
    if not domain.endswith(".metered.live") and not domain.endswith(".metered.ca"):
        domain = f"{domain}.metered.live"
    url = f"https://{domain}/api/v1/turn/credentials?apiKey={api_key}"
    req = urllib.request.Request(url, headers={"User-Agent": "StreamlitApp/1.0"})
    with urllib.request.urlopen(req, timeout=7) as resp:
        if resp.status == 200:
            return json.loads(resp.read().decode())
    return None


def _expand_turn_urls(raw_turn):
    """Given a TURN URL or hostname, return full set of UDP and TCP transports on ports 80 and 443."""
    host = raw_turn.strip()
    # Strip protocol prefix if present
    for prefix in ["turn:", "turns:"]:
        if host.startswith(prefix):
            host = host[len(prefix) :]
    # Strip port/params
    if "?" in host:
        host = host.split("?")[0]
    if ":" in host:
        host = host.split(":")[0]

    if not host:
        return [raw_turn]

    return [
        f"turn:{host}:80",
        f"turn:{host}:80?transport=tcp",
        f"turn:{host}:443",
        f"turn:{host}:443?transport=tcp",
    ]


def get_webrtc_config():
    """
    Builds and returns (RTCConfiguration, status_dict).
    Checks for TURN credentials from:
      1. Twilio: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
      2. Metered API: METERED_DOMAIN (or domain), METERED_API_KEY (or api_key)
      3. Metered / Generic static: turn_url, turn_username, turn_password / credential
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

    detected_keys = _get_all_secret_keys()
    status = {
        "has_turn": False,
        "provider": "stun_only",
        "details": "Google STUN only (No TURN active)",
        "secrets_found": detected_keys,
        "error": None,
    }

    # 1. Twilio
    twilio_sid = _get_secret_val("TWILIO_ACCOUNT_SID", "twilio_sid")
    twilio_token = _get_secret_val("TWILIO_AUTH_TOKEN", "twilio_token")
    if twilio_sid and twilio_token:
        try:
            from streamlit_webrtc import get_twilio_ice_servers

            twilio_servers = get_twilio_ice_servers(twilio_sid, twilio_token)
            status["has_turn"] = True
            status["provider"] = "Twilio"
            status["details"] = "Twilio Network Traversal TURN"
            return RTCConfiguration({"iceServers": twilio_servers}), status
        except Exception as e:
            status["error"] = f"Twilio error: {e}"

    # 2. Metered.ca API Key & Domain
    metered_domain = _get_secret_val("METERED_DOMAIN", "domain", "metered_domain")
    metered_key = _get_secret_val("METERED_API_KEY", "api_key", "metered_api_key")
    if metered_domain and metered_key:
        try:
            servers = _fetch_metered_ice_servers(metered_domain, metered_key)
            if servers and isinstance(servers, list):
                status["has_turn"] = True
                status["provider"] = "Metered.ca API"
                status["details"] = f"Metered.ca Relay ({metered_domain})"
                return RTCConfiguration({"iceServers": servers}), status
        except Exception as e:
            status["error"] = f"Metered API error: {e}"

    # 3. Static TURN credentials (Metered, Xirsys, or custom)
    turn_url = _get_secret_val("turn_url", "TURN_URL", "turn_urls", "urls")
    turn_user = _get_secret_val("turn_username", "TURN_USERNAME", "username", "user")
    turn_pass = _get_secret_val(
        "turn_password", "TURN_PASSWORD", "turn_credential", "credential", "password"
    )

    if turn_url and turn_user and turn_pass:
        expanded_urls = _expand_turn_urls(turn_url)
        ice_servers.append(
            {
                "urls": expanded_urls,
                "username": turn_user,
                "credential": turn_pass,
            }
        )
        status["has_turn"] = True
        status["provider"] = "Static TURN"
        status["details"] = f"Relay ({turn_url}) with TCP/UDP fallback"
        status["error"] = None
        return RTCConfiguration({"iceServers": ice_servers}), status

    return RTCConfiguration({"iceServers": ice_servers}), status
