"""Classificação segura de erros dos providers de mensagens."""

from __future__ import annotations

import re

import httpx


def is_retryable_provider_error(error: str | None) -> bool:
    """429/5xx podem ser roteados a outro provider do mesmo canal."""
    if not error:
        return False
    match = re.search(r"HTTP\s+(\d{3})", error)
    if not match:
        return False
    status = int(match.group(1))
    return status == 429 or 500 <= status <= 599


def classify_provider_exception(exc: Exception) -> tuple[bool, bool]:
    """Retorna ``(ambiguous, halt_fallback)``.

    Erros 4xx são rejeições confirmadas e podem seguir para um canal de fallback.
    Timeouts, falhas de transporte, respostas 5xx e respostas malformadas são
    ambíguas: o provider pode ter aceitado a mensagem antes de a aplicação perder
    a resposta, portanto o orquestrador deve parar a régua para este aluno.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return False, True
        if 400 <= status < 500:
            return False, False
        return True, True
    if isinstance(exc, (httpx.TimeoutException, httpx.RequestError, ValueError)):
        return True, True
    return True, True


def format_provider_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"provider retornou HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout ao aguardar resposta do provider"
    if isinstance(exc, httpx.RequestError):
        return "falha de comunicação com o provider"
    if isinstance(exc, ValueError):
        return "resposta inválida do provider"
    return str(exc)[:500] or exc.__class__.__name__
