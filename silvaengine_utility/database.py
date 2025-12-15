#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

class Database(object):
    @staticmethod
    def create_database_session(settings):
        try:
            from sqlalchemy import create_engine, orm
            from sqlalchemy.ext.declarative import DeclarativeMeta

            assert type(settings) is dict and len(
                settings
            ), "Missing configuration items required to connect to mysql database."

            required_settings = ["user", "password", "host", "port", "schema"]

            for key in required_settings:
                assert settings.get(
                    key
                ), f"Missing required configuration item `{key}`."

            dsn = "{}+{}://{}:{}@{}:{}/{}?charset={}".format(
                settings.get("type", "mysql"),
                settings.get("driver", "pymysql"),
                settings.get("user"),
                settings.get("password", ""),
                settings.get("host"),
                settings.get("port", 3306),
                settings.get("schema"),
                settings.get("charset", "utf8mb4"),
            )

            return orm.scoped_session(
                orm.sessionmaker(
                    autocommit=False,
                    autoflush=False,
                    bind=create_engine(
                        dsn,
                        pool_size=settings.get("pool_size", 10),
                        max_overflow=settings.get("max_overflow", -1),
                        pool_recycle=settings.get("pool_recycle", 1200),
                    ),
                )
            )
        except Exception as e:
            raise e