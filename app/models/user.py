from peewee import CharField, DateTimeField, IntegerField

from app.database import BaseModel


class User(BaseModel):
    class Meta:
        table_name = "users"

    id = IntegerField(primary_key=True)
    username = CharField()
    email = CharField()
    created_at = DateTimeField()
