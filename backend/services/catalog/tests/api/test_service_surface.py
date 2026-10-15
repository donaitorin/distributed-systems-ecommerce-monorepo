import httpx


async def test_openapi_documents_every_endpoint_and_the_problem_responses(
    client: httpx.AsyncClient,
) -> None:
    spec = (await client.get("/openapi.json")).json()

    assert set(spec["paths"]) == {
        "/api/v1/products",
        "/api/v1/products/{sku}",
        "/api/v1/products/{sku}/image",
        "/api/v1/categories",
        "/health",
        "/ready",
    }
    put = spec["paths"]["/api/v1/products/{sku}"]["put"]
    assert {"401", "403", "404", "412", "422", "428"} <= set(put["responses"])
    delete = spec["paths"]["/api/v1/products/{sku}"]["delete"]
    assert {"204", "412", "428"} <= set(delete["responses"])
    assert spec["paths"]["/api/v1/products/{sku}"]["get"]["responses"]["200"]["headers"]["ETag"]


async def test_if_match_is_documented_as_a_header_parameter(client: httpx.AsyncClient) -> None:
    spec = (await client.get("/openapi.json")).json()

    parameters = spec["paths"]["/api/v1/products/{sku}"]["put"]["parameters"]
    assert any(item["name"] == "if-match" and item["in"] == "header" for item in parameters)


async def test_swagger_ui_is_served(client: httpx.AsyncClient) -> None:
    response = await client.get("/docs")

    assert response.status_code == 200
    assert "swagger" in response.text.lower()


async def test_every_response_carries_a_request_id(client: httpx.AsyncClient) -> None:
    ok = await client.get("/api/v1/products")
    missing = await client.get("/api/v1/products/NOPE")
    unknown_route = await client.get("/api/v1/nothing")

    for response in (ok, missing, unknown_route):
        assert response.headers["X-Request-ID"]
