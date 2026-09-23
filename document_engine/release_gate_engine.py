"""
SmartBuy Release Gate Engine v1
"""

from __future__ import annotations


from core.release_gate_models import (

    ReleaseDecision

)





class ReleaseGateEngine:



    def evaluate(

        self,

        candidate_version:str,

        previous_version:str,

        candidate_score:float,

        previous_score:float,

        minimum_score:float = 0.90

    ):



        reasons=[]


        approved=True





        if candidate_score < minimum_score:


            approved=False


            reasons.append(

                "Score sotto soglia minima"

            )





        if candidate_score < previous_score:


            approved=False


            reasons.append(

                "Peggioramento rispetto alla versione precedente"

            )





        return ReleaseDecision(

            candidate_version=candidate_version,

            previous_version=previous_version,

            candidate_score=candidate_score,

            previous_score=previous_score,

            minimum_score=minimum_score,

            approved=approved,

            decision=(

                "RELEASE"

                if approved

                else

                "BLOCK"

            ),

            reasons=reasons

        )