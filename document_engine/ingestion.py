"""
SmartBuy Document Engine - Document Ingestion

Primo livello della pipeline.

Responsabilità:
- validazione file
- controllo formato
- controllo dimensione
- analisi metadata
- creazione documento interno

NON:
- OCR
- classificazione
- estrazione
"""

from __future__ import annotations


import time
import uuid

from pathlib import Path


from .models import FileMetadata

from .metadata import (
    analyze_file_metadata
)



# ==================================================
# CONFIG
# ==================================================

MAX_FILE_SIZE = 25 * 1024 * 1024


SUPPORTED_EXTENSIONS = {

    ".pdf",
    ".png",
    ".jpg",
    ".jpeg"

}



# ==================================================
# INTERNAL DOCUMENT OBJECT
# ==================================================

class IngestedDocument:
    """
    Documento normalizzato pronto
    per i moduli successivi.
    """

    def __init__(
        self,
        document_id: str,
        filename: str,
        content: bytes,
        metadata: FileMetadata,
        processing_time: float
    ):

        self.document_id = document_id

        self.filename = filename

        self.content = content

        self.metadata = metadata

        self.processing_time = processing_time





# ==================================================
# VALIDATION
# ==================================================

def validate_file(

    filename: str,

    content: bytes

):

    """
    Controlli sicurezza iniziali.
    """

    if not filename:

        raise ValueError(
            "Nome file mancante"
        )


    extension = (

        Path(filename)

        .suffix

        .lower()

    )


    if extension not in SUPPORTED_EXTENSIONS:

        raise ValueError(
            f"Formato non supportato: {extension}"
        )


    if not content:

        raise ValueError(
            "File vuoto"
        )


    if len(content) > MAX_FILE_SIZE:

        raise ValueError(
            "File troppo grande. "
            "Massimo consentito 25 MB"
        )





# ==================================================
# INGEST FUNCTION
# ==================================================

def ingest_document(

    filename: str,

    content: bytes

) -> IngestedDocument:

    """
    Punto di ingresso del Document Engine.

    Riceve:
    - nome file
    - bytes documento


    Restituisce:
    documento validato.
    """

    start = time.time()



    # 1) Validazione

    validate_file(

        filename,

        content

    )



    # 2) Metadata

    metadata = analyze_file_metadata(

        filename,

        content

    )



    # 3) ID documento

    document_id = str(

        uuid.uuid4()

    )



    elapsed = (

        time.time()

        -

        start

    )



    return IngestedDocument(

        document_id=document_id,

        filename=filename,

        content=content,

        metadata=metadata,

        processing_time=elapsed

    )