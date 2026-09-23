"""
SmartBuy Evaluation Engine v1
"""


from __future__ import annotations


from core.evaluation_models import (

    EvaluationResult

)





class EvaluationEngine:



    def evaluate(

        self,

        property_id:int,

        response_id:str,

        response:dict,

        sources:list

    ):


        errors=[]



        # Grounding

        grounded = (

            len(sources) > 0

            and

            response.get(

                "grounded",

                False

            )

        )





        grounding_score = (

            1.0

            if grounded

            else 0.0

        )





        # Coverage semplice v1

        evidence_coverage = (

            1.0

            if sources

            else 0.0

        )





        confidence = response.get(

            "confidence",

            0

        )





        overall = (

            grounding_score * 0.5

            +

            evidence_coverage * 0.3

            +

            confidence * 0.2

        )





        if not grounded:


            errors.append(

                "Risposta non sufficientemente supportata"

            )





        return EvaluationResult(

            property_id=property_id,

            response_id=response_id,

            grounded=grounded,

            grounding_score=grounding_score,

            evidence_coverage=evidence_coverage,

            confidence_score=confidence,

            overall_score=round(

                overall,

                2

            ),

            errors=errors

        )