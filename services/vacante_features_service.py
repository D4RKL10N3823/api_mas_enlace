import json
from sqlalchemy.orm import Session
from utils import cv_matcher as cm
from dao.vacantes_features_dao import VacanteFeaturesDAO

class VacanteFeaturesService:
    """Service para generar y actualizar los features de una vacante (texto, términos, embedding)."""

    @staticmethod
    def _vacante_text_from_json(datos: dict | str) -> str:
        """Convierte el JSON o string de una vacante en un texto unificado para embeddings."""
        if isinstance(datos, str):
            try:
                datos = json.loads(datos)
            except json.JSONDecodeError:
                return datos  # devolver texto tal cual si no es JSON válido

        campos = [
            "title", "company", "requirements_summary",
            "matched_utc_areas", "modality", "city", "state", "country"
        ]
        parts = []
        for k in campos:
            v = (datos or {}).get(k)
            if isinstance(v, list):
                parts.append(" ".join(map(str, v)))
            elif v:
                parts.append(str(v))
        return "\n".join(parts)

    @staticmethod
    def build_features(datos: dict | str) -> tuple[str, list, list[float]]:
        """Genera jd_text, jd_terms y embedding a partir de los datos de la vacante."""
        jd_text = VacanteFeaturesService._vacante_text_from_json(datos)
        if not jd_text.strip():
            jd_terms, emb = [], []
        else:
            jd_terms = cm.dedup_fuzzy(
                list(set(cm.keyphrases_spacy(jd_text) + cm.keyphrases_rake(jd_text)))
            )
            emb = cm.get_embedder().encode([jd_text])[0].tolist()
        return jd_text, jd_terms, emb

    @staticmethod
    def upsert_from_vacante(db: Session, vacante):
        """Recibe una instancia de Vacante y crea/actualiza su registro en vacante_features."""
        datos = vacante.datos_vacante or {}
        jd_text, jd_terms, emb = VacanteFeaturesService.build_features(datos)
        return VacanteFeaturesDAO.upsert(db, vacante.id, jd_text, jd_terms, emb)

