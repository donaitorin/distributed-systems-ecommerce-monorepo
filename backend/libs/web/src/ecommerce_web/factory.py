from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
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
    on_shutdown: Sequence[Callable[[], Awaitable[None]]] = (),
    root_path: str = "",
) -> FastAPI:
    configure_logging(settings.name, settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            for hook in on_shutdown:
                stack.push_async_callback(hook)
            if token_verifier is not None:
                stack.push_async_callback(token_verifier.aclose)
            yield

    app = FastAPI(
        title=settings.name, version=settings.version, lifespan=lifespan, root_path=root_path
    )
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
