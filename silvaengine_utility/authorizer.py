#!/usr/bin/env python3
"""AWS API Gateway Lambda Authorizer utility classes."""

import re
from enum import Enum
from typing import Any, Dict, List, Optional

__author__ = "bl"


class HttpVerb(Enum):
    """Supported HTTP verbs for API Gateway methods."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    HEAD = "HEAD"
    DELETE = "DELETE"
    OPTIONS = "OPTIONS"
    ALL = "*"


class AuthPolicy:
    """
    AWS API Gateway Lambda Authorizer Policy Builder.

    This class helps generate IAM policies for AWS API Gateway Lambda authorizers.
    It manages lists of allowed and denied methods and builds the appropriate
    IAM policy document.
    """

    # Default policy version for IAM
    DEFAULT_POLICY_VERSION = "2012-10-17"

    # Regular expression for validating resource paths
    PATH_REGEX = r"^[/.a-zA-Z0-9-\*]+$"

    # Default placeholders
    DEFAULT_REST_API_ID = "<<restApiId>>"
    DEFAULT_REGION = "<<region>>"
    DEFAULT_STAGE = "<<stage>>"

    def __init__(self, principal_id: str, aws_account_id: str):
        """
        Initialize the AuthPolicy.

        Args:
            principal_id: Unique identifier for the end user
            aws_account_id: AWS account ID for generating method ARNs
        """
        self.aws_account_id = aws_account_id
        self.principal_id = principal_id
        self.version = self.DEFAULT_POLICY_VERSION
        self.path_regex = self.PATH_REGEX

        # Initialize method lists
        self.allow_methods: List[Dict[str, Any]] = []
        self.deny_methods: List[Dict[str, Any]] = []

        # Default values - should be overridden
        self.rest_api_id = self.DEFAULT_REST_API_ID
        self.region = self.DEFAULT_REGION
        self.stage = self.DEFAULT_STAGE

    def _validate_http_verb(self, verb: str) -> None:
        """Validate that the HTTP verb is supported."""
        if verb != "*" and verb not in [v.value for v in HttpVerb]:
            raise ValueError(f"Invalid HTTP verb: {verb}. Allowed verbs: {[v.value for v in HttpVerb]}")

    def _validate_resource_path(self, resource: str) -> None:
        """Validate that the resource path matches the expected pattern."""
        if not re.match(self.path_regex, resource):
            raise ValueError(f"Invalid resource path: {resource}. Path should match {self.path_regex}")

    def _normalize_resource_path(self, resource: str) -> str:
        """Remove leading slash from resource path if present."""
        return resource[1:] if resource.startswith("/") else resource

    def _build_resource_arn(self, verb: str, resource: str) -> str:
        """Build the AWS ARN for the API Gateway resource."""
        normalized_resource = self._normalize_resource_path(resource)
        return (
            f"arn:aws:execute-api:{self.region}:{self.aws_account_id}:"
            f"{self.rest_api_id}/{self.stage}/{verb}/{normalized_resource}"
        )

    def _add_method(self, effect: str, verb: str, resource: str, conditions: Optional[List[Dict[str, Any]]]) -> None:
        """
        Add a method to the internal lists of allowed or denied methods.

        Args:
            effect: Either "Allow" or "Deny"
            verb: HTTP verb or "*" for all verbs
            resource: Resource path
            conditions: Optional IAM policy conditions
        """
        self._validate_http_verb(verb)
        self._validate_resource_path(resource)

        resource_arn = self._build_resource_arn(verb, resource)
        method_entry = {
            "resourceArn": resource_arn,
            "conditions": conditions or []
        }

        if effect.lower() == "allow":
            self.allow_methods.append(method_entry)
        elif effect.lower() == "deny":
            self.deny_methods.append(method_entry)
        else:
            raise ValueError(f"Invalid effect: {effect}. Must be 'Allow' or 'Deny'")

    def _create_empty_statement(self, effect: str) -> Dict[str, Any]:
        """Create an empty IAM policy statement with the specified effect."""
        return {
            "Action": "execute-api:Invoke",
            "Effect": effect.capitalize(),
            "Resource": [],
        }

    def _build_statements_for_effect(self, effect: str, methods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate IAM policy statements for the given effect and methods.

        Args:
            effect: Either "Allow" or "Deny"
            methods: List of method dictionaries with resourceArn and conditions

        Returns:
            List of IAM policy statements
        """
        if not methods:
            return []

        statements = []
        main_statement = self._create_empty_statement(effect)

        for method in methods:
            if not method.get("conditions"):
                # Add to main statement if no conditions
                main_statement["Resource"].append(method["resourceArn"])
            else:
                # Create separate statement for conditional methods
                conditional_statement = self._create_empty_statement(effect)
                conditional_statement["Resource"].append(method["resourceArn"])
                conditional_statement["Condition"] = method["conditions"]
                statements.append(conditional_statement)

        # Add main statement if it has resources
        if main_statement["Resource"]:
            statements.append(main_statement)

        return statements

    def allow_all_methods(self) -> None:
        """Add a wildcard allow policy to authorize access to all API methods."""
        self._add_method("Allow", HttpVerb.ALL.value, "*", [])

    def deny_all_methods(self) -> None:
        """Add a wildcard deny policy to deny access to all API methods."""
        self._add_method("Deny", HttpVerb.ALL.value, "*", [])

    def allow_method(self, verb: str, resource: str) -> None:
        """
        Add an API Gateway method to the list of allowed methods.

        Args:
            verb: HTTP verb (GET, POST, etc.)
            resource: Resource path
        """
        self._add_method("Allow", verb, resource, [])

    def deny_method(self, verb: str, resource: str) -> None:
        """
        Add an API Gateway method to the list of denied methods.

        Args:
            verb: HTTP verb (GET, POST, etc.)
            resource: Resource path
        """
        self._add_method("Deny", verb, resource, [])

    def allow_method_with_conditions(self, verb: str, resource: str, conditions: List[Dict[str, Any]]) -> None:
        """
        Add an allowed method with IAM policy conditions.

        Args:
            verb: HTTP verb (GET, POST, etc.)
            resource: Resource path
            conditions: List of IAM policy condition statements
        """
        self._add_method("Allow", verb, resource, conditions)

    def deny_method_with_conditions(self, verb: str, resource: str, conditions: List[Dict[str, Any]]) -> None:
        """
        Add a denied method with IAM policy conditions.

        Args:
            verb: HTTP verb (GET, POST, etc.)
            resource: Resource path
            conditions: List of IAM policy condition statements
        """
        self._add_method("Deny", verb, resource, conditions)

    def build(self) -> Dict[str, Any]:
        """
        Generate the complete IAM policy document.

        Returns:
            Dictionary containing principalId and policyDocument

        Raises:
            ValueError: If no allow or deny methods are defined
        """
        if not self.allow_methods and not self.deny_methods:
            raise ValueError("No statements defined for the policy")

        policy = {
            "principalId": self.principal_id,
            "policyDocument": {
                "Version": self.version,
                "Statement": []
            },
        }

        # Add allow statements
        allow_statements = self._build_statements_for_effect("Allow", self.allow_methods)
        policy["policyDocument"]["Statement"].extend(allow_statements)

        # Add deny statements
        deny_statements = self._build_statements_for_effect("Deny", self.deny_methods)
        policy["policyDocument"]["Statement"].extend(deny_statements)

        return policy


class Authorizer:
    """
    AWS API Gateway Lambda Authorizer.

    This class provides a simplified interface for creating authorization
    policies for AWS API Gateway Lambda authorizers.
    """

    def __init__(self, principal_id: str, aws_account_id: str, api_id: str, region: str, stage: str) -> None:
        """
        Initialize the Authorizer.

        Args:
            principal_id: Unique identifier for the end user
            aws_account_id: AWS account ID
            api_id: API Gateway REST API ID
            region: AWS region
            stage: API Gateway stage name
        """
        self.policy = AuthPolicy(principal_id, aws_account_id)
        self.policy.rest_api_id = api_id
        self.policy.region = region
        self.policy.stage = stage

    def authorize(self, is_allow: bool = True, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generate authorization response.

        Args:
            is_allow: If True, allow all methods; if False, deny all methods
            context: Optional context to include in the response

        Returns:
            Authorization response dictionary
        """
        if is_allow:
            self.policy.allow_all_methods()
        else:
            self.policy.deny_all_methods()

        auth_response = self.policy.build()

        if context:
            auth_response["context"] = context

        return auth_response
