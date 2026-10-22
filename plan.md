# Plano de melhoria UX/UI — MIRA

## Direção escolhida

**Movimento:** editorial SaaS premium inspirado em galerias e templates independentes do Dark Design.

**Princípios:** hierarquia visual forte; conteúdo escaneável em poucos segundos; contraste funcional entre contexto, risco e ação; superfícies com poucos contornos e estados vazios orientados à próxima tarefa.

**Filosofia de cor:** base quente e quase branca para reduzir fadiga; carvão na navegação para criar uma âncora de produto; azul elétrico como assinatura de decisão; coral apenas para risco crítico.

**Paradigma de layout:** shell assimétrico com navegação fixa e conteúdo em coluna editorial, usando blocos largos de contexto e módulos menores de decisão em vez de uma grade homogênea de cards.

**Elementos de assinatura:** sidebar carvão com marcador azul de item ativo; títulos grandes e compactos; chips de estado com fundo tonal; bloco de prioridade com destaque cromático e CTA direto.

**Interação:** cada ação deve ter feedback imediato, foco visível, alvo confortável no mobile e texto que explique a consequência. Estados vazios devem orientar o próximo passo, não apenas informar ausência de dados.

**Animação:** transições curtas de 160–220ms; elevação sutil no hover; skeletons discretos; respeitar `prefers-reduced-motion`.

**Tipografia:** Geist/Sans para leitura e números tabulares; tracking levemente negativo em títulos; labels auxiliares em caixa alta com tracking amplo.

**Essência da marca:** MIRA transforma sinais acadêmicos em decisões humanas de permanência. Personalidade: lúcida, cuidadosa, acionável.

**Voz:** direta e acolhedora. Exemplos: “Comece por quem precisa de atenção hoje.” e “Importe a base para transformar dados em próximos passos.”

**Wordmark:** preservar o wordmark MIRA existente e usá-lo como assinatura de navegação, sem reconstruí-lo em tipografia genérica.

**Cor proprietária:** azul elétrico `#4050CD`, usado em foco, seleção e CTA de decisão.

## Implementação

- Atualizar tokens globais e textura de fundo sem mudar a API.
- Reestruturar sidebar e header para reforçar organização ativa, navegação e conta.
- Melhorar a home com bloco de prioridade, busca mais clara, ações rápidas com contexto e estados vazios acionáveis.
- Refinar KPI, distribuição de risco e lista crítica com contraste, densidade e hierarquia melhores.
- Validar lint e build do frontend.
