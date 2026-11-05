# Ícones da MIRA

Toda a aplicação frontend utiliza **Untitled UI Icons**, pacote gratuito `@untitledui/icons@0.0.23` (licença MIT).

- Fonte oficial: https://www.untitledui.com/react/docs/icons
- Adicione novos ícones no arquivo `src/components/ui/icons.tsx`; importe a partir de `@/components/ui/icons`.
- Componentes existentes continuam usando os mesmos nomes históricos, traduzidos para equivalentes Untitled UI pelo adaptador.
- Use classes Tailwind de tamanho (`h-4 w-4`, etc.), herança de cor e `aria-label` no controle interativo. Ícones decorativos devem ter `aria-hidden`.
- A MIRA usa apenas o pacote público MIT, **não** o pacote PRO nem assets privados.
- Atenção: algumas substituições não são semanticamente idênticas; revisar visualmente botões de pausa, importação e painel lateral antes do merge.

Não há alterações no backend ou no envio de mensagens.
