#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function
__author__ = 'bibow'

import json, dateutil, re
from decimal import Decimal
from datetime import datetime, date

datetime_format = "%Y-%m-%dT%H:%M:%S"
datetime_format_regex = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$')

class JSONEncoder(json.JSONEncoder):
    
    def default(self, o):   # pylint: disable=E0202
        if isinstance(o, Decimal):
            if o % 1 > 0:
                return float(o)
            else:
                return int(o)
        elif hasattr(o, 'attribute_values'):
            return o.attribute_values
        elif isinstance(o, (datetime, date)):
            return o.strftime(datetime_format)
        elif isinstance(o, (bytes, bytearray)):
            return str(o)
        else:
            return super(JSONEncoder, self).default(o)


class JSONDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, o):   # pylint: disable=E0202
        if o.get('_type') in ['bytes', 'bytearray']:
            return str(o['value'])
        
        for (key, value) in o.items():
            try:
                if not isinstance(value, str):
                    continue
                if datetime_format_regex.match(value):
                    o[key] = dateutil.parser.parse(value)
            except (ValueError, AttributeError):
                pass

        return o

class Struct(object):

    def __init__(self, **d):
        for a, b in d.items():
            if isinstance(b, (list, tuple)):
               setattr(self, a, [Struct(**x) if isinstance(x, dict) else x for x in b])
            else:
               setattr(self, a, Struct(**b) if isinstance(b, dict) else b)

              
class Utility(object):

    @staticmethod
    def json_dumps(data):
        return json.dumps(data, indent=4, cls=JSONEncoder, ensure_ascii=False)

    @staticmethod
    def json_loads(data, parser_number=True):
        if parser_number:
            return json.loads(data, cls=JSONDecoder, parse_float=Decimal, parse_int=Decimal)
        return json.loads(data, cls=JSONDecoder)