#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import logging
from typing import Any, Dict, Optional


class Debugger(object):
    @staticmethod
    def info(
        variable: Any,
        stage: str = "",
        delimiter: str = "-",
        delimiter_repetitions: int = 40,
        setting: Optional[Dict[str, Any]] = None,
        logger: Optional[logging.Logger] = None,
    ):
        fn = (
            logger.info
            if isinstance(logger, logging.Logger)
            else logging.getLogger(name="debug")
        )
        is_debug_mode = (
            setting.get("debug_mode", True) if type(setting) is dict else True
        )
        delimiter_repetitions = (
            int(delimiter_repetitions) if int(delimiter_repetitions) > 0 else 40
        )
        delimiter = str(delimiter).strip() if str(delimiter).strip() else "-"
        stage = str(stage).strip()

        if is_debug_mode and callable(fn):
            t = f"{delimiter * delimiter_repetitions} {{mark}}: {stage} {delimiter * delimiter_repetitions}"

            fn(t.format(mark="START"))
            fn(variable)
            fn(t.format(mark="END"))
