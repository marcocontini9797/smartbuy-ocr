"""
SmartBuy Agent Test Engine v1
"""

from __future__ import annotations


from core.agent_test_models import (

    AgentTestResult

)





class AgentTestEngine:



    def __init__(

        self,

        agent

    ):

        self.agent = agent





    def run(

        self,

        test_case

    ):


        response = self.agent.ask(

            property_id=test_case.property_id,

            question=test_case.question

        )



        actual = response.get(

            "answer",

            ""

        )





        passed = (

            test_case.expected_answer.lower()

            in

            actual.lower()

        )





        errors=[]



        if not passed:

            errors.append(

                "Risposta diversa dall'atteso"

            )





        return AgentTestResult(

            test_id=test_case.id,

            passed=passed,

            actual_answer=actual,

            expected_answer=test_case.expected_answer,

            score=1.0 if passed else 0.0,

            errors=errors

        )