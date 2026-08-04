"""Traducción entre el formato de OpenAI y el de Ollama."""
from __future__ import annotations

import pytest

from app.infrastructure.llm.openai_mapper import (
    build_ollama_options,
    chunk_to_openai,
    finish_reason_from_ollama,
    new_completion_id,
    normalize_stop,
    usage_from_ollama,
)


class TestNormalizeStop:
    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            (None, None),
            ("", None),
            ([], None),
            ([""], None),
            (["", ""], None),
            ("FIN", ["FIN"]),
            (["a", ""], ["a"]),
            (["a", "b"], ["a", "b"]),
        ],
    )
    def test_casos(self, entrada, esperado) -> None:
        assert normalize_stop(entrada) == esperado


class TestBuildOptions:
    def test_vacio_si_no_hay_nada(self) -> None:
        assert build_ollama_options() == {}

    def test_los_ceros_no_se_pierden(self) -> None:
        opciones = build_ollama_options(temperature=0, top_p=0)
        assert opciones == {"temperature": 0, "top_p": 0}

    def test_max_tokens_se_traduce(self) -> None:
        assert build_ollama_options(max_tokens=50)["num_predict"] == 50

    def test_extra_no_puede_pisar_model_ni_messages(self) -> None:
        """Se expanden con ** sobre provider.chat(model, messages, ...)."""
        opciones = build_ollama_options(extra={"model": "otro", "messages": [], "seed": 7})
        assert "model" not in opciones and "messages" not in opciones
        assert opciones["seed"] == 7


class TestUsageYFinishReason:
    def test_usage_desde_ollama(self) -> None:
        assert usage_from_ollama({"prompt_eval_count": 11, "eval_count": 4}) == (11, 4)

    def test_usage_ausente_es_cero(self) -> None:
        assert usage_from_ollama({}) == (0, 0)

    def test_finish_reason(self) -> None:
        assert finish_reason_from_ollama({"done_reason": "length"}) == "length"
        assert finish_reason_from_ollama({"done_reason": "stop"}) == "stop"
        assert finish_reason_from_ollama({}) == "stop"


class TestChunk:
    def test_estructura(self) -> None:
        chunk = chunk_to_openai("Ho", "qwen2.5:3b", "chatcmpl-1", 100, role="assistant")
        assert chunk["object"] == "chat.completion.chunk"
        assert chunk["choices"][0]["delta"] == {"role": "assistant", "content": "Ho"}
        assert chunk["choices"][0]["finish_reason"] is None

    def test_chunk_final(self) -> None:
        chunk = chunk_to_openai(None, "m", "chatcmpl-1", 100, finish_reason="stop")
        assert chunk["choices"][0]["delta"] == {}
        assert chunk["choices"][0]["finish_reason"] == "stop"


def test_ids_unicos_con_prefijo_de_openai() -> None:
    ids = {new_completion_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(i.startswith("chatcmpl-") for i in ids)
