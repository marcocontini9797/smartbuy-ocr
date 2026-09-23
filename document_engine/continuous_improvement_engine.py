"""
SmartBuy Continuous Improvement Engine v1
"""


from __future__ import annotations


from core.improvement_models import (

    ImprovementProposal

)





class ContinuousImprovementEngine:



    def analyze(

        self,

        evaluations:list[dict],

        feedback:list[dict]

    ):


        proposals=[]



        total_errors = len(

            [

            e for e in evaluations

            if e.get("errors")

            ]

        )



        if total_errors >= 2:


            proposals.append(

                ImprovementProposal(

                    category=

                    "QUALITY",


                    problem=

                    "Risposte con grounding insufficiente",


                    evidence_count=

                    total_errors,


                    suggestion=

                    "Migliorare recupero evidenze prima della generazione LLM",


                    target_component=

                    "retrieval_engine",


                    priority=

                    "high"

                )

            )



        corrections = len(

            [

            f for f in feedback

            if f.get("action")

            ==

            "CORRECT"

            ]

        )



        if corrections >= 2:


            proposals.append(

                ImprovementProposal(

                    category=

                    "KNOWLEDGE",


                    problem=

                    "Fatti frequentemente corretti dagli utenti",


                    evidence_count=

                    corrections,


                    suggestion=

                    "Rivedere regole estrazione dati",


                    target_component=

                    "knowledge_engine",


                    priority=

                    "medium"

                )

            )



        return proposals