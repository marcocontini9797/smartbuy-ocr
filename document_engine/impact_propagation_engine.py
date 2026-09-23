"""
SmartBuy Impact Propagation Engine v1

Determina quali elementi devono
essere aggiornati dopo un cambiamento.
"""


from __future__ import annotations


from core.impact_models import (

    ImpactPropagationResult,

    ImpactTarget

)





class ImpactPropagationEngine:



    def __init__(

        self,

        knowledge_links

    ):

        self.knowledge_links = knowledge_links





    def propagate(

        self,

        change

    ):


        impacted = []



        links = self.knowledge_links.get_source_links(

            change.entity_type,

            change.entity_id

        )



        for link in links:


            impacted.append(

                ImpactTarget(

                    entity_type=

                        link["target_type"],


                    entity_id=

                        link["target_id"],


                    reason=

                        link["relation_type"]

                )

            )



        return ImpactPropagationResult(

            change_type=

                change.change_type,


            source_entity=

                change.entity_id,


            impacted_entities=

                impacted,


            metadata={

                "field":

                    change.field

            }

        )