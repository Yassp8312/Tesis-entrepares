"""Objetos de entrada cerrados y parámetros escalares explícitos."""

import re
from collections.abc import Mapping

from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail, ValidationError


class JSONSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            accepted = {
                name
                for name, field in self.fields.items()
                if not field.read_only and not isinstance(field, serializers.HiddenField)
            }
            unexpected = set(data) - accepted
            if unexpected:
                raise ValidationError(
                    {
                        name: [ErrorDetail("Campo no admitido.", code="unexpected_field")]
                        for name in sorted(unexpected)
                    }
                )
        return super().to_internal_value(data)


class QuerySerializer(JSONSerializer):
    def to_internal_value(self, data):
        if hasattr(data, "getlist"):
            repeated = [name for name in data if len(data.getlist(name)) != 1]
            if repeated:
                raise ValidationError(
                    {
                        name: [
                            ErrorDetail("El parámetro no puede repetirse.", "repeated_parameter")
                        ]
                        for name in repeated
                    }
                )
            data = data.dict()
        return super().to_internal_value(data)


class QueryIntegerField(serializers.IntegerField):
    def to_internal_value(self, data):
        if type(data) is not int and not (isinstance(data, str) and re.fullmatch(r"[0-9]+", data)):
            self.fail("invalid")
        try:
            return super().to_internal_value(int(data))
        except ValueError:
            self.fail("invalid")


class QueryBooleanField(serializers.BooleanField):
    def to_internal_value(self, data):
        if data == "true":
            return True
        if data == "false":
            return False
        self.fail("invalid", input=data)


class PageQuerySerializer(QuerySerializer):
    page = QueryIntegerField(min_value=1, default=1)
    page_size = QueryIntegerField(min_value=1, max_value=100, default=20)
