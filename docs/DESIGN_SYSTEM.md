# MIRA Design System

**Status:** fonte de verdade · alinhado ao Login + referência Attio  
**Última atualização:** 2026-11-05  
**Princípio:** evoluir sem big bang. Auth (Login/Onboarding) e produto (shell autenticado) compartilham a mesma linguagem, mas com superfícies distintas.

---

## 1. Duas superfícies, uma linguagem

| Superfície | Uso | Base | Primary action |
|------------|-----|------|----------------|
| **Auth** (Login, onboarding conversacional, portal do pagador) | Pré-auth e experiências públicas | Dark Attio (`#101112`) | Azul `#3577f1` (já implementado no Login) |
| **Product** (shell autenticado, home, ficha, cobrança, dados) | Operação diária | Light Attio (paper white + ink) | Near-black elevado + azul MIRA como accent de foco/link |

O **Login** (`frontend/src/app/(auth)/login/page.tsx` + CSS `.auth-login-*`) é a referência canônica de composição, tipografia, radius, estados de erro e botões para qualquer tela de autenticação ou onboarding. Não reinventar.

A referência Attio light (tokens abaixo) governa o produto autenticado e os tags/status de dados.

---

## 2. Tokens de cor — Product (light)

### Neutros / Ink
| Token | Valor | Uso |
|-------|-------|-----|
| `--color-ink` | `#101112` | Texto principal, headings |
| `--color-ink-900` | `#232529` | Headings densos |
| `--color-slate-600` | `#505967` | Texto secundário, nav ativa |
| `--color-muted` | `#75777C` | Placeholder, metadata |
| `--color-faint` | `#9FA1A7` | Disabled, timestamps |
| `--color-border` | `#E6E7EA` | Borda padrão de card |
| `--color-border-subtle` | `#EEEFF1` | Divisores leves, row hover |
| `--color-panel` | `#F8F9FA` | Painéis rebaixados, table header |
| `--color-surface-raised` | `#FBFBFB` | Card elevado |
| `--color-canvas` | `#FFFFFF` | Fundo de página e card |

### Brand & Interactive
| Token | Valor | Uso |
|-------|-------|-----|
| `--color-blue` / `--brand-blue-attio` | `#266DF0` | Links, focus, selected (Attio) |
| `--brand-indigo` | `#4050CD` | Accent MIRA de foco/ação no produto (já existente) |
| `--auth-blue` | `#3577f1` | Primary do Login / onboarding |

### Semantic tags (só para dados — nunca para CTA)
| Família | Ink | Tint | Border |
|---------|-----|------|--------|
| Green (sucesso / positivo) | `#007D53` | `#E0FCED` | `#CBF7E1` |
| Blue (info) | `#006699` | `#E5EEFF` | `#D6E5FF` |
| Purple | `#6238B5` | `#F5F0FF` | `#E8DDFE` |
| Peach (aviso) | — | `#FEEEE1` | `#FEE0C8` |
| Red (risco / negativo) | `#772322` | — | `#FEE7E7` |

**Regra de ouro Attio:** accents coloridos são para **tags e status de dados**. Primary actions são near-black (ou azul no escopo Auth).

---

## 3. Tokens de cor — Auth (dark, já no Login)

```css
--auth-bg: #101112;
--auth-panel: #101112;
--auth-panel-contrast: #11151d;
--auth-border: #292c32;
--auth-text: #f1f2f3;
--auth-muted: #a0a3aa;
--auth-subtle: #858a93;
--auth-blue: #3577f1;
```

Inputs: fundo `#14161a`, borda `#34373e`.  
Erro: fundo `#29181d`, borda `#66323d`, texto `#f3a4ae`.

---

## 4. Tipografia

- **UI / body:** Inter (ou Geist / system-ui) — peso padrão 500 para labels, botões e links.
- **Display / headings:** tracking negativo (-0.02em a -0.03em), peso 600.
- **Editorial (quotes):** Georgia / Tiempos Text italic (já usado no depoimento do Login).
- **Dados / mono:** JetBrains Mono ou ui-monospace.

Escala de referência (Attio):
- Body: 14–16px
- Label: 12–14px / 500
- Heading MD: 24–32px
- Micro: 11–12px

---

## 5. Radius, spacing, elevation

| Elemento | Radius |
|----------|--------|
| Chip / tag | 5–6px |
| Button / input (Auth) | 7px (Login atual) |
| Button / input (Product) | 10px (Attio) |
| Card | 12px |
| Large panel | 16–20px |
| Pill | 999px |

**Shadows (whisper, blue-tinted):**
- Card: `rgba(0, 22, 62, 0.04) 0 4px 12px -1px, rgba(0, 22, 62, 0.18) 0 1px 3px -1px`
- Focus: soft 4px blue ring (`rgba(83, 139, 243, 0.1)`)
- Primary button (product): inset white highlight + soft dark drop (Attio)

Spacing base: 4px. Densidade comfortable-compact.

---

## 6. Componentes — regras

### Primary Button
- **Auth:** azul `#3577f1` sólido (Login).
- **Product:** near-black elevado (`#101112` → charcoal), texto branco, radius 10px, sombra inset Attio. Azul MIRA só quando a ação for de “foco/decisão” explícita do domínio.

### Secondary / Outline
- White / surface + hairline border. Hover escurece a borda.

### Tag / Status Pill
- Sempre o contrato de 3 partes: ink + tint + border da família semântica.
- Nunca usar tag colorida como botão de ação.

### Input
- White (product) ou `#14161a` (auth).
- Focus: ring azul suave, nunca outline duro.

### Card / Surface
- Hairline border + sombra micro. Profundidade por luminância, não por sombra pesada.

### Empty states
- Explicar o que falta + CTA óbvio (“Importar dados”, “Limpar filtros”, “Solicitar acesso”).
- Nunca inventar score ou dado.

---

## 7. Do’s & Don’ts

**Do**
- Texto de corpo em `#101112`, nunca pure black.
- Tags com contrato completo de 3 partes.
- Radius consistente (10px product / 7px auth).
- Elevação com micro-shadows blue-tinted.
- `#266DF0` / `#4050CD` só para link, focus e selected.

**Don’t**
- Colorir CTAs de produto com tags (green/red/purple).
- Sombras pesadas ou escuras.
- Serif em UI (só editorial).
- Fundo tintado no canvas (exceto gradiente hero suave).
- Misturar famílias de tag sem significado semântico.

---

## 8. Implementação no repositório

- Tokens vivos: `frontend/src/app/globals.css` (`:root` + `.auth-login-page`).
- Componentes base: `frontend/src/components/ui/*`.
- Login é a referência viva de Auth — qualquer tela de onboarding deve reutilizar as classes `.auth-login-*` ou extrair para um escopo `.auth-surface`.
- Product shell continua com `.mira-page` e tokens `--surface-*` / `--brand-indigo`.

Quando criar o onboarding conversacional (Blueprint §5), usar a superfície Auth (dark + azul) e a prévia viva na coluna direita no mesmo espírito do Login.

---

## 9. Próximos passos de design system

1. Extrair `.auth-surface` reutilizável a partir do Login (para onboarding e portal).
2. Atualizar `Button` product variants para near-black Attio + radius 10px (manter compatibilidade).
3. Criar componente `Tag` / `StatusPill` com as 5 famílias.
4. Unificar empty states e focus rings.
5. Documentar tokens no Storybook ou página interna quando existir.
