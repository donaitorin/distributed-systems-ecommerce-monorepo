WORKER_ENVIRON = {
    "CATALOG_DB_HOST": "postgres",
    "CATALOG_DB_NAME": "catalog_db",
    "CATALOG_DB_USER": "catalog_user",
    "CATALOG_DB_PASSWORD": "pw",
    "JWT_JWKS_URL": "http://auth:8000/jwks.json",
    "JWT_ISSUER": "ecommerce-auth",
    "OBJECT_STORAGE_ACCESS_KEY": "access",
    "OBJECT_STORAGE_SECRET_KEY": "secret",
    "OBJECT_STORAGE_ENDPOINT": "http://object-storage:8333",
    "OBJECT_STORAGE_MEDIA_BUCKET": "media",
    "MEDIA_PUBLIC_BASE_URL": "http://localhost:8000/media",
    "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
}
