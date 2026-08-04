"""Hash y generación de API keys."""
from __future__ import annotations

from app.infrastructure.security.hashing import Sha256KeyHasher
from app.infrastructure.security.key_generator import SecretsKeyGenerator


class TestHasher:
    def test_es_determinista_y_de_64_hex(self) -> None:
        hasher = Sha256KeyHasher()
        assert hasher.hash("sk_live_x") == hasher.hash("sk_live_x")
        assert len(hasher.hash("sk_live_x")) == 64

    def test_claves_distintas_dan_hashes_distintos(self) -> None:
        hasher = Sha256KeyHasher()
        assert hasher.hash("a") != hasher.hash("b")

    def test_verify(self) -> None:
        hasher = Sha256KeyHasher()
        h = hasher.hash("sk_live_x")
        assert hasher.verify("sk_live_x", h) is True
        assert hasher.verify("sk_live_y", h) is False

    def test_el_hash_no_contiene_la_clave(self) -> None:
        assert "sk_live" not in Sha256KeyHasher().hash("sk_live_secreto")


class TestGenerator:
    def test_prefijo_y_unicidad(self) -> None:
        generador = SecretsKeyGenerator(prefix="sk_live_")
        claves = {generador.generate() for _ in range(200)}
        assert len(claves) == 200
        assert all(c.startswith("sk_live_") for c in claves)

    def test_longitud_suficiente(self) -> None:
        clave = SecretsKeyGenerator(prefix="sk_live_").generate()
        assert len(clave) - len("sk_live_") >= 30
