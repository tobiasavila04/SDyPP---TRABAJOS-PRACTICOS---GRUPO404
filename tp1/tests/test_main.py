import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def clear_items():
    """Reset state before each test."""
    import app.main as main_module

    main_module.items.clear()
    main_module.next_id = {"value": 1}
    yield


client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "SD2026-GRUPO404 API is running"}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "health"}


def test_list_items_empty():
    response = client.get("/items")
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_create_item():
    payload = {"name": "Widget", "description": "A useful widget", "price": 9.99}
    response = client.post("/items", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "Widget"
    assert data["price"] == 9.99


def test_get_item():
    client.post("/items", json={"name": "Gadget", "price": 19.99})
    response = client.get("/items/1")
    assert response.status_code == 200
    assert response.json()["name"] == "Gadget"


def test_get_item_not_found():
    response = client.get("/items/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Item not found"


def test_list_items_after_create():
    client.post("/items", json={"name": "A", "price": 1.0})
    client.post("/items", json={"name": "B", "price": 2.0})
    response = client.get("/items")
    assert len(response.json()["items"]) == 2


def test_delete_item():
    client.post("/items", json={"name": "ToDelete", "price": 5.0})
    response = client.delete("/items/1")
    assert response.status_code == 200
    assert client.get("/items/1").status_code == 404


def test_delete_item_not_found():
    response = client.delete("/items/999")
    assert response.status_code == 404
