from sqlalchemy.orm import Session
from dao.cv_features_dao import CVFeaturesDAO
from utils import cv_matcher as cm

class CVFeaturesService:
    """Service para extracción y persistencia de features de un CV (texto/skills/embedding)."""

    @staticmethod
    def build_features_from_pdf_bytes(archivo_bytes: bytes) -> tuple[str, list, list[float]]:
        # 1) Leer texto del PDF (bytes)
        texto_raw = cm.read_pdf_text_bytes(archivo_bytes)
        # 2) Normalizar y segmentar en bloques
        texto = cm.normalize_text(texto_raw)
        blocks = cm.split_sections(texto)
        # 3) Skills a partir de bloques
        skills = cm.mine_skills(blocks)
        # 4) Embedding con el texto completo
        emb = cm.get_embedder().encode([texto])[0].tolist()
        return texto, skills, emb

    @staticmethod
    def upsert_from_pdf(db: Session, usuario_id: int, archivo_bytes: bytes):
        texto, skills, emb = CVFeaturesService.build_features_from_pdf_bytes(archivo_bytes)
        return CVFeaturesDAO.upsert(db, usuario_id, texto, skills, emb)
