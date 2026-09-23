from document_engine.grounding_validator import (
    GroundingValidator
)


from document_engine.llm_adapter import (
    MockLLMAdapter
)





class MockContext:


    sources=[]





llm = MockLLMAdapter()


validator = GroundingValidator()





response = llm.generate(

    {}

)





result = validator.validate(

    response,

    MockContext()

)





print(response)

print(result)