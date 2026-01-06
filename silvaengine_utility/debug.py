#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function


class Debug(object):
    @staticmethod
    def info(info, variable, delimiter_title="", delimiter="-", delimiter_total=40):
        fn = print

        if (
            info
            and hasattr(info, "context")
            and "logger" in info.context
            and hasattr(info.context.get("logger"), "info")
        ):
            fn = info.context.get("logger").info

        if bool(info.get("context", {}).get("debug_mode", True)):
            t = f"{'-' * delimiter_total} {{mark}}: {str(delimiter_title).strip()} {'-' * delimiter_total}"

            fn(t.format(mark="START"))
            fn(variable)
            fn(t.format(mark="END"))
