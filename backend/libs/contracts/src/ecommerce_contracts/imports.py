from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

IMPORTS_TOPIC: Final = "imports.jobs"
IMPORT_VALIDATION_REQUESTED: Final = "import.validation_requested"
IMPORT_REQUESTED: Final = "import.requested"
SHA256_PATTERN: Final = r"^[0-9a-f]{64}$"


class ImportFileReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    import_id: UUID
    object_key: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)


class ImportValidationRequestedV1(ImportFileReference):
    pass


class ImportRequestedV1(ImportFileReference):
    pass
