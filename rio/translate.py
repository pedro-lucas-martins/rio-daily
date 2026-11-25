"""Free offline Portuguese-to-English translation (Argos model on CTranslate2)."""
import hashlib, io, re, zipfile
from .common import ROOT, get

URL = "https://argos-net.com/v1/translate-pb_en-1_9.argosmodel"
SHA256 = "578e9c504595ac85f8e8e0b31e4f53c84e38e7638db8c3c8df384d05eac2671b"
DIR = ROOT / "models" / "translate-pb_en-1_9"

# Applied to the Portuguese text first: local terms the model gets wrong.
GLOSSARY = [(r"\barrast(ão|ões)\b", "assalto em grupo"), (r"\bsaidinha de banco\b", "assalto após saque bancário"),
            (r"\bbala perdida\b", "bala perdida de tiroteio"), (r"\bPMs\b", "policiais militares"),
            (r"\bPM\b", "Polícia Militar"), (r"\bréveillon\b", "festa de Ano Novo"),
            (r"\bengarrafamento\b", "congestionamento"), (r"\bbalneabilidade\b", "qualidade da água das praias")]
GLOSSARY += [(r"\bressaca\b", "mar agitado"), (r"\btemporal\b", "tempestade"), (r"\btemporais\b", "tempestades"), (r"\bdupla\b", "duas pessoas"), (r"\binédit[oa]\b", "novo"), (r"\binterditad([ao]s?)\b", r"fechad\1")]
# (found in Portuguese, wrong English, right English): place names the model translates.
FIXES = [(r"Central do Brasil", r"Central (do )?(Brazil|Brasil)|Brazil Central", "Central do Brasil"), (r"perseguição", r"persecution", "chase"), (r"(?i:rio)", r"(the )?[Rr]iver", "Rio"), (r"(?i:museu do amanhã)", r"(?i:museum of tomorrow)", "Museum of Tomorrow"),
         (r"Linha Vermelha", r"(the )?Red Line", "Linha Vermelha"), (r"Linha Amarela", r"(the )?Yellow Line", "Linha Amarela"),
         (r"Maré", r"(the )?Tides?", "Maré"), (r"Glória", r"Glory", "Glória"), (r"Lagoa", r"(the )?(Lagoon|Pond|Lake)", "Lagoa"),
         (r"Pão de Açúcar", r"Sugar ?[Bb]read|Sugar Loaf", "Sugarloaf"), (r"Centro", r"(the )?Center", "Centro"),
         (r"Saúde", r"Health", "Saúde"), (r"Penha", r"(the )?Rock", "Penha"), (r"Galeão", r"(the )?Galleon|(the )?Galeon", "Galeão"),
         (r"Cidade de Deus", r"City of God", "Cidade de Deus"), (r"Zona Sul", r"South(ern)? Zone", "South Zone"),
         (r"Lapa", r"(the )?Limpet", "Lapa"), (r"Cristo Redentor", r"Christ the Redeemer|Redeemer Christ", "Christ the Redeemer")]
# Explanations added after English place names.
EXPLAIN = {"Linha Vermelha": "the expressway to the airport", "Linha Amarela": "expressway to Barra",
           "VLT": "light rail", "Galeão": "Rio's international airport"}
_engine = None


def _load():
    global _engine
    if _engine:
        return _engine
    if not DIR.exists():
        blob = get(URL, timeout=300).content
        if hashlib.sha256(blob).hexdigest() != SHA256:
            raise RuntimeError("translation model checksum mismatch")
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for n in z.namelist():
                if ".." in n or n.startswith("/"):
                    raise RuntimeError("unsafe path in model archive")
            z.extractall(DIR.parent)
    import ctranslate2, sentencepiece
    _engine = (ctranslate2.Translator(str(DIR / "model"), device="cpu"),
               sentencepiece.SentencePieceProcessor(model_file=str(DIR / "sentencepiece.model")))
    return _engine


def acceptable(src, out):
    """Reject empty, untranslated, truncated or looping output."""
    words = out.split()
    if len(words) < 3 or out.strip().lower() == src.strip().lower() or "⁇" in out or "<unk>" in out:
        return False
    if not 0.45 <= len(words) / max(len(src.split()), 1) <= 2.2:
        return False
    if any(len(set(words[i:i + 6])) <= 2 for i in range(max(len(words) - 5, 0))):
        return False
    return set(re.findall(r"\d+", src)) <= set(re.findall(r"\d+", out))


def translate(text):
    """English text, or None when the result should not be published."""
    tr, sp = _load()
    src = text
    for pat, rep in GLOSSARY:
        src = re.sub(pat, rep, src, flags=re.I)
    parts = [p for p in re.split(r"(?<=[.!?])\s+", src) if p]
    res = tr.translate_batch([sp.encode(p, out_type=str) for p in parts], beam_size=4, replace_unknowns=True)
    out = " ".join("".join(r.hypotheses[0]).replace("▁", " ").strip() for r in res)
    if not acceptable(src, out):
        return None
    for pt, wrong, right in FIXES:
        if re.search(rf"\b{pt}\b", text):
            out = re.sub(rf"\b({wrong})\b", right, out)
    for name, note in EXPLAIN.items():
        out = re.sub(rf"\b{name}\b", f"{name} ({note})", out, count=1)
    return out[0].upper() + out[1:]
