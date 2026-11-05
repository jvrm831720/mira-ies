# Licenças e proveniência — MIRA + Frappe

Esta distribuição referencia projetos Frappe de terceiros por **submódulos Git versionados**. O código referenciado mantém os titulares originais, licenças, avisos e histórico upstream. Não afirmar autoria exclusiva da MIRA nem apagar créditos. O manifesto `vendor-lock.json` fixa os commits auditados em 5 nov. 2026; atualizar exige revisão de código e licença.

- Frappe Framework: MIT — https://github.com/frappe/frappe
- ERPNext: GPL-3.0 — https://github.com/frappe/erpnext
- Frappe Education: o próprio projeto declara GPLv3 em `education/hooks.py` e marketplace; confira o `license.txt` do commit fixado — https://github.com/frappe/education
- Frappe UI: MIT, biblioteca Vue; não colocar código Vue no Next.js React supondo compatibilidade — https://github.com/frappe/frappe-ui
- Frappe Docker: MIT — https://github.com/frappe/frappe_docker
- Payments: MIT (repo); cada gateway e SDK têm condições próprias — https://github.com/frappe/payments
- Print Designer: AGPL-3.0 — https://github.com/frappe/print_designer

**GPL/AGPL:** antes de distribuir apps modificados, integrar código copyleft em módulos fechados ou lançar serviços AGPL acessíveis em rede, avaliar as obrigações de disponibilização do código-fonte correspondentes com assessoria jurídica. O uso interno/hospedagem própria não elimina todas as obrigações; **não presumir que o SaaS inteiro fica proprietário**. Cumprir também políticas de marcas e logos; o produto público se chama MIRA, sem sugerir afiliação oficial com Frappe.

**Política operacional:** nada de trocar o banco PostgreSQL atual da MIRA nem rodar migrations Frappe nele. O Frappe deve funcionar em ambiente/banco/Redis próprios, com contas e segredos próprios, sem exposição pública automática. Não habilitar cobrança real, Pix ou disparo de mensagens sem homologação e autorização.
