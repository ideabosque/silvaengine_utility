#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import logging
import traceback
from typing import Any, Dict, Optional


class Debugger(object):
    @staticmethod
    def info(
        variable: Any,
        stage: str = "",
        delimiter: str = "-",
        delimiter_repetitions: int = 20,
        setting: Optional[Dict[str, Any]] = None,
        logger: Optional[logging.Logger] = None,
        enabled_trace: bool = True,
    ):
        debug_mode_key = "debug_mode"
        is_debug_mode = (
            setting.get("debug_mode", True)
            if isinstance(setting, dict) and debug_mode_key in setting
            else True
        )

        if is_debug_mode:
            logger = (
                logger
                if logger and isinstance(logger, logging.Logger)
                else logging.getLogger("DEBUG")
            )
            logger.setLevel(level=logging.INFO)

            delimiter_repetitions = (
                int(delimiter_repetitions) if int(delimiter_repetitions) > 0 else 20
            )
            delimiter = str(delimiter).strip() if str(delimiter).strip() else "-"
            stage = str(stage).strip()

            template = f"{delimiter * delimiter_repetitions} {{mark}} {stage} {delimiter * delimiter_repetitions}"

            logger.info(template.format(mark="START:"))
            logger.info(f"{variable}")

            if enabled_trace:
                logger.info(template.format(mark=f"{delimiter * 6}"))
                logger.info(f"{traceback.format_stack()}")

            logger.info(template.format(mark="END:"))
