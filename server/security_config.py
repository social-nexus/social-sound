"""Shared security configuration for the local Social Sound web app."""
LOCAL_HOSTS = frozenset({"localhost:8000", "127.0.0.1:8000"})
LOCAL_ORIGINS = frozenset({"http://localhost:8000", "http://127.0.0.1:8000"})
LOCAL_ORIGIN_BYTES = frozenset(origin.encode("ascii") for origin in LOCAL_ORIGINS)
