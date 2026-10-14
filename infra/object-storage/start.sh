#!/bin/sh
set -eu

CONFIG_FILE=/tmp/s3-identities.json

cat > "$CONFIG_FILE" <<JSON
{
  "identities": [
    {
      "name": "service",
      "credentials": [
        {"accessKey": "$OBJECT_STORAGE_ACCESS_KEY", "secretKey": "$OBJECT_STORAGE_SECRET_KEY"}
      ],
      "actions": ["Admin", "Read", "Write", "List", "Tagging"]
    },
    {
      "name": "anonymous",
      "actions": ["Read:$OBJECT_STORAGE_MEDIA_BUCKET"]
    }
  ]
}
JSON
chmod 644 "$CONFIG_FILE"

exec /entrypoint.sh server -dir=/data -ip.bind=0.0.0.0 \
  -master.volumeSizeLimitMB=256 -volume.max=0 \
  -s3 -s3.port=8333 -s3.config="$CONFIG_FILE"
