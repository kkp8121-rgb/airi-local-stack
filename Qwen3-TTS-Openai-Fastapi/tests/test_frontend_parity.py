# coding=utf-8
# SPDX-License-Identifier: Apache-2.0
"""
Frontend parity checks for API-exposed capabilities.
"""

from pathlib import Path


INDEX_HTML_PATH = Path(__file__).resolve().parents[1] / "api" / "static" / "index.html"


def test_frontend_includes_normalization_options_payload():
    """Frontend must expose API normalization options in speech requests."""
    html = INDEX_HTML_PATH.read_text(encoding="utf-8")
    assert "normalization_options" in html
    assert "unit_normalization" in html
    assert "url_normalization" in html
    assert "email_normalization" in html
    assert "phone_normalization" in html
    assert "replace_remaining_symbols" in html


def test_frontend_uses_model_and_capability_endpoints_for_differentiation():
    """Frontend must consume API endpoints that describe model differences."""
    html = INDEX_HTML_PATH.read_text(encoding="utf-8")
    assert "/v1/models/" in html
    assert "/v1/audio/voices" in html
    assert "/v1/audio/voice-clone/capabilities" in html
    assert "Backend model type" in html
    assert "voicedesign" in html
    assert "non-streaming" in html
