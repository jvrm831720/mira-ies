# MIRA — Demo para investidores | 6 de novembro de 2026

**Modo de demonstração com dados 100% sintéticos.**
Não usa conexão com API, Supabase, Frappe, ERPNext ou dados de alunos reais.
Toda interação ocorre no navegador; recarregar a página reinicia as ações.

## Publicar gratuitamente na sua conta Cloudflare

A publicação **não depende do Vercel, Render, Docker, GitHub Actions
ou token de API**.

1. Entre em https://dash.cloudflare.com/ com a sua conta.
2. Abra **Workers & Pages** → **Create application** → **Pages** →
   **Connect to Git** (os nomes podem variar ligeiramente).
3. Autorize o acesso do Cloudflare Pages ao repositório GitHub
   `jvrm831720/mira-ies`, se ainda não estiver conectado.
4. Selecione o repositório **mira-ies**.
5. Configure:

   | Campo | Valor |
   |---|---|
   | Project name | `mira-investidores` |
   | Production branch | `demo/mira-investidores-cloudflare-20261106` |
   | Root directory | `demo-investidores` |
   | Framework preset | `None` ou `No framework` |
   | Build command | `exit 0` (se for obrigatório; senão, deixe vazio) |
   | Build output directory | `.` |
   | Environment variables | **Nenhuma** |

6. Clique em **Save and Deploy**.
7. Abra a URL `*.pages.dev` efetivamente retornada pela Cloudflare.
   Não invente uma URL antes da primeira publicação.
8. Valide **Visão geral**, **Alunos**, busca e filtros,
   **ficha do aluno**, **Intervenções**, **Resultados** e **Dados e integrações**
   no computador e no celular.

Se o painel oferecer apenas **Workers** ou pedir uma integração
de framework, volte e escolha a opção **Pages (static assets)**.
Esta demonstração usa apenas HTML, CSS e JavaScript, **não**
precisa de OpenNext, Next.js runtime, banco, tokens ou build Node.

## Roteiro de apresentação (aprox. 5 minutos)

1. **Visão geral:** explique o problema de evasão com sinais
   financeiros, acadêmicos e de engajamento; apresente o painel.
2. **Alunos:** abra a ficha da estudante fictícia Marina Oliveira,
   mostre evidências e contexto; o risco aqui é ilustrativo.
3. **Central de trabalho / Intervenções:** planeje uma intervenção
   simulada, demonstre atribuição e acompanhamento sem disparo real.
4. **Resultados:** explique a diferença entre fazer contato e
   **verificar** se a ação ajudou.
5. **Dados e integrações:** apresente a arquitetura de integração
   MIRA/FastAPI com sistemas institucionais; Frappe/ERPNext/Education
   está **em homologação**, não implantado nesta demonstração.

O botão **Ver demonstração guiada** na Visão geral avança por
essas cinco telas, fornecendo uma orientação a cada clique.

## O que a demo comprova e o que não comprova

- Comprova: navegação, interface, responsividade,
  filtros, ficha de aluno fictício e fluxo de intervenção
  simulada no navegador.
- **Não comprova**: cálculo de risco calibrado, qualidade de
  predição, integração com Frappe em produção, compliance,
  comunicação real, cobrança, Pix, sincronização de dados,
  economia observada, retenção verificada em clientes ou SLA.
- **Não é** a aplicação multi-tenant autenticada MIRA.
- Não mostrar os números inventados como indicadores reais
  ou resultados comerciais.
- O domínio pages.dev resultante é público para quem
  possuir o link; não inserir dados sensíveis.

## Por que Pages e não o frontend inteiro em Workers neste momento?

O frontend Next.js real já tem adaptador OpenNext em
`frontend/open-next.config.ts` e configuração `wrangler.jsonc`.
Esse deploy exige validação de build, compatibilidade e limites de CPU,
memória e tamanho da Cloudflare Workers Free, além do
proxy `/api/v1`. GitHub Actions está limitado e a
Vercel atingiu limite de deployments.

Este projeto estático é uma **contingência para 6 de novembro**;
não altera `main`, o frontend Vercel, Render nem a API MIRA.

Fontes de infraestrutura:
- https://developers.cloudflare.com/pages/framework-guides/nextjs/
- https://developers.cloudflare.com/pages/configuration/build-configuration/
- https://developers.cloudflare.com/workers/platform/limits/

## Segurança

Nunca cadastre valores reais, chaves ou tokens na demo.
Ela não executa `fetch`, não cria cookies, não usa
`localStorage`/`sessionStorage`, não modifica o backend e não
envia mensagens. Há aviso visível de dados fictícios em todas as telas.
