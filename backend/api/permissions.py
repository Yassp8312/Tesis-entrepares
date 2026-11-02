"""Protección de entrada mientras cada operación incorpora su autorización explícita."""

from rest_framework.permissions import BasePermission


class DenyUnconfiguredAccess(BasePermission):
    message = "La operación no tiene un acceso autorizado configurado."

    def has_permission(self, request, view):
        return False

    def has_object_permission(self, request, view, obj):
        return False
