"""Definição operacional versionada dos rótulos de evasão por tenant."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

TARGET_DEFINITION_VERSION = "evasion_90d_v1"
TARGET_HORIZON = timedelta(days=90)
POSITIVE_OUTCOMES = frozenset({"evadiu", "trancou"})
NEGATIVE_OUTCOMES = frozenset({"ativo", "concluiu", "formou"})
EXCLUDED_OUTCOMES = frozenset({"transferiu"})
SUPPORTED_OUTCOMES = POSITIVE_OUTCOMES | NEGATIVE_OUTCOMES | EXCLUDED_OUTCOMES


def normalize_utc_timestamp(value: datetime) -> datetime:
    """Normaliza timestamps; datas sem fuso são interpretadas como UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def derive_target_label(
    outcome: str, scored_at: datetime, observed_at: datetime | None
) -> tuple[int | None, str]:
    """Rotula a ocorrência de evasão/trancamento nos 90 dias após a pontuação.

    Ativo só vira negativo após 90 dias observados; conclusão/formatura é negativa.
    Transferência é um desfecho concorrente e fica fora do treino.
    """
    outcome_key = outcome.strip().lower()
    if outcome_key not in SUPPORTED_OUTCOMES:
        raise ValueError(f"outcome inválido: {outcome}")
    if outcome_key in EXCLUDED_OUTCOMES:
        return None, "excluded_competing_outcome"
    if observed_at is None:
        return None, "missing_observation_date"

    start = normalize_utc_timestamp(scored_at)
    observed = normalize_utc_timestamp(observed_at)
    if observed < start:
        raise ValueError("observed_at não pode ser anterior a scored_at")

    horizon_end = start + TARGET_HORIZON
    if outcome_key in POSITIVE_OUTCOMES:
        if observed <= horizon_end:
            return 1, "positive_within_90_days"
        return 0, "negative_after_90_days"

    if outcome_key == "ativo" and observed < horizon_end:
        return None, "pending_90_day_observation"
    return 0, "negative_observed"
