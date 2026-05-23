# ================================================
# FILE: config/supabase_client.py
# PURPOSE: Single shared Supabase connection
#          Used by all files that need database access
#
# HOW IT WORKS:
#   All files import get_client() from here.
#   Credentials come from Streamlit secrets.
#   Falls back gracefully if Supabase unreachable.
# ================================================

import streamlit as st

_client = None

def get_client():
    """
    Return a shared Supabase client instance.
    Creates it once and reuses it (singleton pattern).
    Returns None if connection fails — callers handle gracefully.
    """
    global _client

    if _client is not None:
        return _client

    try:
        from supabase import create_client, Client

        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]

        _client = create_client(url, key)
        return _client

    except KeyError:
        # Supabase secrets not configured yet
        print("⚠️ Supabase credentials not found in secrets.toml")
        return None

    except Exception as e:
        print(f"⚠️ Could not connect to Supabase: {e}")
        return None


def is_connected():
    """Quick check if Supabase is available."""
    return get_client() is not None
