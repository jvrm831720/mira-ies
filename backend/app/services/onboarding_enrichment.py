"""External institution lookups used by the email-verified onboarding flow."""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

import httpx

FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"
MINHA_RECEITA_URL = "https://minhareceita.org/{cnpj}"


def normalize_public_website(value: str) -> str:
    """Normalize a user-provided URL and reject obvious local/private targets."""
    candidate = value.strip()
    if not candidate:
        raise ValueError("Informe o site institucional.")
    if not re.match(r"^https?://", candidate, re.IGNORECASE):
        candidate = f"https://{candidate}"
    parsed = urlsplit(candidate)
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or hostname in {"localhost", "localhost.localdomain"}
        or hostname.endswith((".local", ".internal", ".localhost", ".test"))
    ):
        raise ValueError("Informe um site público válido.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("O site precisa estar em um endereço público.")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("Informe um site público válido.")
    return candidate


def _optional_text(data: dict, key: str, limit: int = 500) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned[:limit] or None


def normalize_company_data(data: dict) -> dict:
    """Return only the public registration fields needed by the onboarding form."""
    address_parts = [
        data.get("descricao_tipo_de_logradouro"),
        data.get("logradouro"),
        data.get("numero"),
        data.get("complemento"),
        data.get("bairro"),
        data.get("municipio"),
        data.get("uf"),
        data.get("cep"),
    ]
    address = " ".join(" ".join(str(part).split()) for part in address_parts if part)
    return {
        "cnpj": re.sub(r"\D", "", str(data.get("cnpj") or "")),
        "legal_name": _optional_text(data, "razao_social"),
        "trade_name": _optional_text(data, "nome_fantasia"),
        "status": _optional_text(data, "descricao_situacao_cadastral"),
        "primary_activity": _optional_text(data, "cnae_fiscal_descricao"),
        "address": address[:800] or None,
    }


async def lookup_company(cnpj: str) -> dict:
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=3.0), follow_redirects=False) as client:
        response = await client.get(MINHA_RECEITA_URL.format(cnpj=cnpj))
        if response.status_code == 404:
            raise LookupError("CNPJ não encontrado na consulta pública.")
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError("A consulta pública retornou uma resposta inválida.")
    return normalize_company_data(payload)


async def scrape_website(url: str, api_key: str) -> dict:
    """Return Firecrawl page metadata and a bounded Markdown preview, not instructions."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0), follow_redirects=False) as client:
        response = await client.post(
            FIRECRAWL_SCRAPE_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"url": url, "formats": ["markdown"], "onlyMainContent": True, "blockAds": True},
        )
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError("O Firecrawl retornou uma resposta inválida.")
    data = payload.get("data")
    if payload.get("success") is False or not isinstance(data, dict):
        raise LookupError("O Firecrawl não conseguiu extrair o conteúdo do site.")
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    markdown = data.get("markdown") if isinstance(data.get("markdown"), str) else ""
    return {
        "url": url,
        "title": _optional_text(metadata, "title"),
        "description": _optional_text(metadata, "description", 1000),
        "markdown": markdown[:8000],
        "truncated": len(markdown) > 8000,
        "source": "Firecrawl",
    }
