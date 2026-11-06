# MIRA — Gate de release e compatibilidade (verificação 06/11/2026)

Este documento diferencia **merge**, **migration** e **publicação**. É um registro de evidências e proposta de controle; não altera configurações em serviços ativos.

## Evidências confirmadas diretamente

- **GitHub:** as PRs #171 Object Index, #172 Portal do Aluno, #173 Workflow Experience e #174 Record Experience foram integradas à `main`. A #174 foi integrada no merge `9b670896f89438a22455d06369fe7be42e5a8b5d` após CI aprovado no HEAD reconciliado.
- **Vercel:** projeto efetivamente verificado `mira-ies`, ID `prj_Grf4E284ZnParr4aWVGVFdFrYfZp` sob equipe `team_HhTzRWKWW1iuB4eHGLptdsee`. A consulta mais recente nesta análise encontrou deployment production `READY` no commit `208ec56091cdc5be606c60cc94e8942bc105dc3c`, anterior à Wave 0.2. O projeto está ligado a `jvrm831720/mira-ies`. Atualizar o commit publicado antes de qualquer declaração de produção atualizada.
- **GitHub Actions Cloudflare:** o arquivo `.github/workflows/deploy-cloudflare.yml` aciona deploy ao modificar `frontend/**` em `push: main`. A execução anterior falhou por ausência de `CLOUDFLARE_API_TOKEN`; não presumir que publicação Cloudflare ocorreu.
- **Supabase `mira-testes`:** projeto `wovteqlakcilpyvyphvm`; `SELECT version_num FROM public.alembic_version` retornou `066_object_index_views`; tabela `public.mira_object_views` existe e aplica `relrowsecurity=true`, `relforcerowsecurity=true`. Política `mira_object_views_owner_policy` exige `tenant_id = current_setting('app.tenant_id')` e `owner_user_id = current_setting('app.user_id')`; índices em `(tenant_id,owner_user_id,object_key)` identificados.
- **Render:** o serviço desejado é `mira-api-testes`, mas o conector ainda não tem workspace confirmado pelo usuário; branch, autoDeploy, commit ativo, healthcheck e comando real do serviço **não foram inspecionados**.

## Diagnóstico de startup no código

Em `backend/app/main.py`, `settings.auto_migrate` habilita explicitamente `alembic upgrade head`. **A exceção desse upgrade é relançada**, não silenciada na versão inspecionada. Entretanto, o startup não-development também executa `apply_runtime_schema_patches()` e há tratamento tolerante de erro em bootstrap inicial do tenant e no carregamento do modelo. Essa distinção é importante: não alterar o startup sem inspecionar as variáveis reais, o contrato de saúde e o impacto de remoção dos patches.

## Release controlado — alvo, não configuração já aplicada

1. **Integração:** `main` recebe PR com lint/test/TypeScript/build/pytest/Alembic/RLS e revisão de segurança.
2. **Release candidate:** criar tag/commit imutável e executar QA autenticado em preview/staging. Migrations permanecem separadas.
3. **Banco:** verificar o `alembic_version` real, compatibilidade N-1/N, backups/recuperação e revisão da migration; executar por job dedicado explicitamente aprovado, não por startup do web service.
4. **Publicação:** promover apenas um commit verificado, idealmente com branch `release/production` e aprovação humana, **após autorização específica para alterar Production Branch e Render AutoDeploy**.
5. **Pós-publicação:** monitorar deploy `READY/live`, endpoint de readiness, dependências, logs sanitizados, latência e erros.
6. **Rollback:** promoção da versão frontend anterior ou redeploy backend compatível; **não pressupor rollback automático de migrations ou efeitos financeiros**.

## Bloqueios para migrar a política

- Confirmar workspace Render e inspecionar `mira-api-testes` antes de qualquer trigger, config ou análise de health.
- Verificar Production Branch da Vercel e políticas de deploy em todos os projetos associados ao mesmo repositório.
- Planejar a migração de `main` para `release/production` como mudança operacional aprovada separadamente.
- Decidir onde executar migration dedicada, após validar disponibilidade de job/pre-deploy no plano atual.
- Não usar `alembic upgrade head` contra produção automaticamente apenas para liberar feature.
- Para a Wave 0.4: nenhuma migration nova e nenhum endpoint de mutação, permitindo compatibilidade com schema Alembic 066 já aplicado.

**Limite da evidência:** sucesso de CI ou existência da tabela não substitui QA visual autenticado, teste de isolamento multi-tenant real e observação do serviço Render em execução.
