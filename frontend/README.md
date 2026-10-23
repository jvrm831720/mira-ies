# Mira — Frontend

Interface Next.js da plataforma Mira, com identidade visual baseada em carvão, off-white e índigo, e tipografia Inter. O layout autenticado usa navegação lateral, páginas responsivas e dados carregados pela API com React Query.

## Rodar localmente

Na raiz do repositório, suba banco e Redis; em seguida:

```powershell
cd frontend
npm ci
npm run dev
```

O frontend fica em http://localhost:3000. Por padrão, a API esperada é http://localhost:8000; para alterar, defina `NEXT_PUBLIC_API_URL` no ambiente.

## Verificações

```bash
npm run lint
npm run build
```

O GitHub Actions executa lint e build do frontend além dos testes de backend. O dashboard principal não usa dados de demonstração para métricas: lê os resumos, alunos prioritários, status do modelo, configuração dos agentes e histórico de retenção da API autenticada.

## Dashboard

A visão geral combina indicadores de risco, distribuição da base, fila crítica, atividade de retenção recente e configuração operacional. Quando os endpoints não respondem, a interface apresenta estados de erro e opções para tentar novamente; não substitui falhas por números fictícios. O painel operacional é somente informativo e não dispara comunicações.

## Importação guiada de planilhas

A página `/importar` oferece prévia autenticada antes de persistir qualquer dado, auto-mapeamento determinístico por aliases, edição manual de colunas, alertas de qualidade e um modelo CSV para download. O backend compartilha as regras de limpeza entre prévia e upload. Matrículas existentes são atualizadas apenas dentro da instituição autenticada; células vazias não apagam dados existentes. Nenhuma IA é utilizada nesta etapa.
