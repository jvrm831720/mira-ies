# Prioridade 13 — Wave 13.5: matriz de auditoria ponta a ponta

## Critérios demonstrados

1. Instituição A produz contribuição sanitizada elegível.
2. Modalidade B bloqueada no serviço.
3. Isolamento entre dois tenants na chave de contribuição.
4. Revogação impede dataset compartilhado.
5. Run shared exige contribuições elegíveis + política revalidada.
6. MIRA Base só registra candidato de run `shared_base` succeeded.
7. Activate exclusivo + rollback com histórico append-only.

Ver testes em `backend/tests/test_governance_wave13_5_e2e_audit.py`.

**Operacional:** migrations versionadas; nenhuma aplicada remotamente neste merge sem gate explícito.
