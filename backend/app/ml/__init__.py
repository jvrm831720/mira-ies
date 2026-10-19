"""Motor Preditivo de Risco — Project Beacon XGBoost + SHAP"""

from app.ml.scoring import score_batch, score_student_dict, get_model_info

__all__ = ["score_batch", "score_student_dict", "get_model_info"]
