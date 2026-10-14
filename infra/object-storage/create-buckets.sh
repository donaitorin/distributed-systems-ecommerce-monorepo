#!/bin/sh
set -eu

create_bucket() {
  aws s3api head-bucket --bucket "$1" 2>/dev/null || aws s3api create-bucket --bucket "$1"
}

create_bucket "$OBJECT_STORAGE_MEDIA_BUCKET"
create_bucket "$OBJECT_STORAGE_IMPORTS_BUCKET"
