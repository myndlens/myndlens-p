from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from types import SimpleNamespace

import pytest

from config.validators import _require_jwt_secret, validate_startup_config


def _settings(**overrides):
    base = {
        "JWT_SECRET": "test-secret",
        "MIO_KEY_ENCRYPTION_KEY": "enc-key",
        "MYNDLENS_BASE_URL": "https://app.myndlens.com",
        "OBEGEE_API_URL": "https://obegee.co.uk/api",
        "CHANNEL_ADAPTER_IP": "138.68.179.111",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.parametrize("jwt_secret", ["", "   "])
def test_require_jwt_secret_fails_when_empty(jwt_secret):
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        _require_jwt_secret(_settings(JWT_SECRET=jwt_secret))


def test_validate_startup_config_raises_on_missing_required_vars():
    with pytest.raises(RuntimeError, match="MIO_KEY_ENCRYPTION_KEY"):
        validate_startup_config(_settings(MIO_KEY_ENCRYPTION_KEY=""))


def test_validate_startup_config_raises_on_missing_base_url():
    with pytest.raises(RuntimeError, match="MYNDLENS_BASE_URL"):
        validate_startup_config(_settings(MYNDLENS_BASE_URL=""))


def test_validate_startup_config_logs_warning_for_dispatch_vars(caplog):
    caplog.set_level("WARNING")

    validate_startup_config(_settings(OBEGEE_API_URL="", CHANNEL_ADAPTER_IP=""))

    assert "OBEGEE_API_URL" in caplog.text
    assert "CHANNEL_ADAPTER_IP" in caplog.text


def test_validate_startup_config_passes_with_valid_required_config():
    validate_startup_config(_settings())
