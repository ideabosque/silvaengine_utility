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
        is_debug_mode = (
            setting.get("debug_mode", True) if type(setting) is dict else True
        )

        if is_debug_mode:
            logging.basicConfig(level=logging.INFO)
            fn = (
                logger.info
                if isinstance(logger, logging.Logger)
                else logging.getLogger("DEBUG").info
            )

            delimiter_repetitions = (
                int(delimiter_repetitions) if int(delimiter_repetitions) > 0 else 40
            )
            delimiter = str(delimiter).strip() if str(delimiter).strip() else "-"
            stage = str(stage).strip()

            template = f"{delimiter * delimiter_repetitions} {{mark}}: {stage} {delimiter * delimiter_repetitions}"

            fn(template.format(mark="START"))
            fn(variable)
            fn(template.format(mark="END"))
