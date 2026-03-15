"""Tests for global error handling middleware."""

import pytest
from fastapi import FastAPI, HTTPException
from httpx import AsyncClient, ASGITransport


class TestGlobalErrorHandler:
    """Global error handler should return structured JSON responses."""

    @pytest.mark.asyncio
    async def test_http_exception_returns_structured_error(self):
        """HTTPException should return structured JSON with error field."""
        from app.core.error_handler import register_error_handlers

        test_app = FastAPI()
        register_error_handlers(test_app)

        @test_app.get("/fail")
        async def fail():
            raise HTTPException(status_code=404, detail="Не знайдено")

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/fail")
            assert response.status_code == 404
            data = response.json()
            assert "error" in data
            assert data["error"]["message"] == "Не знайдено"
            assert data["error"]["status_code"] == 404

    @pytest.mark.asyncio
    async def test_unhandled_exception_returns_500(self):
        """Unhandled exceptions should return 500 with generic message."""
        from app.core.error_handler import register_error_handlers

        test_app = FastAPI(debug=False)
        register_error_handlers(test_app)

        @test_app.get("/crash")
        async def crash():
            raise RuntimeError("unexpected failure")

        transport = ASGITransport(app=test_app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/crash")
            assert response.status_code == 500
            data = response.json()
            assert "error" in data
            assert data["error"]["status_code"] == 500

    @pytest.mark.asyncio
    async def test_validation_error_returns_422(self):
        """Pydantic validation errors should return 422 with details."""
        from app.core.error_handler import register_error_handlers
        from pydantic import BaseModel

        test_app = FastAPI()
        register_error_handlers(test_app)

        class Item(BaseModel):
            name: str
            price: float

        @test_app.post("/items")
        async def create_item(item: Item):
            return {"name": item.name}

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/items", json={"name": 123})
            assert response.status_code == 422
            data = response.json()
            assert "error" in data
            assert data["error"]["status_code"] == 422
