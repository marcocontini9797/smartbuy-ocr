"""
SmartBuy Authentication Service v1

Argon2 password hashing
"""

from __future__ import annotations


from jose import jwt


from argon2 import PasswordHasher


from core.auth_models import User, TokenResponse





SECRET_KEY = "smartbuy-secret"

ALGORITHM = "HS256"





password_hasher = PasswordHasher()





class AuthService:


    def __init__(

        self,

        repository

    ):

        self.repository = repository





    def register(

        self,

        email:str,

        password:str

    ):


        password_hash = (

            password_hasher.hash(

                password

            )

        )


        user = User(

            email=email,

            password_hash=password_hash

        )


        return self.repository.create(

            user

        )





    def login(

        self,

        email:str,

        password:str

    ):


        user = self.repository.find_by_email(

            email

        )


        if not user:

            return None





        try:


            password_hasher.verify(

                user.password_hash,

                password

            )


        except:


            return None





        token = jwt.encode(

            {

            "sub": user.id,

            "email": user.email

            },

            SECRET_KEY,

            algorithm=ALGORITHM

        )





        return TokenResponse(

            access_token=token

        )