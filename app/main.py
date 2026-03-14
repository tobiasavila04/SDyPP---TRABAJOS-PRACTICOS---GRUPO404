"""_summary_

Raises:
    HTTPException: _description_
    HTTPException: _description_

Returns:
    _type_: _description_
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="SD2026-GRUPO404 API", version="1.0.0")


class Item(BaseModel):
    """_summary_

    Args:
        BaseModel (_type_): _description_
    """

    name: str
    description: str = ""
    price: float


items: dict[int, Item] = {}

next_id: dict[str, int] = {"value": 0}


@app.get("/")
def root():
    """_summary_

    Returns:
        _type_: _description_
    """
    return {"message": "SD2026-GRUPO404 API is running"}


@app.get("/health")
def health():
    """_summary_

    Returns:
        _type_: _description_
    """
    return {"status": "health"}


@app.get("/items")
def list_items():
    """_summary_

    Returns:
        _type_: _description_
    """
    return {"items": [{"id": k, **v.model_dump()} for k, v in items.items()]}


@app.get("/items/{item_id}")
def get_item(item_id: int):
    """_summary_

    Args:
        item_id (int): _description_

    Raises:
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Item not found")

    return {"id": item_id, **items[item_id].model_dump()}


@app.post("/items", status_code=201)
def create_item(item: Item):
    """_summary_

    Args:
        item (Item): _description_

    Returns:
        _type_: _description_
    """

    items[next_id["value"]] = item

    result = {"id": next_id["value"], **item.model_dump()}

    next_id["value"] += 1

    return result


@app.delete("/items/{item_id}")
def delete_item(item_id: int):
    """_summary_

    Args:
        item_id (int): _description_

    Raises:
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Item not found")

    del items[item_id]

    return {"message": f"Item {item_id} deleted"}
