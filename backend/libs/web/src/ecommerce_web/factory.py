from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ecommerce_auth import ManagedTokenVerifier
from ecommerce_observability import RequestIdMiddleware, configure_logging
from ecommerce_web.problems import problem_response, register_problem_handlers
from ecommerce_web.readiness import STATUS_OK, ReadinessCheck, run_readiness_checks
from ecommerce_web.settings import ServiceSettings


def create_app(
    settings: ServiceSettings,
    readiness_checks: Sequence[ReadinessCheck] = (),
    token_verifier: ManagedTokenVerifier | None = None,
) -> FastAPI:
    configure_logging(settings.name, settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        if token_verifier is not None:
            await token_verifier.aclose()

    app = FastAPI(title=settings.name, version=settings.version, lifespan=lifespan)
    if token_verifier is not None:
        app.state.token_verifier = token_verifier.verifier

    app.add_middleware(RequestIdMiddleware)
    register_problem_handlers(app)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", response_model=None)
    async def ready(request: Request) -> JSONResponse:
        results = await run_readiness_checks(readiness_checks, settings.readiness_timeout_seconds)
        if all(status == STATUS_OK for status in results.values()):
            return JSONResponse({"status": "ready", "checks": results})
        return problem_response(
            request,
            HTTPStatus.SERVICE_UNAVAILABLE,
            "Service not ready",
            "One or more dependencies are unavailable",
            checks=results,
        )

    return app
