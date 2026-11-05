# Wave 4A — Proveniência de documentos acadêmicos

## Capacidade entregue em código
- Emissão de atestação de integridade para documentos **já publicados** pela instituição.
- Autorização institucional `critical.manage` + sessão MFA AAL2.
- HMAC-SHA256 sobre representação canônica do documento, usando chave do servidor
  versionada e protegida via variáveis de ambiente; a chave nunca entra no banco.
- Código de verificação de alta entropia, disponível ao próprio aluno autenticado.
- Verificação pública `POST /api/v1/public/academic-documents/verify`: devolve apenas
  `valid: true/false`, sem revelar aluno, documento, CPF, instituição ou conteúdo.
- Revogação explícita por operador MFA; trigger PostgreSQL impede apagar,
  sobrescrever atestação ou revogar mais de uma vez.
- Migration 061 com RLS/FORCE RLS, FK composta de tenant e controle de integridade.

## Não é assinatura oficial qualificada
A atestação comprova integridade e proveniência **dentro da MIRA**.
Não substitui assinatura eletrônica avançada/qualificada exigida por regulamentos,
não confere validade de diploma e não gera automaticamente um PDF oficial.
Documento oficial em PDF, QR code, certificado institucional, carimbo de tempo
confiável e política de assinatura deverão passar por homologação jurídica.

## Ativação (somente sandbox)
`STUDENT_DOCUMENT_ATTESTATION_ENABLED=false` por padrão.
`STUDENT_DOCUMENT_SIGNING_KEYS` é um JSON de chaves nomeadas com pelo menos
32 bytes de segredo aleatório cada, ex. `{"v1":"<segredo-aleatorio>"}`.
`STUDENT_DOCUMENT_ACTIVE_KEY_ID` aponta para uma das chaves.
Manter versões antigas para verificar atestações históricas após rotação.
Exigir `NATIVE_ACADEMIC_ENABLED`, `STUDENT_PORTAL_ENABLED` e
`NATIVE_ACADEMIC_SERVICES_ENABLED` conforme a Wave 3.

## Gates
PostgreSQL descartável com usuário sem BYPASSRLS, alterações após publicação,
tutela de dois tenants, revogação, rotação, isolamento de aluno, abuso do endpoint
de verificação e revisão de UX. Sem deploy nem migration Supabase no merge.
