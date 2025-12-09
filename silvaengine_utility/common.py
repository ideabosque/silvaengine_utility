#!/usr/bin/env python3
"""Common utility functions for SilvaEngine."""

import json
from collections import defaultdict
from typing import Any, Dict, List, Optional, Union

import boto3

from silvaengine_utility.utility import Utility

__author__ = "bl"


class Common:
    """Common utility class providing shared functionality across the application."""

    # Role type mappings
    ROLE_TYPE_MAPPING = {
        1: "product_managers",
        2: "qc_managers",
        3: "dept_managers",
    }

    # Valid Lambda invocation types
    VALID_INVOCATION_TYPES = {"RequestResponse", "Event"}

    @staticmethod
    def get_grouped_seller_role_emails(
        channel: str,
        settings: Dict[str, Any],
        logger: Any,
        role_types: List[int],
        relation_type: int,
        ids: Optional[List[Union[str, int]]] = None,
        database_session: Optional[Any] = None,
    ) -> Dict[str, Dict[str, List[str]]]:
        """
        Retrieve grouped seller role emails based on channel, role types, and relation type.

        Args:
            channel: Channel identifier
            settings: Configuration settings
            logger: Logger instance
            role_types: List of role type integers (0=Normal, 1=GWI Account Manager,
                       2=GWI QC Manager, 3=Dept Managers)
            relation_type: Relationship type (0=admin, 1=seller, 2=team)
            ids: Optional list of seller or company IDs
            database_session: Optional database session

        Returns:
            Dictionary mapping role types to seller emails grouped by seller ID

        Raises:
            Exception: If an error occurs during processing
        """
        if database_session:
            settings["database_session"] = database_session

        role_sellers = Utility.import_dynamically(
            "silvaengine_permission",
            "get_users_by_role_type",
            "Permission",
            constructor_parameters={"logger": logger, **dict(settings)},
        )(
            channel=channel,
            settings=settings,
            role_types=role_types,
            relationship_type=relation_type,
            ids=ids,
        )

        result = defaultdict(dict)

        if not role_sellers:
            return result

        for seller_role in role_sellers:
            if not (
                seller_role and seller_role.get("type") and seller_role.get("groups")
            ):
                continue

            role_index = Common.ROLE_TYPE_MAPPING.get(seller_role.get("type"))
            if not role_index:
                continue

            for seller_id, users in seller_role.get("groups").items():
                emails = [
                    user.get("user_base_info", {}).get("email")
                    for user in users
                    if user.get("user_base_info", {}).get("email")
                ]
                if emails:
                    result[role_index][seller_id] = emails

        return result

    @staticmethod
    def invoke_data_process(
        settings: Dict[str, Any],
        data_payload: Dict[str, Any],
        channel: str,
        invocation_type: str = "Event",
    ) -> None:
        """
        Invoke AWS Lambda function for data processing.

        Args:
            settings: Configuration settings containing AWS credentials and region
            data_payload: Data to be processed
            channel: Channel identifier
            invocation_type: Lambda invocation type ("RequestResponse" or "Event")

        Raises:
            Exception: If Lambda invocation fails
        """
        if invocation_type not in Common.VALID_INVOCATION_TYPES:
            invocation_type = "Event"

        lambda_client = Common._create_lambda_client(settings)

        payload = {
            "endpoint_id": str(channel).strip(),
            "funct": "data_process_engine_run",
            "params": data_payload,
        }

        lambda_client.invoke(
            FunctionName="silvaengine_agenttask",
            InvocationType=invocation_type,
            Payload=json.dumps(payload),
        )

    @staticmethod
    def _create_lambda_client(settings: Dict[str, Any]) -> Any:
        """
        Create AWS Lambda client based on environment settings.

        Args:
            settings: Configuration settings

        Returns:
            Configured boto3 Lambda client
        """
        region = settings.get("aws_region_name", "us-east-1")

        if settings.get("app_env") == "local":
            return boto3.client(
                "lambda",
                aws_access_key_id=settings.get("aws_access_key_id"),
                aws_secret_access_key=settings.get("aws_secret_access_key"),
                region_name=region,
            )
        else:
            return boto3.client("lambda", region_name=region)

    @staticmethod
    def get_query(model: Any, context: Dict[str, Any]) -> Any:
        """
        Get SQLAlchemy query object for a model.

        Args:
            model: SQLAlchemy model class
            context: Context dictionary containing database session

        Returns:
            Query object for the model

        Raises:
            Exception: If neither model.query exists nor database_session is provided
        """
        query = getattr(model, "query", None)

        if query is not None:
            return query

        session = context.get("database_session")
        if not session:
            raise Exception(
                "A query in the model Base or a session in the schema is required for querying.\n"
                "Read more http://docs.graphene-python.org/projects/sqlalchemy/en/latest/tips/#querying"
            )

        return session.query(model)
