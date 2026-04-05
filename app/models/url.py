from peewee import BooleanField, CharField, DateTimeField, ForeignKeyField, IntegerField

from app.database import BaseModel
from app.models.user import User


class Url(BaseModel):
    class Meta:
        table_name = "urls"

    id = IntegerField(primary_key=True)
    user = ForeignKeyField(User, field=User.id, backref="urls", on_delete="CASCADE")
    short_code = CharField(unique=True, index=True)
    original_url = CharField()
    title = CharField()
    is_active = BooleanField(default=True)
    created_at = DateTimeField()
    updated_at = DateTimeField()
