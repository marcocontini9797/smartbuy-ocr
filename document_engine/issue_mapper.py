"""
SmartBuy Issue Mapper v2

Converte problemi grezzi
nel modello standard core.Issue.

Orientato all'agente immobiliare.
"""


from __future__ import annotations


from typing import Any


from core.models import (
    Issue,
    Evidence
)





# ==================================================
# SINGLE ISSUE BUILDER
# ==================================================


def build_issue(

    category: str,

    issue_type: str,

    severity: str,

    title: str,

    description: str,

    impact: str | None = None,

    recommended_action: str | None = None,

    evidence: list[Evidence] | None = None,

    metadata: dict[str, Any] | None = None

) -> Issue:


    return Issue(

        category=category,

        type=issue_type,

        severity=severity,

        title=title,

        description=description,

        impact=impact,

        recommended_action=recommended_action,

        evidence=evidence or [],

        metadata=metadata or {}

    )





# ==================================================
# DICT -> ISSUE
# ==================================================


def map_dict_to_issue(

    issue_data: dict

) -> Issue:


    evidence_objects = []



    for item in issue_data.get(

        "evidence",

        []

    ):


        evidence_objects.append(

            Evidence(

                document=item.get(

                    "document",

                    "unknown"

                ),

                page=item.get(

                    "page"

                ),

                text=item.get(

                    "text"

                ),

                confidence=item.get(

                    "confidence",

                    0.0

                )

            )

        )



    return build_issue(

        category=issue_data.get(

            "category",

            "general"

        ),

        issue_type=issue_data.get(

            "type",

            "unknown"

        ),

        severity=issue_data.get(

            "severity",

            "medium"

        ),

        title=issue_data.get(

            "title",

            ""

        ),

        description=issue_data.get(

            "description",

            ""

        ),

        impact=issue_data.get(

            "impact"

        ),

        recommended_action=issue_data.get(

            "recommended_action"

        ),

        evidence=evidence_objects,

        metadata=issue_data.get(

            "metadata",

            {}

        )

    )





# ==================================================
# LIST CONVERSION
# ==================================================


def map_issue_list(

    issues: list[dict]

) -> list[Issue]:


    return [

        map_dict_to_issue(issue)

        for issue in issues

    ]





# ==================================================
# DEBUG
# ==================================================


def debug_print_issues(

    issues: list[Issue]

):


    for issue in issues:


        print(

            issue.model_dump_json(

                indent=2

            )

        )