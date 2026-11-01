export function signalStatusPresentation(status) {
  switch (status) {
    case "TRUE":
      return {
        label: "Confirmado",
        explanation: "O backend confirmou este sinal.",
        tone: "success",
      };
    case "FALSE":
      return {
        label: "Não confirmado",
        explanation: "O backend não confirmou este sinal.",
        tone: "muted",
      };
    case "INDETERMINATE":
      return {
        label: "Dados insuficientes",
        explanation: "A API não retornou dados suficientes para avaliar este sinal.",
        tone: "warning",
      };
    default:
      return {
        label: "Estado desconhecido",
        explanation: "A resposta não contém um estado de sinal reconhecido.",
        tone: "warning",
      };
  }
}

export function cursorErrorKind(status) {
  if (status === 400) return "invalid";
  if (status === 410) return "expired";
  return null;
}

export function hasCursorContinuation(page) {
  return Boolean(
    page &&
      typeof page.next_cursor === "string" &&
      page.next_cursor.length > 0
  );
}
