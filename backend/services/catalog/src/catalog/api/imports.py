from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from catalog.api.dependencies import ImportServiceDep, PageSize, require_problem_page_size
from catalog.api.import_schemas import ImportOut, ProblemOut, ProblemsPageOut
from catalog.api.responses import problem_responses
from catalog.api.uploads import StreamedUpload
from catalog.domain.imports import PREVIEW_PROBLEMS
from ecommerce_auth import AdminUser
from ecommerce_observability import get_request_id

router = APIRouter(prefix="/api/v1/imports", tags=["imports"])

ImportId = Annotated[UUID, Path(description="Import id")]
MULTIPART_BODY = {
    "required": True,
    "content": {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "required": ["file"],
                "properties": {"file": {"type": "string", "format": "binary"}},
            }
        }
    },
}


def correlation_id() -> UUID:
    current = get_request_id()
    try:
        return UUID(current) if current else uuid4()
    except ValueError:
        return uuid4()


@router.post(
    "",
    response_model=ImportOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a products CSV (admin)",
    description=(
        "Multipart field `file`. The file is stored, hashed and validated in the background; "
        "nothing is written to the catalog until the import is confirmed. Uploading the same "
        "file again returns the existing import with status 200."
    ),
    openapi_extra={"requestBody": MULTIPART_BODY},
    responses={
        200: {"description": "The same file was already uploaded; the existing import"},
        **problem_responses(401, 403, 413, 415, 422, 503),
    },
)
async def upload_import(
    request: Request, response: Response, admin: AdminUser, service: ImportServiceDep
) -> ImportOut:
    upload = StreamedUpload(request, service.max_bytes)
    result = await service.upload(
        upload.chunks(), admin.user_id, correlation_id(), lambda: upload.filename
    )
    response.headers["Location"] = f"/api/v1/imports/{result.record.id}"
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return ImportOut.from_domain(result.record, [])


@router.get(
    "/{import_id}",
    response_model=ImportOut,
    summary="Get an import with its status, counts and first problems (admin)",
    responses=problem_responses(401, 403, 404),
)
async def get_import(
    import_id: ImportId, _admin: AdminUser, service: ImportServiceDep
) -> ImportOut:
    record, preview = await service.preview(import_id, PREVIEW_PROBLEMS)
    return ImportOut.from_domain(record, preview)


@router.get(
    "/{import_id}/problems",
    response_model=ProblemsPageOut,
    summary="List the problems of an import, in file order (admin)",
    responses=problem_responses(401, 403, 404, 422),
)
async def list_problems(
    import_id: ImportId,
    _admin: AdminUser,
    service: ImportServiceDep,
    severity: Annotated[Literal["error", "warning"] | None, Query()] = None,
    limit: Annotated[PageSize, Depends(require_problem_page_size)] = 100,
    cursor: Annotated[str | None, Query(max_length=64)] = None,
) -> ProblemsPageOut:
    page = await service.problems(import_id, severity, cursor, limit)
    return ProblemsPageOut(
        items=[ProblemOut.from_domain(item) for item in page.items], next_cursor=page.next_cursor
    )


@router.get(
    "/{import_id}/problems.csv",
    summary="Download every problem of an import as a CSV (admin)",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/csv": {}}}, **problem_responses(401, 403, 404)},
)
async def download_problems(
    import_id: ImportId, _admin: AdminUser, service: ImportServiceDep
) -> StreamingResponse:
    await service.get(import_id)
    return StreamingResponse(
        service.problems_csv(import_id),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="import-{import_id}-problems.csv"'},
    )


@router.post(
    "/{import_id}/confirm",
    response_model=ImportOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Confirm the import of the valid rows (admin)",
    description=(
        "Only a validated import can be confirmed. The valid rows are then written in the "
        "background; poll the import for progress. Repeating the call is harmless."
    ),
    responses=problem_responses(401, 403, 404, 409),
)
async def confirm_import(
    import_id: ImportId, _admin: AdminUser, service: ImportServiceDep
) -> ImportOut:
    record = await service.confirm(import_id, correlation_id())
    return ImportOut.from_domain(record, [])


@router.post(
    "/{import_id}/revalidate",
    response_model=ImportOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Validate the same file again against the current categories (admin)",
    description=(
        "Allowed for a rejected or validated import, for example after creating a category the "
        "file refers to. The previous report, problems and category snapshot are discarded "
        "together with the status change and the file is validated again in the background; "
        "poll the import for the result. Repeating the call while it is pending is harmless."
    ),
    responses=problem_responses(401, 403, 404, 409),
)
async def revalidate_import(
    import_id: ImportId, _admin: AdminUser, service: ImportServiceDep
) -> ImportOut:
    record = await service.revalidate(import_id, correlation_id())
    return ImportOut.from_domain(record, [])
