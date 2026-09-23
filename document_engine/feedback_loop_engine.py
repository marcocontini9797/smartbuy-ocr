"""
SmartBuy Feedback Loop Engine v1

Gestisce conseguenze feedback utente.
"""

from __future__ import annotations





class FeedbackLoopEngine:



    def __init__(

        self,

        memory_repository,

        knowledge_repository

    ):


        self.memory_repository = memory_repository

        self.knowledge_repository = knowledge_repository





    def process(

        self,

        feedback

    ):


        changes = []



        if feedback.action == "CONFIRM":


            changes.append(

                "FACT_CONFIRMED"

            )





        elif feedback.action == "CORRECT":


            changes.append(

                "FACT_UPDATED"

            )





            self.knowledge_repository.update_fact(

                feedback.target_id,

                feedback.corrected_value

            )





        # ogni feedback significativo

        # diventa memoria


        self.memory_repository.save(

            {

            "property_id":

                feedback.property_id,


            "memory_type":

                "USER_FEEDBACK",


            "title":

                feedback.action,


            "content":

                {

                "target":

                    feedback.target_id,

                "value":

                    feedback.corrected_value

                }

            }

        )



        return {


            "processed":

                True,


            "changes":

                changes

        }