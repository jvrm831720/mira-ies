"""ML package — imports lazy para facilitar testes unitarios."""
__all__ = ["score_batch", "score_student_dict", "get_model_info"]


def __getattr__(name: str):
    if name in ("score_batch", "score_student_dict", "get_model_info"):
        from app.ml import scoring
        return getattr(scoring, name)
    raise AttributeError(name)
