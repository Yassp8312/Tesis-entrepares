"""Paginación del contrato: count, page, page_size y results."""

from django.core.exceptions import ImproperlyConfigured
from django.core.paginator import InvalidPage, Paginator
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response


class ContractPagination:
    def paginate_queryset(self, queryset, request, view=None):
        query = getattr(view, "validated_query", {})
        if "page" not in query or "page_size" not in query:
            raise ImproperlyConfigured("La vista paginada debe validar PageQuerySerializer.")
        self.page_size = query["page_size"]
        try:
            self.page = Paginator(queryset, self.page_size).page(query["page"])
        except InvalidPage:
            raise ValidationError({"page": "La página solicitada está fuera de rango."}) from None
        return list(self.page)

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "page": self.page.number,
                "page_size": self.page_size,
                "results": data,
            }
        )
