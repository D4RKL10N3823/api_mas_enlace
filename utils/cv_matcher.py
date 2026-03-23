import re, pickle, numpy as np
import nltk
from pathlib import Path
from unidecode import unidecode
from pypdf import PdfReader
from pdfminer.high_level import extract_text as pdfminer_text
from rake_nltk import Rake
from rapidfuzz import process, fuzz
import spacy
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, util
from io import BytesIO

_nlp = None

def get_nlp():
    global _nlp
    if _nlp is None:
        import spacy
        try:
            _nlp = spacy.load("es_core_news_sm")
        except OSError:
            import spacy.cli
            spacy.cli.download("es_core_news_sm")
            _nlp = spacy.load("es_core_news_sm")
    return _nlp

_EMB = None

def get_embedder():
    global _EMB
    if _EMB is None:
        from sentence_transformers import SentenceTransformer
        _EMB = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    return _EMB

SEC_PATTERNS = [
    (r'(?im)^(experiencia|laboral|trayectoria)\b', 'experiencia'),
    (r'(?im)^(educaci[oó]n|estudios|formaci[oó]n)\b', 'educacion'),
    (r'(?im)^(habilidades|skills|competencias)\b', 'habilidades'),
    (r'(?im)^(certificaciones?|cursos|capacitaci[oó]n)\b', 'certificaciones'),
    (r'(?im)^(proyectos?|portafolio|portfolio)\b', 'proyectos'),
    (r'(?im)^(perfil|resumen|about)\b', 'perfil'),
]

BANWORDS = {unidecode(w.lower()) for w in {
  "experiencia","experiencia laboral","educación","formación","estudios",
  "habilidades","skills","competencias","certificaciones","cursos","perfil","resumen",
  "objetivo","funciones","responsabilidades","actividades","requisitos","otros",
  "proyectos","portafolio","portfolio","contacto","datos","referencias",
  "conocimiento","conocimientos","manejo","uso","experto","intermedio","básico",
  "excelente","avanzado","principiante","años","año"
}}
ALIASES = {
    "js":"javascript","node js":"node.js","nodejs":"node.js",
    "ms excel":"excel","ms word":"word","ms powerpoint":"powerpoint"
}


def ensure_nltk_data():
    """
    Verifica y descarga automáticamente recursos NLTK, checando la ruta adecuada
    para cada paquete (corpora / tokenizers / taggers).
    """
    paths = {
        "stopwords": "corpora/stopwords",
        "punkt": "tokenizers/punkt",
        "punkt_tab": "tokenizers/punkt_tab",
        "wordnet": "corpora/wordnet",
        "omw-1.4": "corpora/omw-1.4",
        "averaged_perceptron_tagger": "taggers/averaged_perceptron_tagger",
    }
    for pkg, path in paths.items():
        try:
            nltk.data.find(path)
        except Exception:
            try:
                print(f"📦 Descargando NLTK: {pkg}")
                nltk.download(pkg, quiet=True)
            except Exception as e:
                print(f"⚠️ No se pudo descargar {pkg}: {e}")

# Ejecuta al importar
ensure_nltk_data()


# ---------- helpers de texto ----------
def read_pdf_text(fp: Path) -> str:
    try:
        r = PdfReader(str(fp))
        txt = "\n".join(p.extract_text() or "" for p in r.pages)
        if not txt.strip(): raise ValueError("empty")
        return txt
    except Exception:
        return pdfminer_text(str(fp)) or ""

def normalize_text(s: str) -> str:
    s = s.replace('\x00','').replace('\ufeff','')
    return s.replace('•','- ').replace('·','- ').replace('●','- ')

def split_sections(text: str):
    lines = [ln.strip() for ln in text.splitlines()]
    blocks, current = [], {"title": "otros", "lines": []}
    def flush():
        if current["lines"]:
            blocks.append({"title": current["title"], "text": "\n".join(current["lines"]).strip()})
            current["lines"].clear()
    for ln in lines:
        found = False
        for pat, tag in SEC_PATTERNS:
            if re.search(pat, ln):
                flush(); current["title"] = tag; found = True; break
        if not found: current["lines"].append(ln)
    flush(); return blocks

def normalize_skill(s) -> str:
    if s is None: return ""
    if not isinstance(s, str): s = str(s)
    s = unidecode(s.lower().strip())
    s = re.sub(r'[^a-z0-9#+.\- áéíóúñ/]','', s)
    s = re.sub(r'\s+',' ',s)
    return ALIASES.get(s, s)

def is_good_phrase(p: str) -> bool:
    if not p or p in BANWORDS: return False
    if len(p) < 3: return False
    if not re.search(r"[a-záéíóúñ]", p): return False
    if " " not in p:
        return p in {"excel","linux","windows","python","java","javascript","sql","kotlin","swift","react","docker","aws","azure","gcp"}
    return True

def keyphrases_spacy(text: str):
    nlp = get_nlp()
    doc = nlp(text)
    cands = set()
    for ch in doc.noun_chunks:
        p = normalize_skill(ch.text)
        if is_good_phrase(p): cands.add(p)
    for m in re.finditer(r"(?i)\b(gesti[oó]n|atenci[oó]n|soporte|administraci[oó]n)\s+(de|a)\s+[a-z0-9 áéíóúñ/+\-.]{3,}", text):
        p = normalize_skill(m.group(0))
        if is_good_phrase(p): cands.add(p)
    return list(cands)

def keyphrases_rake(text: str):
    r = Rake(language='spanish'); r.extract_keywords_from_text(text)
    out=[]
    for score, phrase in r.get_ranked_phrases_with_scores():
        p = normalize_skill(phrase)
        if is_good_phrase(p): out.append(p)
    return out

def dedup_fuzzy(phrases, threshold=88):
    canon=[]
    for c in phrases:
        if not canon: canon.append(c); continue
        m = process.extractOne(c, canon, scorer=fuzz.token_set_ratio)
        if not m or m[1] < threshold: canon.append(c)
    return canon

def mine_skills(blocks):
    weighted = []
    for b in blocks:
        # usa enteros 2/2/1 como refuerzo real de texto
        w = 2 if b["title"] == "habilidades" else 2 if b["title"] == "experiencia" else 1
        if b["text"]:
            weighted.append((b["text"] + "\n") * w)
    txt = "\n".join(weighted)
    merged = dedup_fuzzy(list(set(keyphrases_spacy(txt) + keyphrases_rake(txt))))
    merged = [p for p in merged if p not in BANWORDS and is_good_phrase(p)]
    return merged[:200]

def extract_jd_terms(jd_text: str):
    return dedup_fuzzy(list(set(keyphrases_spacy(jd_text) + keyphrases_rake(jd_text))))

def pretty_overlap(cv_terms, jd_terms, top=10):
    hits=[]
    for s in cv_terms:
        m = process.extractOne(s, jd_terms, scorer=fuzz.token_set_ratio)
        if m and m[1] >= 90: hits.append(s)
    return hits[:top]

# ---------- embeddings / índice ----------
def prepare_index(cvs):
    texts=[]
    for cv in cvs:
        parts=[]
        for b in cv["blocks"]:
            w = 1.4 if b["title"]=="experiencia" else 1.3 if b["title"]=="habilidades" else 1.1 if b["title"]=="educacion" else 1.0
            parts.append((b["text"]+"\n")*int(w))
        texts.append("\n".join(parts))

    bm25 = BM25Okapi([t.lower().split() for t in texts])
    EMB = get_embedder()
    embs = EMB.encode([f"passage: {t}" for t in texts], normalize_embeddings=True)
    return {"bm25": bm25, "embs": embs, "texts": texts}

def overlap_score(cv_terms, jd_terms):
    scr = 0.0
    for s in cv_terms:
        m = process.extractOne(s, jd_terms, scorer=fuzz.token_set_ratio)
        if m and m[1] >= 90:
            scr += 1.0 if " " in s else 0.6
    return scr

def hybrid_rank(jd_text, index, topk=5, alpha=0.5, beta=0.25, gamma=0.25,
                cv_skill_list=None, jd_terms_list=None):
    EMB = get_embedder()
    q_emb = EMB.encode(f"query: {jd_text}", normalize_embeddings=True)
    cos = util.cos_sim(q_emb, index["embs"]).cpu().numpy().ravel()
    bm  = index["bm25"].get_scores(jd_text.lower().split())

    ol = np.zeros_like(cos)
    if cv_skill_list is not None and jd_terms_list is not None:
        ol_raw = np.array([overlap_score(cv_skill_list, terms) for terms in jd_terms_list], dtype=float)
        if ol_raw.max() > 0:
            ol = (ol_raw - ol_raw.min()) / (ol_raw.max() - ol_raw.min() + 1e-9)

    cos_n = (cos - cos.min()) / (cos.max() - cos.min() + 1e-9)
    bm_n  = (bm  - bm.min())  / (bm.max()  - bm.min()  + 1e-9)

    final = alpha * cos_n + beta * bm_n + gamma * ol
    order = np.argsort(-final)[:topk]
    return order, final[order], cos[order], bm[order], ol[order]


# ---------- serialización ----------
def save_index(path: Path, cvs, index, cv_skill_list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump({"cvs": cvs, "index": index, "cv_skill_list": cv_skill_list}, f)

def load_index(path: Path):
    with open(path, "rb") as f:
        data = pickle.load(f)
    return data["cvs"], data["index"], data["cv_skill_list"]

def read_pdf_text_bytes(b: bytes) -> str:
    """Extrae texto de un PDF en bytes (bytea) sin tocar disco."""
    try:
        from pypdf import PdfReader
        pdf = PdfReader(BytesIO(b))
        txt = "\n".join(p.extract_text() or "" for p in pdf.pages)
        if txt.strip():
            return txt
    except Exception:
        pass
    # fallback: pdfminer
    from pdfminer.high_level import extract_text_to_fp
    bio_in, bio_out = BytesIO(b), BytesIO()
    extract_text_to_fp(bio_in, bio_out)
    return bio_out.getvalue().decode("utf-8", errors="ignore")

def build_vacante_index(vacantes: list):
    """
    vacantes: [{"id": str, "text": str}, ...]
    Crea índice híbrido para TODAS las vacantes y también sus 'terms'.
    """
    jd_terms_list = []
    for v in vacantes:
        terms = dedup_fuzzy(list(set(keyphrases_spacy(v["text"]) + keyphrases_rake(v["text"]))))
        jd_terms_list.append(terms)
    # reusa prepare_index, empaquetando cada vacante como un único bloque
    idx = prepare_index([{"blocks":[{"title":"otros","text":v["text"]}]} for v in vacantes])
    return idx, jd_terms_list
