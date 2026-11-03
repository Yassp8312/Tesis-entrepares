"""JSON sin claves duplicadas ni constantes numéricas no finitas."""

import codecs
import math

from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser
from rest_framework.utils import json


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Clave duplicada")
        result[key] = value
    return result


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Número no finito")
    return number


class StrictJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        encoding = (parser_context or {}).get("encoding", "utf-8")
        try:
            return json.load(
                codecs.getreader(encoding)(stream),
                object_pairs_hook=unique_object,
                parse_constant=json.strict_constant,
                parse_float=finite_float,
            )
        except (ValueError, LookupError, RecursionError):
            raise ParseError("El cuerpo no contiene un documento JSON válido.") from None
