#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import re
import socket
import struct

__author__ = "bibow"


class Struct(object):
    def __init__(self, **d):
        for a, b in d.items():
            if isinstance(b, (list, tuple)):
                setattr(self, a, [Struct(**x) if isinstance(x, dict) else x for x in b])
            else:
                setattr(self, a, Struct(**b) if isinstance(b, dict) else b)


class Utility(object):
    _snake_case_cache = {}

    @staticmethod
    def format_error(error):
        return {"message": str(error)}

    # Check the specified ip exists in the given ip segment
    @staticmethod
    def in_subnet(ip, subnet) -> bool:
        if isinstance(subnet, str) and subnet:
            match = re.match("(.*)/(.*)", subnet)

            if match:
                subnet = match.group(1)
                shift = int(match.group(2))
                nip = struct.unpack("I", socket.inet_aton(str(ip)))[0]
                nsubnet = struct.unpack("I", socket.inet_aton(subnet))[0]
                mask = (1 << shift) - 1

                return (nip & mask) == (nsubnet & mask)

            return str(ip).strip() == subnet.strip()
        elif type(subnet) is list and len(subnet):
            return str(ip) in [str(value).strip() for value in subnet]

        return str(ip).strip() == str(subnet).strip()

    # Convert camel case to underscore
    @staticmethod
    def convert_camel_to_underscore(text, separator="_"):
        if not separator:
            separator = "_"

        return "".join(
            [
                char if not char.isupper() or index == 0 else f"{separator}{char}"
                for index, char in enumerate(text)
            ]
        ).lower()

        # Add a cache for snake case conversions to avoid repeated calculations

    @staticmethod
    def to_snake_case(s: str) -> str:
        """Convert string to snake_case format with caching for improved performance."""
        if not s:
            return s

        # Check cache first
        cache_key = str(s)
        if cache_key in Utility._snake_case_cache:
            return Utility._snake_case_cache[cache_key]

        s = cache_key.strip()
        length = len(s)
        result = []
        prev_char = None

        for i in range(length):
            ch = s[i]
            next_char = s[i + 1] if i < length - 1 else None

            if ch == "-" or ch == "_":
                # Only add underscore if not at start or after another underscore
                if not (i == 0 or prev_char == "_"):
                    result.append("_")
                prev_char = "_"
            elif ch.isupper():
                # Convert to lowercase
                lower_ch = ch.lower()

                # Add underscore before uppercase if:
                # 1. Previous character is lowercase
                # 2. Previous character is uppercase and next character is lowercase
                if i > 0 and (
                    (prev_char and prev_char.islower())
                    or (
                        prev_char
                        and prev_char.isupper()
                        and next_char
                        and next_char.islower()
                    )
                ):
                    result.append("_")

                result.append(lower_ch)
                prev_char = lower_ch
            else:
                result.append(ch)
                prev_char = ch

        # Join and cache the result
        snake_case = "".join(result)
        Utility._snake_case_cache[cache_key] = snake_case
        return snake_case

    @staticmethod
    def convert_object_to_dict(instance):
        attributes = {}

        for attribute in dir(instance):
            value = getattr(instance, attribute)

            if not attribute.startswith("__") and not callable(value):
                attributes[attribute] = value

        return attributes
