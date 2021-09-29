#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

__author__ = "bl"

from collections import defaultdict
from .utility import Utility
import boto3, json


class Common(object):
    @staticmethod
    def get_grouped_seller_role_emails(logger, role_types, relation_type, ids):
        role_sellers = Utility.import_dynamically(
            "silvaengine_auth",
            "get_users_by_role_type",
            "Auth",
            constructor_parameters={"logger": logger},
        )(
            role_types,  # 待查询的角色类别, 数组, 必填, 可取值为: 0 - 普通角色, 1 - GWI Account Manager, 2 - GWI QC Manager, 3 - Dept Managers
            relation_type,  # 关系类型, 整型, 必填, 可取值为:0 - admin, 1 - seller, 2 - team
            ids,  # 商家或公司ID, 数组, 选填, 默认为None
        )

        result = defaultdict(dict)
        role_types = {
            1: "product_managers",
            2: "qc_managers",
            3: "dept_managers"
        }

        for seller_role in role_sellers:
            if seller_role and seller_role.get("type") and seller_role.get("groups"):
                index = role_types.get(seller_role.get("type"))

                for seller_id, users in seller_role.get("groups").items():
                    result[index][seller_id] = [
                        user.get("user_base_info", {}).get("email") for user in users if user.get("user_base_info", {}).get("email")
                    ]

            # if seller_role["role_id"] == "b874bcee-0af8-11ec-acc5-5d5264ad5593":
            #     for seller_id, users in seller_role["groups"].items():
            #         result["product_managers"][seller_id] = [
            #             user["user_base_info"]["email"] for user in users
            #         ]
            # if seller_role["role_id"] == "cc1d018b-0af8-11ec-bb01-5d5264ad5593":
            #     for seller_id, users in seller_role["groups"].items():
            #         result["qc_managers"][seller_id] = [
            #             user["user_base_info"]["email"] for user in users
            #         ]
            # if seller_role["role_id"] == "dc1b01eb-4af8-17ec-ba01-2d5234adf591":
            #     for seller_id, users in seller_role["groups"].items():
            #         result["dept_managers"][seller_id] = [
            #             user["user_base_info"]["email"] for user in users
            #         ]

        return result

    @staticmethod
    def invoke_data_process(settings, data_payload):
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
