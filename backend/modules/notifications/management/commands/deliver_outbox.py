"""Lote finito; no arranca un servicio, cron o bucle en segundo plano."""

import json
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from application.delivery.transports import DjangoEmailTransport
from application.delivery.worker import OutboxWorker
from core.clock import SystemClock
from core.correlation import OperationContext


class Command(BaseCommand):
    help = "Procesa un lote finito de salida; solo imprime contadores técnicos."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= 1000:
            raise CommandError("El límite debe estar entre 1 y 1000.")
        # Registro cerrado vacío hasta integrar cada plantilla/flujo con sus propias pruebas.
        worker = OutboxWorker(transport=DjangoEmailTransport())
        counts = Counter()
        try:
            for _ in range(limit):
                outcome = worker.run_once(operation=OperationContext.start(clock=SystemClock()))
                counts["recovered"] += outcome.recovered
                counts[outcome.status] += 1
                if outcome.status == "empty":
                    break
        except Exception:
            # El error real puede incluir parámetros SQL, destino, cuerpo o credenciales.
            raise CommandError(
                "No se completó el lote de salida; conserva sus registros para recuperación."
            ) from None
        self.stdout.write(json.dumps(dict(counts), sort_keys=True))
