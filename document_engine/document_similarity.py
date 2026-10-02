"""SmartBuy document comparison v2. Pure Python, deterministic, no network.

Similarity is a triage signal, never proof of ownership/conformity or permission
to delete/replace a document. Existing public function names are preserved.
"""
from __future__ import annotations
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import math
import re
import unicodedata
from typing import Any

VERSION = "2.0"
MAX_TEXT_CHARS = 200_000
MAX_STRUCTURE_ITEMS = 4_000
MAX_CADASTRAL_UNITS = 200
_HASH_KEYS = ("sha256", "content_sha256", "checksum_sha256", "file_sha256")
_EMPTY_HASH = hashlib.sha256(b"").hexdigest()
_TECHNICAL = {
    "id", "document_id", "property_id", "fascicolo_id", "agente_id", "user_id", "tenant_id",
    "filename", "file_name", "storage_path", "url", "signed_url", "created_at", "updated_at",
    "processed_at", "processing_time_seconds", "confidence", "confidence_score", "fonte",
    "source_text", "source_page", "page", "evidence_ids", "model_name", "organization",
    "sha256", "content_sha256", "checksum_sha256", "file_sha256",
}
_ALIASES = {
    "atto_provenienza": "atto_compravendita", "atto_notarile": "atto_compravendita",
    "planimetria": "planimetria_catastale",
}
_FIELDS = {
    "categoria": ("categoria", "categoria_catastale"),
    "classe_energetica": ("classe_energetica", "energy_class"),
    "intestatari": ("intestatari", "proprietari", "owners"),
    "codici_fiscali": ("codici_fiscali", "codice_fiscale", "tax_code"),
    "superficie_utile": ("superficie_utile_mq",),
    "superficie_commerciale": ("superficie_commerciale_mq",),
    "prezzo": ("prezzo_eur", "prezzo_compravendita_eur"),
}
_CATEGORIES = {f"{group}/{i}" for group, limit in {"A":11,"B":8,"C":7,"D":10,"E":9,"F":7}.items()
               for i in range(1,limit+1)}


def calculate_file_hash(content: bytes) -> str:
    if not isinstance(content, (bytes, bytearray, memoryview)):
        raise TypeError("content must be bytes")
    return hashlib.sha256(content).hexdigest()


def _text(value):
    if not isinstance(value, str):
        return ""
    value = unicodedata.normalize("NFKC", value).casefold()
    # Join only alphabetic line-break hyphenation, never numeric identifiers.
    value = re.sub(r"(?<=[^\W\d_])-\s*\n\s*(?=[^\W\d_])", "", value)
    return " ".join(re.findall(r"\w+|[.,/]", value, flags=re.UNICODE))


def _dice(a, b):
    total = sum(a.values()) + sum(b.values())
    return 2 * sum((a & b).values()) / total if total else 0.0


def _text_analysis(a, b):
    valid = isinstance(a, str) and isinstance(b, str) and bool(a.strip() and b.strip())
    if not valid:
        return {"available":False, "score":0.0, "limited":False, "substantial":False, "numeric_changes":False}
    if max(len(a),len(b)) > MAX_TEXT_CHARS:
        # Never compare only a prefix and classify unseen suffixes as duplicates.
        return {"available":False, "score":0.0, "limited":True, "substantial":False, "numeric_changes":False}
    x,y = _text(a),_text(b)
    wx,wy = x.split(),y.split()
    words = _dice(Counter(zip(wx,wx[1:])),Counter(zip(wy,wy[1:])))
    chars = _dice(Counter(x[i:i+4] for i in range(max(0,len(x)-3))),
                  Counter(y[i:i+4] for i in range(max(0,len(y)-3))))
    score = 1.0 if x and x==y else .65*words + .35*chars
    return {"available":bool(x and y), "score":round(score,4), "limited":False,
            "substantial":min(len(wx),len(wy))>=20 and min(len(set(wx)),len(set(wy)))>=8,
            "numeric_changes":Counter(re.findall(r"\d+(?:[.,/]\d+)*",x)) !=
                              Counter(re.findall(r"\d+(?:[.,/]\d+)*",y))}


def calculate_text_similarity(text_a: str, text_b: str) -> float:
    """Bounded, symmetric token/character similarity; no quadratic SequenceMatcher."""
    return round(_text_analysis(text_a,text_b)["score"],3)


def _unwrap(value):
    if isinstance(value,dict):
        if "valore" in value: return value["valore"]
        if "value" in value: return value["value"]
    return value


def _canonical(value, budget=None, depth=0):
    if budget is None: budget=[MAX_STRUCTURE_ITEMS,MAX_TEXT_CHARS]
    budget[0]-=1
    if budget[0]<0 or depth>12:
        raise ValueError("Structured input exceeds comparison limits")
    value=_unwrap(value)
    if value is None: return None
    if isinstance(value,str):
        budget[1]-=len(value)
        if budget[1]<0: raise ValueError("Structured text exceeds total comparison budget")
        return ("text",_text(value)) if value.strip() else None
    if isinstance(value,bool): return ("bool",value)
    if isinstance(value,(int,float)):
        return ("number",value) if math.isfinite(value) else None
    if isinstance(value,dict):
        if len(value)>MAX_STRUCTURE_ITEMS: raise ValueError("Too many fields")
        pairs=[]
        for key,raw in value.items():
            if not isinstance(key,str) or key.casefold() in _TECHNICAL: continue
            item=_canonical(raw,budget,depth+1)
            if item is not None: pairs.append((key.casefold(),item))
        return ("object",tuple(sorted(pairs))) if pairs else None
    if isinstance(value,(list,tuple)):
        if len(value)>MAX_STRUCTURE_ITEMS: raise ValueError("Too many values")
        items=[_canonical(v,budget,depth+1) for v in value]
        items=[v for v in items if v is not None]
        return ("list",tuple(sorted(items,key=repr))) if items else None
    return None


def _metadata_detail(a,b):
    if not isinstance(a,dict) or not isinstance(b,dict): return {"score":0.0,"shared":0,"union":0}
    ca,cb=_canonical(a),_canonical(b)
    x=dict(ca[1]) if ca and ca[0]=="object" else {}
    y=dict(cb[1]) if cb and cb[0]=="object" else {}
    union=x.keys() | y.keys()
    shared=x.keys() & y.keys()
    return {"score":sum(x[k]==y[k] for k in shared)/len(union) if union else 0.0,
            "shared":len(shared),"union":len(union)}


def compare_metadata(metadata_a: dict[str, Any], metadata_b: dict[str, Any]) -> float:
    """Compare meaningful fields over their union; absent/empty fields never match."""
    return round(_metadata_detail(metadata_a,metadata_b)["score"],3)


def _fields(doc):
    result={}
    for name in ("metadata","extracted_fields"):
        value=doc.get(name)
        if isinstance(value,dict): result.update(value)
    return result


def _known(value):
    value=_unwrap(value)
    if value is None or isinstance(value,bool): return None
    if isinstance(value,str) and len(value)>2048: return None
    return str(value).strip() or None if isinstance(value,(str,int)) else None


def _identifier(value):
    text=_known(value)
    if not text: return None
    text=unicodedata.normalize("NFKC",text).strip().upper()
    return str(int(text)) if text.isdecimal() else text


def _hash(doc):
    found=set()
    invalid=False
    for key in _HASH_KEYS:
        value=doc.get(key)
        if value in (None,""): continue
        if not isinstance(value,str) or not re.fullmatch(r"[a-fA-F0-9]{64}",value.strip()):
            invalid=True
        elif value.strip().lower()==_EMPTY_HASH:
            invalid=True
        else: found.add(value.strip().lower())
    return (next(iter(found)) if len(found)==1 and not invalid else None,
            invalid or len(found)>1)


def _kind(doc):
    value=_known(doc.get("document_type"))
    if not value: return None
    value=value.casefold().strip()
    if value in {"altro","unknown","document","none"}: return None
    return _ALIASES.get(value,value)


def _category(value):
    value=_known(value)
    if not value: return None
    match=re.fullmatch(r"([A-Fa-f])\s*[/ -]?\s*0*(\d{1,2})",value)
    result=f"{match[1].upper()}/{int(match[2])}" if match else None
    return result if result in _CATEGORIES else None


def _units(doc):
    fields=_fields(doc)
    raw=_unwrap(fields.get("riferimenti_catastali",fields.get("riferimento_catastale")))
    if raw is None and any(k in fields for k in ("foglio","particella","mappale")): raw=fields
    records=raw if isinstance(raw,list) else [raw] if isinstance(raw,dict) else []
    if len(records)>MAX_CADASTRAL_UNITS: raise ValueError("Too many cadastral units")
    result={}
    incomplete=False
    for row in records:
        if not isinstance(row,dict): incomplete=True; continue
        # Codes and names are separate namespaces: do not guess a municipal code from a name.
        code=_identifier(row.get("codice_comune") or row.get("comune_catastale"))
        valid_code=bool(code and re.fullmatch(r"[A-Z][0-9]{3}",code))
        comune=("code",code) if valid_code else ("name",_text(_known(row.get("comune")) or code or ""))
        parts=(_identifier(row.get("foglio")), _identifier(row.get("particella",row.get("mappale"))),
               _identifier(row.get("subalterno")))
        if not comune[1] or not all(parts): incomplete=True; continue
        key=(comune,_identifier(row.get("sezione")) or "",*parts)
        result.setdefault(key,set())
        cat=_category(row.get("categoria"))
        if cat: result[key].add(cat)
    return result,incomplete


def _scope(a,b):
    simulated=[]
    for doc in (a,b):
        metadata=doc.get("metadata") if isinstance(doc.get("metadata"),dict) else {}
        markers=[doc.get("environment"),doc.get("source_mode"),
                 metadata.get("environment"),metadata.get("source_mode")]
        simulated.append(any(isinstance(v,str) and v.casefold() in
                             {"sandbox","test","fixture","simulation","simulated","demo"} for v in markers))
    if simulated[0]!=simulated[1]: return "out_of_scope"
    for aliases in (("property_id","fascicolo_id"),("user_id","agente_id"),("tenant_id",)):
        x={v for k in aliases if (v:=_identifier(a.get(k))) is not None}
        y={v for k in aliases if (v:=_identifier(b.get(k))) is not None}
        if len(x)>1 or len(y)>1: return "inconsistent"
        if x and y and x!=y: return "out_of_scope"
    return "compatible_or_unknown"


def _number(value):
    if isinstance(value,bool) or value is None: return None
    if isinstance(value,(int,float,Decimal)):
        try:
            result=Decimal(str(value))
            return result if result.is_finite() else None
        except InvalidOperation: return None
    if not isinstance(value,str): return None
    raw=value.strip().casefold().replace("€","").replace("eur","").strip()
    raw=re.sub(r"\s*(mq|m²|m2)\s*$","",raw).strip().replace(" ","")
    if not re.fullmatch(r"-?\d+(?:[.,]\d+)*",raw): return None
    if "," in raw and "." in raw:
        if raw.rfind(",")>raw.rfind("."): raw=raw.replace(".","").replace(",",".")
        else: raw=raw.replace(",","")
    elif "," in raw:
        if raw.count(",")>1: return None
        raw=raw.replace(",",".")
    elif raw.count(".")>1:
        if not re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+",raw): return None
        raw=raw.replace(".","")
    elif "." in raw and len(raw.split(".")[1])==3:
        # Locale ambiguous: do not infer 1.234 versus 1234 from this alone.
        return None
    try:
        result=Decimal(raw)
        return result if result.is_finite() else None
    except InvalidOperation: return None


def _unit_relation(a,b,incomplete):
    if incomplete: return "incomplete"
    if not a or not b: return "unknown"
    if a.keys()==b.keys(): return "same_units"
    if a.keys() & b.keys(): return "overlapping_units"
    for x in a:
        for y in b:
            # A municipal name and code cannot be equated without an official mapping.
            if x[0][0]!=y[0][0]: return "unknown"
            # Absent optional section is not a proven different unit.
            if x[0]==y[0] and x[2:]==y[2:] and (not x[1] or not y[1]): return "incomplete"
    return "different_units"


def _business_value(field,value):
    value=_unwrap(value)
    if field in {"superficie_utile","superficie_commerciale","prezzo"}: return _number(value)
    if field=="categoria": return _category(value)
    if field=="intestatari":
        people=value if isinstance(value,list) else [value]
        return tuple(sorted(tuple(sorted(_text(p).split())) for p in people if isinstance(p,str) and p.strip())) or None
    if field=="classe_energetica":
        text=_known(value)
        text=re.sub(r"\s","",text.upper()) if text else ""
        return text if re.fullmatch(r"A[1-4]?|A\+|[B-G]",text) else None
    return _canonical(value)


def _business_conflicts(a,b):
    issues=[]
    fa,fb=_fields(a),_fields(b)
    for field,aliases in _FIELDS.items():
        va=[_business_value(field,fa[k]) for k in aliases if k in fa]
        vb=[_business_value(field,fb[k]) for k in aliases if k in fb]
        va=[v for v in va if v is not None]; vb=[v for v in vb if v is not None]
        if va and vb and set(va)!=set(vb):
            issues.append({"field":field,"kind":"structured_disagreement"})
    return issues


def _document_date(doc):
    values=[]
    fields=_fields(doc)
    for container in (doc,fields):
        for name in ("document_date","issue_date","data_emissione"):
            value=_known(container.get(name))
            if value:
                try:
                    # No timestamps/upload dates or locale-ambiguous date inference.
                    values.append(date.fromisoformat(value))
                except ValueError: return None,"invalid"
    if len(set(values))>1: return None,"inconsistent"
    return (values[0],"known") if values else (None,"missing")


def compare_documents(document_a: dict, document_b: dict, *, today: date | None = None) -> dict:
    if not isinstance(document_a,dict) or not isinstance(document_b,dict):
        raise TypeError("Documents must be dictionaries")
    a,b=document_a,document_b
    today=today or date.today()
    boundary=_scope(a,b)
    result={"engine_version":VERSION,"status":"insufficient_evidence","similarity_score":0.0,
            "duplicate_exact":False,"scores":{"hash":0.0,"type":0.0,"text":0.0,"metadata":0.0},
            "requires_review":True,"automatic_merge_allowed":False,"reasons":[],
            "conflicts":[],"version":{"assessment":"not_established","newer":None},
            "identity":{"relation":"unknown"},"comparison_limited":False}
    if boundary!="compatible_or_unknown":
        result["status"]="out_of_scope" if boundary=="out_of_scope" else "insufficient_evidence"
        result["reasons"]=[boundary]
        return result
    ha,badha=_hash(a); hb,badhb=_hash(b)
    ta,tb=_kind(a),_kind(b)
    same_type=bool(ta and tb and ta==tb)
    text=_text_analysis(a.get("ocr_text"),b.get("ocr_text"))
    try:
        meta=_metadata_detail(_fields(a),_fields(b))
        ua,ia=_units(a); ub,ib=_units(b)
        conflicts=_business_conflicts(a,b)
    except (ValueError,RecursionError):
        meta={"score":0.0,"shared":0,"union":0}
        ua,ub={},{}; ia=ib=True; conflicts=[]
        result["comparison_limited"]=True
        result["reasons"].append("structured_input_limit")
    relation=_unit_relation(ua,ub,ia or ib)
    result["identity"]={"relation":relation}
    if any(len(values)>1 for units in (ua,ub) for values in units.values()):
        conflicts.append({"field":"categoria","kind":"ambiguous_readings_within_one_document"})
    # Per-unit category comparison avoids mixing a garage with the main apartment.
    for key in ua.keys() & ub.keys():
        if ua[key] and ub[key] and ua[key]!=ub[key]:
            conflicts.append({"field":"categoria","kind":"same_unit_category_disagreement"})
    if relation in {"different_units","overlapping_units"}:
        conflicts=[c for c in conflicts if c["kind"] in {"same_unit_category_disagreement","ambiguous_readings_within_one_document"}]
    if ta and tb and not same_type:
        result["reasons"].append("different_document_types")
    if badha or badhb: result["reasons"].append("invalid_or_inconsistent_hash")
    result["scores"].update(hash=1.0 if ha and hb and ha==hb else 0.0,
                            type=1.0 if same_type else 0.0,text=round(text["score"],3),
                            metadata=round(meta["score"],3))
    result["comparison_limited"] |= text["limited"]
    if text["limited"]: result["reasons"].append("ocr_text_limit")
    if text["numeric_changes"] and text["score"]>=.8:
        conflicts.append({"field":"ocr_numeric_tokens","kind":"numeric_change_requires_reading"})
    result["conflicts"]=conflicts
    exact=bool(ha and hb and ha==hb)
    result["duplicate_exact"]=exact
    if exact:
        result.update(status="duplicate",similarity_score=1.0,
                      requires_review=bool(conflicts or (ta and tb and not same_type) or
                                           relation in {"different_units","overlapping_units"} or result["comparison_limited"]))
        result["reasons"].append("matching_sha256_bytes_not_independent_evidence")
        return result
    # Renormalise observed evidence only when sufficiently long OCR is available.
    if text["available"] and text["substantial"]:
        weights=.75+(.20 if meta["union"] else 0)+(.05 if ta and tb else 0)
        score=(.75*text["score"]+.20*meta["score"]+.05*result["scores"]["type"])/weights
    else:
        score=.20*meta["score"]+.05*result["scores"]["type"]
    result["similarity_score"]=round(score,3)
    da,sa=_document_date(a); db,sb=_document_date(b)
    series_a=_known(a.get("document_series_id"))
    series_b=_known(b.get("document_series_id"))
    explicit_series=bool(series_a and series_b and series_a==series_b)
    version_ok=(explicit_series and same_type and relation=="same_units" and da and db and da!=db
                and max(da,db)<=today and not result["comparison_limited"])
    if version_ok:
        result["status"]="same_document_updated"  # Compatibility label, explicitly only a candidate.
        result["version"]={"assessment":"candidate_requires_review","newer":"a" if da>db else "b"}
        result["reasons"].append("same_explicit_series_units_type_and_later_issue_date")
    elif relation=="different_units":
        result["status"]="different"
        result["reasons"].append("different_cadastral_units")
    elif conflicts:
        result["status"]="possible_conflict"
        result["reasons"].append("differences_require_cross_validation")
    elif result["comparison_limited"]:
        result["status"]="insufficient_evidence"
    elif text["substantial"] and score>=.80 and not (ta and tb and not same_type):
        result["status"]="similar"
        result["reasons"].append("similar_ocr_is_not_a_verified_revision")
    elif text["substantial"]:
        result["status"]="different"
        result["requires_review"]=False
    else:
        result["reasons"].append("not_enough_content_to_classify")
    if explicit_series and not version_ok:
        result["reasons"].append("version_lineage_not_sufficient")
    if sa in {"invalid","inconsistent"} or sb in {"invalid","inconsistent"}:
        result["reasons"].append("invalid_or_inconsistent_document_date")
    return result
