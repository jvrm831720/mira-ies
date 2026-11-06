"""Official Asaas API adapter: pinned hosts, explicit environment, bounded requests.

No user-configured URLs, no automatic POST retries, no secret-bearing logs.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

import httpx

from app.core.config import get_settings

_PAYMENT = re.compile(r"^pay_[a-zA-Z0-9_-]{4,72}$")
_CUSTOMER = re.compile(r"^cus_[a-zA-Z0-9_-]{4,72}$")
_SPLIT = re.compile(r"^[a-zA-Z0-9_-]{6,80}$")
BASES = {"sandbox": "https://api-sandbox.asaas.com/v3", "production": "https://api.asaas.com/v3"}


class GatewayDenied(ValueError):
    pass


class GatewayInconclusive(RuntimeError):
    """Never replay a money-creating POST automatically after this exception."""


class GatewayRejected(ValueError):
    """The provider rejected the request; response contents are not disclosed."""


def environment(*, write: bool = False) -> str:
    cfg = get_settings()
    mode = cfg.asaas_mode
    if mode not in BASES:
        raise GatewayDenied("Ambiente Asaas inválido.")
    if not (cfg.native_academic_enabled and cfg.native_academic_services_enabled
            and cfg.student_finance_reconciliation_enabled):
        raise GatewayDenied("Serviços financeiros desabilitados.")
    if mode == "production":
        if not (cfg.app_env == "production" and cfg.asaas_production_enabled):
            raise GatewayDenied("Produção Asaas bloqueada até aprovação operacional.")
        key = cfg.asaas_production_api_key
        token = cfg.asaas_production_webhook_token
    else:
        if not cfg.asaas_sandbox_enabled:
            raise GatewayDenied("Sandbox oficial Asaas desabilitado.")
        key = cfg.asaas_sandbox_api_key
        token = cfg.asaas_sandbox_webhook_token
    if not isinstance(key, str) or len(key) < 24:
        raise GatewayDenied("Credencial Asaas indisponível.")
    if not isinstance(token, str) or not 32 <= len(token) <= 255 or any(c.isspace() for c in token):
        raise GatewayDenied("Token do webhook Asaas indisponível ou inválido.")
    if write and mode == "production" and not cfg.asaas_production_enabled:
        raise GatewayDenied("Emissão real não autorizada.")
    return mode


def issuer_wallet() -> str:
    mode = environment()
    cfg = get_settings()
    value = (getattr(cfg, "asaas_production_issuer_wallet_id", None) if mode == "production"
             else getattr(cfg, "asaas_sandbox_issuer_wallet_id", None)
                  or getattr(cfg, "student_payments_asaas_issuer_wallet_id", None))
    from uuid import UUID
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise GatewayDenied("Carteira da conta emissora não configurada para o ambiente.") from exc


def token() -> str:
    mode = environment()
    cfg = get_settings()
    return cfg.asaas_sandbox_webhook_token if mode == "sandbox" else cfg.asaas_production_webhook_token


async def request(method: str, path: str, *, data: dict | None = None,
                  params: dict | None = None) -> dict:
    mode = environment(write=method == "POST")
    if method not in {"GET", "POST"} or not path.startswith("/") or ".." in path:
        raise GatewayDenied("Rota não permitida.")
    if not re.fullmatch(r"/[a-zA-Z0-9/_-]+/?", path):
        raise GatewayDenied("Identificador de recurso inválido.")
    auth = get_settings().asaas_sandbox_api_key if mode == "sandbox" else get_settings().asaas_production_api_key
    headers = {
        "access_token": auth,
        "User-Agent": "MIRA-IES/1.0 (+finance-integration)",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=3.0),
            follow_redirects=False, trust_env=False,
        ) as client:
            response = await client.request(
                method, BASES[mode] + path, headers=headers,
                json=data if method == "POST" else None, params=params,
            )
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise GatewayInconclusive("Asaas não confirmou a operação; reconciliação obrigatória.") from exc
    if response.status_code == 429 or response.status_code >= 500 or 300 <= response.status_code < 400:
        raise GatewayInconclusive("Resposta Asaas inconclusiva; não reenviar automaticamente.")
    if response.status_code >= 400:
        raise GatewayRejected("Asaas recusou os dados ou credenciais da operação.")
    if len(response.content) > 128 * 1024:
        raise GatewayInconclusive("Resposta do provedor excedeu o limite.")
    try:
        parsed = response.json()
    except (ValueError, UnicodeError) as exc:
        raise GatewayInconclusive("Resposta Asaas não é JSON válido.") from exc
    if not isinstance(parsed, dict):
        raise GatewayInconclusive("Resposta Asaas incompatível com o contrato.")
    return parsed


def validate_cpf(raw: object) -> str:
    if not isinstance(raw, str):
        raise GatewayDenied("CPF de cobrança precisa estar verificado no cadastro do aluno.")
    digits = "".join(c for c in raw if c.isascii() and c.isdecimal())
    if len(digits) != 11 or len(set(digits)) == 1:
        raise GatewayDenied("CPF do aluno é inválido ou está ausente.")
    for length in (9, 10):
        total = sum(int(c) * (length + 1 - i) for i, c in enumerate(digits[:length]))
        check = (total * 10) % 11
        if (0 if check == 10 else check) != int(digits[length]):
            raise GatewayDenied("CPF do aluno precisa ser corrigido.")
    return digits


def customer_reference(student_id: str) -> str:
    return "MIRA-STUDENT-" + student_id


async def get_or_create_customer(*, student_id: str, name: str, cpf: str) -> str:
    """Reconcilable customer lookup; no repeated POST after ambiguous response."""
    valid_cpf = validate_cpf(cpf)
    if not isinstance(name, str) or not 3 <= len(name.strip()) <= 200:
        raise GatewayDenied("Nome de faturamento ausente.")
    reference = customer_reference(student_id)
    found = await request("GET", "/customers", params={"externalReference": reference, "limit": 10})
    customers = found.get("data")
    if not isinstance(customers, list):
        raise GatewayInconclusive("Listagem de clientes indisponível.")
    matches = [c for c in customers if isinstance(c, dict) and c.get("externalReference") == reference]
    if len(matches) > 1:
        raise GatewayInconclusive("Identificador de cliente duplicado no Asaas.")
    if matches:
        customer = matches[0]
        if customer.get("cpfCnpj") != valid_cpf or not _CUSTOMER.fullmatch(str(customer.get("id", ""))):
            raise GatewayInconclusive("Cliente Asaas não corresponde ao CPF institucional.")
        return customer["id"]
    created = await request("POST", "/customers", data={
        "name": name.strip(), "cpfCnpj": valid_cpf,
        "externalReference": reference, "notificationDisabled": True,
    })
    customer_id = created.get("id")
    if not isinstance(customer_id, str) or not _CUSTOMER.fullmatch(customer_id):
        raise GatewayInconclusive("Cliente Asaas criado sem ID verificável.")
    return customer_id


def charge_payload(*, customer_id: str, method: str, amount: Decimal,
                   due_date: date, external_reference: str, destination_wallet_id: str) -> dict:
    if not _CUSTOMER.fullmatch(customer_id) or method not in {"pix", "boleto"}:
        raise GatewayDenied("Cliente ou método de pagamento inválido.")
    if amount <= 0 or amount != amount.quantize(Decimal("0.01")) or amount > Decimal("9999999999.99"):
        raise GatewayDenied("Valor da obrigação inválido.")
    from app.services.student_payments import asaas_split_rule
    return {
        "customer": customer_id,
        "billingType": "PIX" if method == "pix" else "BOLETO",
        "value": float(amount),
        "dueDate": due_date.isoformat(),
        "externalReference": external_reference,
        "description": "Mensalidade acadêmica",
        "split": asaas_split_rule(destination_wallet_id)["split"],
    }


def verify_payment_response(remote: dict, charge, *, strict: bool = True) -> str:
    """Prevent silently using modified split/payment/customer/amount."""
    payment_id = remote.get("id")
    if not isinstance(payment_id, str) or not _PAYMENT.fullmatch(payment_id):
        raise GatewayInconclusive("ID da cobrança externa inválido.")
    if (remote.get("externalReference") != charge.external_reference
            or remote.get("customer") != charge.customer_id
            or remote.get("billingType") != ("PIX" if charge.method == "pix" else "BOLETO")):
        raise GatewayInconclusive("Cobrança diverge do cliente ou da referência interna.")
    try:
        amount = Decimal(str(remote.get("value")))
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise GatewayInconclusive("Valor externo inválido.") from exc
    if amount != charge.amount:
        raise GatewayInconclusive("Cobrança externa diverge no valor.")
    split = remote.get("split")
    if not isinstance(split, list) or len(split) != 1:
        raise GatewayInconclusive("Provedor não confirmou o Split único obrigatório.")
    dest = split[0]
    if not isinstance(dest, dict) or dest.get("walletId") != charge.destination_wallet_id:
        raise GatewayInconclusive("Carteira do Split não corresponde ao workspace.")
    if dest.get("fixedValue") not in (None, 0):
        raise GatewayInconclusive("Split contém um valor fixo não autorizado.")
    try:
        percent = Decimal(str(dest.get("percentualValue")))
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise GatewayInconclusive("Percentual de Split inválido.") from exc
    if percent != 100:
        raise GatewayInconclusive("Split diferente de 100% do líquido.")
    return payment_id


def verify_split_response(remote: dict, charge, split_id: str) -> bool:
    payment = remote.get("payment")
    payment_id = payment.get("id") if isinstance(payment, dict) else payment
    if (remote.get("id") != split_id or remote.get("walletId") != charge.destination_wallet_id
            or payment_id != charge.asaas_payment_id):
        raise GatewayInconclusive("Split não pertence à cobrança e à IES.")
    return remote.get("status") == "DONE"


async def payment_instructions(payment_id: str, method: str) -> dict:
    if not _PAYMENT.fullmatch(payment_id):
        raise GatewayDenied("Cobrança sem ID válido.")
    if method == "pix":
        result = await request("GET", f"/payments/{payment_id}/pixQrCode")
        payload = result.get("payload")
        if not isinstance(payload, str) or not 20 <= len(payload) <= 2000:
            raise GatewayInconclusive("Pix copia e cola indisponível.")
        return {"method": "pix", "copy_and_paste": payload,
                "expiration_date": result.get("expirationDate")}
    if method == "boleto":
        result = await request("GET", f"/payments/{payment_id}/identificationField")
        line = result.get("identificationField")
        if not isinstance(line, str) or not re.fullmatch(r"[0-9]{44,50}", line):
            raise GatewayInconclusive("Linha digitável indisponível.")
        return {"method": "boleto", "identification_field": line}
    raise GatewayDenied("Forma de pagamento indisponível.")
