#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function
from collections import defaultdict
from silvaengine_utility.utility import Utility
import boto3, json

__author__ = "bl"


class Common(object):
    @staticmethod
    def get_grouped_seller_role_emails(
        channel,
        settings,
        logger,
        role_types,
        relation_type,
        ids,
        database_session=None,
    ):
        if database_session:
            settings["database_session"] = database_session

        try:
            role_sellers = Utility.import_dynamically(
                "silvaengine_permission",
                "get_users_by_role_type",
                "Permission",
                constructor_parameters={"logger": logger, **dict(settings)},
            )(
                channel=channel,
                settings=settings,
                role_types=role_types,  # 0 - Normal, 1 - GWI Account Manager, 2 - GWI QC Manager, 3 - Dept Managers
                relationship_type=relation_type,  # Integer, required:0 - admin, 1 - seller, 2 - team
                ids=ids,  # seller or company id, list, optional: None(default)
            )

            result = defaultdict(dict)

            if role_sellers:
                role_types = {
                    1: "product_managers",
                    2: "qc_managers",
                    3: "dept_managers",
                }

                for seller_role in role_sellers:
                    # print("*************************************************************")
                    # print(seller_role)
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
    def invoke_data_process(settings, data_payload, channel, invocation_type="Event"):
        try:
            if "app_env" not in settings or (settings["app_env"] != "local"):
                lambda_client = boto3.client(
                    "lambda",
                    region_name=settings.get("aws_region_name", "us-east-1"),
                )
            else:
                lambda_client = boto3.client(
                    "lambda",
                    aws_access_key_id=settings.get("aws_access_key_id"),
                    aws_secret_access_key=settings.get("aws_secret_access_key"),
                    region_name=settings.get("aws_region_name", "us-east-1"),
                )

            if invocation_type not in ["RequestResponse", "Event"]:
                invocation_type = "Event"

            lambda_client.invoke(
                FunctionName="silvaengine_agenttask",
                InvocationType=invocation_type,
                Payload=json.dumps(
                    {
                        "endpoint_id": str(channel).strip(),
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
