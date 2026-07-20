# -*- coding: utf-8 -*-

from peewee import (
    CharField,
    IntegerField,
    Model,
    MySQLDatabase,
    Proxy,
    TextField,
)
from playhouse.shortcuts import ReconnectMixin

store_database_proxy = Proxy()


class ReconnectMySQLDatabase(ReconnectMixin, MySQLDatabase):
    pass


def init_store(host, user, password, database):
    store_db_connection = ReconnectMySQLDatabase(
        host=host,
        user=user,
        password=password,
        database=database,
    )
    store_database_proxy.initialize(store_db_connection)


class StoreBaseModel(Model):
    class Meta:
        database = store_database_proxy


class Store(StoreBaseModel):
    id = IntegerField()
    name = CharField()
    code = CharField()
    platform = CharField()
    api_credential = CharField()
    url = CharField()
    service_account_data = TextField()

    class Meta:
        table_name = "spree_shops"
