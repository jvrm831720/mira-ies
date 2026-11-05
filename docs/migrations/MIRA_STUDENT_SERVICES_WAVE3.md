# MIRA Educação — Wave 3: Serviços do Aluno

## Escopo
- Solicitações autenticadas pelo token de sessão revogável do aluno; listagem e histórico derivados do aluno da sessão.
- Revisão por operador institucional autenticado, com autorização `critical.manage`, estados válidos, trava de linha e evento append-only.
- Documentos textuais institucionais em rascunho, publicação explícita e consulta somente pelo aluno destinatário.
- Referências financeiras somente de leitura, com identificador e estado da fonte. **Nenhum Pix, boleto, link de pagamento ou cobrança é criado pela MIRA nessa wave.**
- Interface do Portal em abas de solicitações, documentos e financeiro.

## Restrições deliberadas
- Flag `NATIVE_ACADEMIC_SERVICES_ENABLED=false` por padrão, além das flags `NATIVE_ACADEMIC_ENABLED` e `STUDENT_PORTAL_ENABLED`.
- A migration `059_student_services` precisa de homologação em PostgreSQL descartável com usuário sem `BYPASSRLS`.
- Não há geração de PDF oficial, assinatura eletrônica, upload de arquivos, armazenamento externo nem integração financeira de ingestão nesta wave.
- Não reutilizar o módulo de cobrança para iniciar pagamentos no Portal. O conector financeiro do tenant será responsável por status, reconciliação, identificador e proveniência em wave posterior.
- Não há dados financeiros falsos, notificações automáticas ou identificação presumida do aluno.
- `main` não deve ser publicada nem receber migrations de forma automática antes da homologação.

## Próximos gates
1. Confirmar migração e rollback em banco descartável e verificações RLS com dois tenants.
2. Validar APIs com sessões reais de aluno e operador, revogação e autorização negativa.
3. Homologar UX de solicitações, documentos e fontes financeiras.
4. Aprovar explicitamente migrations e publicação, separadamente do merge.
