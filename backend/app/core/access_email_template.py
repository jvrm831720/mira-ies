"""Transactional MIRA access-code email (HTML + plain-text fallback)."""

from __future__ import annotations

from html import escape


def access_code_email(code: str, *, ttl_minutes: int = 5) -> tuple[str, str]:
    """Render both MIME alternatives without exposing account-existence details."""
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        raise ValueError("Access code must contain exactly six ASCII digits.")
    if ttl_minutes < 1:
        raise ValueError("TTL must be positive.")

    plain = (
        "Olá,\n\n"
        "Use o código abaixo para continuar seu acesso à MIRA.\n\n"
        f"{code}\n\n"
        f"Seu código é válido por {ttl_minutes} minutos e pode ser utilizado apenas uma vez.\n\n"
        "Se você não solicitou este acesso, basta ignorar este e-mail.\n\n"
        "Até breve,\nEquipe MIRA"
    )
    safe_code = escape(code)
    html = f"""<!doctype html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Seu código de acesso à MIRA</title></head>
<body style="margin:0;padding:0;background-color:#f3f4f6;color:#101112;font-family:Arial,Helvetica,sans-serif;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
Use seu código de acesso para continuar na MIRA. Válido por {ttl_minutes} minutos.
</div>
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color:#f3f4f6;">
<tr><td align="center" style="padding:48px 16px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:560px;">
<tr><td align="center" style="padding:0 0 30px;">
<span style="font-family:Arial,Helvetica,sans-serif;color:#101112;font-size:29px;letter-spacing:-1.5px;font-weight:700;">mira</span>
</td></tr>
<tr><td style="background-color:#ffffff;padding:46px 42px;border:1px solid #e6e7ea;border-top:3px solid #3577f1;">
<p style="margin:0 0 24px;font-size:16px;line-height:24px;color:#101112;">Olá,</p>
<h1 style="margin:0 0 20px;font-size:27px;line-height:34px;letter-spacing:-0.7px;font-weight:600;color:#101112;">Seu código de acesso.</h1>
<p style="margin:0 0 28px;font-size:16px;line-height:26px;color:#505967;">Use o código abaixo para continuar seu acesso à MIRA.</p>
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
<tr><td align="center" style="padding:22px 12px;background-color:#f8f9fa;border:1px solid #e6e7ea;">
<span style="font-size:32px;line-height:40px;font-weight:700;letter-spacing:7px;color:#101112;font-family:Arial,Helvetica,sans-serif;">{safe_code}</span>
</td></tr>
</table>
<p style="margin:24px 0 0;font-size:14px;line-height:23px;color:#505967;">Seu código é válido por <strong style="color:#101112;">{ttl_minutes} minutos</strong> e pode ser utilizado apenas uma vez.</p>
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"><tr><td style="padding-top:28px;border-bottom:1px solid #e6e7ea;"></td></tr></table>
<p style="margin:25px 0 24px;font-size:14px;line-height:23px;color:#75777c;">Se você não solicitou este acesso, basta ignorar este e-mail.</p>
<p style="margin:0;font-size:14px;line-height:23px;color:#505967;">Até breve,<br>Equipe MIRA</p>
</td></tr>
<tr><td align="center" style="padding:26px 12px;font-size:12px;line-height:19px;color:#858a93;">
Esta é uma mensagem automática da MIRA. Não é necessário responder.
</td></tr>
</table></td></tr>
</table></body></html>"""
    return plain, html
