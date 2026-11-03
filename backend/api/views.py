"""Base HTTP con CSRF explícito también para operaciones sin sesión."""

from rest_framework.authentication import CSRFCheck
from rest_framework.views import APIView

from api.context import operation_context
from api.errors import ApiProblem
from api.serializers import JSONSerializer, QuerySerializer


class JSONAPIView(APIView):
    query_serializer_class = QuerySerializer
    input_serializer_class = JSONSerializer

    def initial(self, request, *args, **kwargs):
        operation_context(request)
        raw = request._request
        check = CSRFCheck(lambda request: None)
        check.process_request(raw)
        if check.process_view(raw, None, (), {}):
            raise ApiProblem("CSRF_FAILED")
        super().initial(request, *args, **kwargs)
        query = self.query_serializer_class(data=request.query_params)
        query.is_valid(raise_exception=True)
        self.validated_query = query.validated_data
        if request.method not in {"GET", "HEAD", "OPTIONS", "TRACE"}:
            body = self.input_serializer_class(data=request.data)
            body.is_valid(raise_exception=True)
            self.validated_input = body.validated_data
