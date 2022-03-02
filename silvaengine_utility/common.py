#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function
from collections import defaultdict
from .utility import Utility
import boto3, json

__author__ = "bl"


class Common(object):
    @staticmethod
    def get_grouped_seller_role_emails(info, logger, role_types, relation_type, ids):
        try:
            role_sellers = Utility.import_dynamically(
                "silvaengine_permission",
                "get_users_by_role_type",
                "Permission",
                constructor_parameters={"logger": logger},
            )(
                info=info,
                role_types=role_types,  # 待查询的角色类别, 数组, 必填, 可取值为: 0 - 普通角色, 1 - GWI Account Manager, 2 - GWI QC Manager, 3 - Dept Managers
                relationship_type=relation_type,  # 关系类型, 整型, 必填, 可取值为:0 - admin, 1 - seller, 2 - team
                ids=ids,  # 商家或公司ID, 数组, 选填, 默认为None
            )

            result = defaultdict(dict)

            if role_sellers:
                role_types = {
                    1: "product_managers",
                    2: "qc_managers",
                    3: "dept_managers",
                }

                for seller_role in role_sellers:
                    if (
                        seller_role
                        and seller_role.get("type")
                        and seller_role.get("groups")
                    ):
                        index = role_types.get(seller_role.get("type"))

                        for seller_id, users in seller_role.get("groups").items():
                            result[index][seller_id] = [
                                user.get("user_base_info", {}).get("email")
                                for user in users
                                if user.get("user_base_info", {}).get("email")
                            ]

            return result
        except Exception as e:
            raise e

    @staticmethod
    def invoke_data_process(settings, data_payload):
        try:
            if "env" not in settings or (settings["env"] != "local"):
                lambda_client = boto3.client("lambda", region_name="us-east-1")
            else:
                lambda_client = boto3.client(
                    "lambda",
                    aws_access_key_id=settings["aws_access_key_id"],
                    aws_secret_access_key=settings["aws_secret_access_key"],
                    region_name="us-east-1",
                )
            lambda_client.invoke(
                FunctionName="silvaengine_agenttask",
                InvocationType="Event",
                Payload=json.dumps(
                    {
                        "endpoint_id": "api",
                        "funct": "data_process_engine_run",
                        "params": data_payload,
                    }
                ),
            )
        except Exception as e:
            raise e

    @staticmethod
    def get_query(model, context):
        try:
            query = getattr(model, "query", None)

            if not query:
                session = context.get("database_session")

                if not session:
                    raise Exception(
                        "A query in the model Base or a session in the schema is required for querying.\n"
                        "Read more http://docs.graphene-python.org/projects/sqlalchemy/en/latest/tips/#querying"
                    )

                query = session.query(model)
            return query
        except Exception as e:
            raise e
