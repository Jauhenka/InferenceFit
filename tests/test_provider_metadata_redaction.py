"""Native response persistence must not add credential exposure."""

import json

from inferencefit.providers.metadata import safe_native_response


def test_native_json_redacts_credential_key_aliases_and_echoed_values():
    native = {
        "content": [{"type": "text", "text": "answer"}],
        "metadata": {
            " apiKey ": "other-provider-key",
            "accessToken": "access-token-value",
            "refreshToken": "refresh-token-value",
            "clientSecret": "client-secret-value",
            "Authorization ": "Bearer " + "other-provider-key",
            "requestHeaders": [{"X-Api-Key": "another-key"}],
            "note": "resolved-secret was echoed",
            "suspicious": "Bearer " + "independent-token-value",
        },
    }
    safe = safe_native_response(native, "resolved-secret")
    encoded = json.dumps(safe)
    for secret in (
        "other-provider-key",
        "access-token-value",
        "refresh-token-value",
        "client-secret-value",
        "another-key",
        "resolved-secret",
        "independent-token-value",
    ):
        assert secret not in encoded
    assert safe["content"] == native["content"]
