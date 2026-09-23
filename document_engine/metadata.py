"""
SmartBuy Document Engine - Metadata Analyzer

Analisi preliminare del documento.

Non classifica il documento.
Non usa il nome file per decidere il tipo.

Raccoglie solo informazioni utili
alla pipeline successiva.
"""

from __future__ import annotations

import io
import mimetypes

from pathlib import Path

from .models import FileMetadata



# ==================================================
# PDF ANALYSIS
# ==================================================

def _analyze_pdf(content: bytes) -> dict:
    """
    Estrae informazioni base da un PDF.
    """

    result = {
        "pages": None,
        "creator": None,
        "title": None,
        "is_scanned": None,
    }

    try:

        import pypdf


        reader = pypdf.PdfReader(
            io.BytesIO(content)
        )


        # Numero pagine

        result["pages"] = len(
            reader.pages
        )


        # Metadati PDF

        metadata = reader.metadata


        if metadata:

            result["creator"] = (
                metadata.creator
            )

            result["title"] = (
                metadata.title
            )


        # ------------------------------------------
        # Verifica presenza testo nativo
        # ------------------------------------------

        text_found = False


        pages_to_check = min(
            len(reader.pages),
            3
        )


        for i in range(pages_to_check):

            text = (
                reader.pages[i]
                .extract_text()
            )


            if text and len(text.strip()) > 50:

                text_found = True
                break



        # Se non c'è testo è probabilmente
        # una scansione

        result["is_scanned"] = not text_found



    except Exception:

        # Non blocchiamo la pipeline
        pass


    return result





# ==================================================
# MAIN FUNCTION
# ==================================================

def analyze_file_metadata(

    filename: str,

    content: bytes

) -> FileMetadata:

    """
    Analizza il documento caricato.
    """



    extension = (

        Path(filename)

        .suffix

        .lower()

    )


    mime_type, _ = mimetypes.guess_type(
        filename
    )


    data = {

        "filename":

            filename,


        "extension":

            extension,


        "size_bytes":

            len(content),


        "mime_type":

            mime_type,

    }



    # Analisi PDF

    if extension == ".pdf":


        pdf_info = _analyze_pdf(
            content
        )


        data.update(

            {

                "pages":
                    pdf_info["pages"],


                "pdf_creator":
                    pdf_info["creator"],


                "pdf_title":
                    pdf_info["title"],


                "is_scanned":
                    pdf_info["is_scanned"],

            }

        )


    return FileMetadata(
        **data
    )