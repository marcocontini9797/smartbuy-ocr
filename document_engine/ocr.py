"""
SmartBuy Document Engine - OCR Engine

Responsabilità:
- convertire PDF / immagini in pagine immagine
- eseguire OCR multimodale tramite OpenAI Vision
- gestire documenti multipagina
- restituire testo strutturato

NON classifica il documento.
NON estrae campi immobiliari.
"""

from __future__ import annotations


import os
import base64
import time
import asyncio

from io import BytesIO


from dotenv import load_dotenv

load_dotenv()


import httpx

from PIL import Image

from pdf2image import convert_from_bytes


from .models import (
    OCRPage,
    OCRResult
)



# ==================================================
# CONFIGURAZIONE
# ==================================================


OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY"
)


if not OPENAI_API_KEY:

    raise RuntimeError(
        "OPENAI_API_KEY non configurata nel file .env"
    )



POPPLER_PATH = os.getenv(
    "POPPLER_PATH",
    r"C:\poppler\poppler-26.09.0\Library\bin"
)



VISION_MODEL = os.getenv(
    "OPENAI_VISION_MODEL",
    "gpt-4o"
)



MAX_PAGES = int(
    os.getenv(
        "OCR_MAX_PAGES",
        "50"
    )
)



OCR_TIMEOUT_SECONDS = int(
    os.getenv(
        "OCR_TIMEOUT_SECONDS",
        "120"
    )
)



MAX_IMAGE_SIDE = int(
    os.getenv(
        "OCR_MAX_IMAGE_SIDE",
        "1800"
    )
)



# ==================================================
# IMAGE PROCESSING
# ==================================================


def normalize_image(
    image: Image.Image
) -> Image.Image:

    """
    Normalizza immagine prima dell'invio.
    """

    if image.mode != "RGB":

        image = image.convert(
            "RGB"
        )


    width, height = image.size

    max_side = max(
        width,
        height
    )


    if max_side > MAX_IMAGE_SIDE:

        scale = (
            MAX_IMAGE_SIDE /
            max_side
        )

        image = image.resize(
            (
                int(width * scale),
                int(height * scale)
            )
        )


    return image





def image_to_base64(
    image: Image.Image
) -> str:

    """
    Converte immagine PIL in PNG base64.
    """

    image = normalize_image(
        image
    )


    buffer = BytesIO()


    image.save(
        buffer,
        format="PNG",
        optimize=True
    )


    return base64.b64encode(
        buffer.getvalue()
    ).decode("utf-8")





# ==================================================
# DOCUMENT TO IMAGE
# ==================================================


def document_to_images(
    content: bytes,
    extension: str
) -> list[Image.Image]:

    """
    Converte documento in immagini.
    """

    extension = extension.lower()



    if extension == ".pdf":

        images = convert_from_bytes(
            content,
            dpi=200,
            poppler_path=POPPLER_PATH
        )


        if not images:

            raise RuntimeError(
                "PDF senza pagine leggibili"
            )


        if len(images) > MAX_PAGES:

            images = images[:MAX_PAGES]


        return images



    if extension in {
        ".jpg",
        ".jpeg",
        ".png"
    }:

        return [
            Image.open(
                BytesIO(content)
            )
        ]



    raise ValueError(
        f"Formato non supportato: {extension}"
    )





# ==================================================
# OPENAI VISION OCR
# ==================================================


async def vision_page_ocr(
    image: Image.Image,
    page_number: int,
    retries: int = 2
) -> str:

    """
    OCR di una singola pagina.
    """

    encoded = image_to_base64(
        image
    )



    payload = {

        "model": VISION_MODEL,


        "messages": [

            {

                "role": "user",


                "content": [

                    {

                        "type": "text",

                        "text": """

Sei un motore OCR professionale
per documentazione immobiliare italiana.

Il tuo unico compito è TRASCRIVERE
il contenuto visibile della pagina.

Non devi:
- analizzare il documento;
- dare consigli;
- esprimere giudizi;
- rifiutare la richiesta;
- riassumere.

Devi riportare fedelmente:

- intestazioni;
- nomi e cognomi;
- codici fiscali;
- indirizzi;
- dati catastali;
- foglio;
- particella;
- subalterno;
- rendite;
- date;
- importi;
- firme;
- timbri;
- tabelle.

Se un dato è poco leggibile,
scrivi [non leggibile].

Restituisci esclusivamente
la trascrizione del documento.

"""

                    },


                    {

                        "type": "image_url",

                        "image_url": {

                            "url":
                            (
                                "data:image/png;base64,"
                                + encoded
                            )

                        }

                    }

                ]

            }

        ]

    }



    last_error = None



    for attempt in range(
        retries + 1
    ):


        try:


            async with httpx.AsyncClient(
                timeout=OCR_TIMEOUT_SECONDS
            ) as client:


                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",

                    headers={

                        "Authorization":
                        f"Bearer {OPENAI_API_KEY}",

                        "Content-Type":
                        "application/json"

                    },

                    json=payload

                )



            if response.status_code != 200:

                raise RuntimeError(
                    response.text
                )



            data = response.json()



            text = (
                data["choices"][0]
                ["message"]
                ["content"]
            )



            blocked_phrases = [

                "mi dispiace",

                "non posso aiutarti",

                "i can't help",

                "i cannot help"

            ]



            if any(

                phrase in text.lower()

                for phrase in blocked_phrases

            ):

                raise RuntimeError(
                    f"Vision ha rifiutato OCR pagina {page_number}"
                )



            if not text.strip():

                raise RuntimeError(
                    "OCR vuoto"
                )



            return text.strip()



        except Exception as e:

            last_error = e


            if attempt < retries:

                await asyncio.sleep(
                    2 ** attempt
                )



    raise RuntimeError(
        f"OCR fallito pagina {page_number} "
        f"dopo {retries + 1} tentativi: {last_error}"
    )





# ==================================================
# MAIN OCR PIPELINE
# ==================================================


async def run_ocr(
    content: bytes,
    extension: str
) -> OCRResult:

    """
    OCR completo documento.
    """

    start = time.time()



    images = document_to_images(
        content,
        extension
    )



    pages = []



    for index, image in enumerate(
        images,
        start=1
    ):


        print(
            f"OCR pagina {index}/{len(images)}"
        )


        try:


            text = await vision_page_ocr(
                image,
                index
            )


        except Exception as e:


            text = (
                "[ERRORE OCR PAGINA "
                f"{index}: {str(e)}]"
            )



        pages.append(

            OCRPage(

                page_number=index,

                text=text,

                confidence=0.95
                if not text.startswith("[ERRORE")
                else 0.0

            )

        )



    full_text = "\n\n".join(

        [

            f"--- PAGINA {p.page_number} ---\n{p.text}"

            for p in pages

        ]

    )



    elapsed = time.time() - start



    valid_confidences = [

        p.confidence

        for p in pages

    ]



    confidence = (

        sum(valid_confidences)

        /

        len(valid_confidences)

        if valid_confidences

        else 0

    )



    return OCRResult(

        full_text=full_text,

        pages=pages,

        confidence=round(
            confidence,
            2
        ),

        processing_time_seconds=round(
            elapsed,
            2
        )

    )