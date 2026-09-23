"""
SmartBuy User Repository v1
"""

from __future__ import annotations


from core.auth_models import User





class UserRepository:


    def __init__(self):

        self.users=[]





    def create(

        self,

        user:User

    ):

        self.users.append(user)

        return user





    def find_by_email(

        self,

        email:str

    ):


        for user in self.users:

            if user.email == email:

                return user


        return None