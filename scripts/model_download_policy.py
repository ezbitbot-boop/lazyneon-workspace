"""Explicit model acquisition consent; offline always takes precedence."""
import json
import os
from pathlib import Path


def offline():
    if any(os.environ.get(k, '').lower() in {'1', 'true', 'yes'} for k in
           ('LAZYNEON_OFFLINE', 'LAZYNEON_WS_OFFLINE')):
        return True
    raw = os.environ.get('LAZYNEON_WS', '')
    if raw:
        try:
            settings = json.loads(raw) if raw.lstrip().startswith('{') else json.loads(Path(raw).read_text())
            return settings.get('offline') is True
        except (ValueError, OSError):
            return True  # unreadable requested policy is not network permission
    return False


def downloads_allowed(consent=False):
    return consent is True and not offline()


def local_model_or_consent(model, consent=False):
    if Path(model).exists():
        return str(Path(model).resolve())
    if not downloads_allowed(consent):
        raise PermissionError('Model unavailable locally; --allow-model-download required (OFFLINE overrides consent)')
    return model
