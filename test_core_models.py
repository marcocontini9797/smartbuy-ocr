from core.models import (
    Fact,
    Evidence,
    Issue
)



fact = Fact(

    name="energy_class",

    value="A2",

    category="energy",

    confidence=0.98

)



evidence = Evidence(

    document="APE_test.pdf",

    page=2,

    text="Classe energetica A2",

    confidence=0.98

)



issue = Issue(

    type="energy_conflict",

    severity="medium",

    title="Classe energetica non verificata",

    description="Il valore richiede controllo.",

    evidence=[evidence]

)



print("\nFACT")

print(

    fact.model_dump_json(

        indent=2

    )

)



print("\nEVIDENCE")

print(

    evidence.model_dump_json(

        indent=2

    )

)



print("\nISSUE")

print(

    issue.model_dump_json(

        indent=2

    )

)