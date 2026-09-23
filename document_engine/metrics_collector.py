"""
SmartBuy Metrics Collector v1
"""

from __future__ import annotations


from core.monitoring_models import (

    AgentMetrics

)





class MetricsCollector:



    def collect(

        self,

        audit_logs:list[dict],

        evaluations:list[dict],

        feedback:list[dict]

    ):


        requests = len(

            audit_logs

        )


        errors = len(

            [

            e for e in evaluations

            if e.get("errors")

            ]

        )



        grounding_values = [

            1

            if e.get("grounded")

            else 0

            for e in evaluations

        ]



        confidence_values = [

            e.get(

                "confidence",

                0

            )

            for e in audit_logs

        ]



        scores = [

            e.get(

                "overall_score",

                0

            )

            for e in evaluations

        ]



        corrections = len(

            [

            f for f in feedback

            if f.get("action")

            ==

            "CORRECT"

            ]

        )





        return AgentMetrics(

            total_requests=requests,

            total_errors=errors,

            average_grounding=(

                sum(grounding_values)

                /

                len(grounding_values)

                if grounding_values

                else 0

            ),

            average_confidence=(

                sum(confidence_values)

                /

                len(confidence_values)

                if confidence_values

                else 0

            ),

            average_score=(

                sum(scores)

                /

                len(scores)

                if scores

                else 0

            ),

            user_corrections=corrections,

            total_input_tokens=sum(

                x.get(

                    "input_tokens",

                    0

                )

                for x in audit_logs

            ),

            total_output_tokens=sum(

                x.get(

                    "output_tokens",

                    0

                )

                for x in audit_logs

            )

        )