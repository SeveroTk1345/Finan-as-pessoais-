"""Autenticador WebAuthn em software, para testar sem aparelho físico.

Faz o papel do celular: gera um par de chaves P-256 por credencial, monta os dados
do autenticador (hash do domínio, indicadores, contador) e assina o desafio. Os
testes podem desligar a verificação do usuário, trocar a origem ou o contador para
simular ataques.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import struct
from dataclasses import dataclass
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

UP, UV, AT = 0x01, 0x04, 0x40


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64u(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass
class Credential:
    id: bytes
    key: ec.EllipticCurvePrivateKey
    user_handle: bytes
    sign_count: int = 0


class SoftAuthenticator:
    def __init__(self, origin: str) -> None:
        self.origin = origin
        self.credentials: list[Credential] = []

    def _client_data(self, kind: str, challenge: str, origin: str | None) -> bytes:
        return json.dumps(
            {"type": kind, "challenge": challenge, "origin": origin or self.origin, "crossOrigin": False}
        ).encode()

    def create(self, options: dict[str, Any], *, user_verified: bool = True) -> dict[str, Any]:
        """navigator.credentials.create(): cadastra uma credencial nova."""
        rp_id = options["rp"]["id"]
        key = ec.generate_private_key(ec.SECP256R1())
        nums = key.public_key().public_numbers()
        cose = cbor2.dumps(
            {1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")}
        )
        cred = Credential(id=secrets.token_bytes(32), key=key, user_handle=unb64u(options["user"]["id"]))
        flags = UP | AT | (UV if user_verified else 0)
        auth_data = (
            hashlib.sha256(rp_id.encode()).digest()
            + bytes([flags])
            + struct.pack(">I", cred.sign_count)
            + bytes(16)  # AAGUID zerado, como em atestado "none"
            + struct.pack(">H", len(cred.id))
            + cred.id
            + cose
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        self.credentials.append(cred)
        return {
            "id": b64u(cred.id),
            "rawId": b64u(cred.id),
            "type": "public-key",
            "authenticatorAttachment": "platform",
            "clientExtensionResults": {},
            "response": {
                "clientDataJSON": b64u(self._client_data("webauthn.create", options["challenge"], None)),
                "attestationObject": b64u(attestation),
                "transports": ["internal"],
            },
        }

    def get(
        self,
        options: dict[str, Any],
        *,
        credential: Credential | None = None,
        user_verified: bool = True,
        origin: str | None = None,
        user_handle: bytes | None = None,
        sign_count: int | None = None,
    ) -> dict[str, Any]:
        """navigator.credentials.get(): assina o desafio com a credencial guardada."""
        cred = credential or self.credentials[-1]
        cred.sign_count = cred.sign_count + 1 if sign_count is None else sign_count
        flags = UP | (UV if user_verified else 0)
        auth_data = hashlib.sha256(options["rpId"].encode()).digest() + bytes([flags])
        auth_data += struct.pack(">I", cred.sign_count)
        client_data = self._client_data("webauthn.get", options["challenge"], origin)
        signature = cred.key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            "id": b64u(cred.id),
            "rawId": b64u(cred.id),
            "type": "public-key",
            "authenticatorAttachment": "platform",
            "clientExtensionResults": {},
            "response": {
                "clientDataJSON": b64u(client_data),
                "authenticatorData": b64u(auth_data),
                "signature": b64u(signature),
                "userHandle": b64u(user_handle if user_handle is not None else cred.user_handle),
            },
        }
