from document_engine.user_repository import (
    UserRepository
)


from document_engine.auth_service import (
    AuthService
)





repo = UserRepository()



auth = AuthService(

    repo

)





user = auth.register(

    email="marco@test.com",

    password="password123"

)



print("================ USER ================")

print(

    user.model_dump_json(

        indent=2

    )

)





token = auth.login(

    email="marco@test.com",

    password="password123"

)



print("================ TOKEN ================")

print(

    token.model_dump_json(

        indent=2

    )

)