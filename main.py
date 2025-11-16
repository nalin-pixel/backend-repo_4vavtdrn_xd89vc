import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId
from datetime import datetime, timezone
from typing import List, Optional

from database import db, create_document, get_documents

app = FastAPI(title="Luxury ToDo API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for requests/responses
class TaskCreate(BaseModel):
    title: str
    notes: Optional[str] = None
    priority: str = "medium"
    due_at: Optional[datetime] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    priority: Optional[str] = None
    completed: Optional[bool] = None
    due_at: Optional[datetime] = None

class TaskOut(BaseModel):
    id: str
    title: str
    notes: Optional[str]
    priority: str
    completed: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    due_at: Optional[datetime]


def serialize_task(doc) -> TaskOut:
    return TaskOut(
        id=str(doc.get("_id")),
        title=doc.get("title"),
        notes=doc.get("notes"),
        priority=doc.get("priority", "medium"),
        completed=bool(doc.get("completed", False)),
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
        due_at=doc.get("due_at"),
    )


@app.get("/")
async def root():
    return {"message": "Luxury ToDo API running"}

@app.get("/test")
async def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response

# CRUD Endpoints
COLL = "task"

@app.get("/api/tasks", response_model=List[TaskOut])
async def list_tasks(q: Optional[str] = None, filter: Optional[str] = None):
    query = {}
    if q:
        # Simple regex search on title/notes
        query = {"$or": [{"title": {"$regex": q, "$options": "i"}}, {"notes": {"$regex": q, "$options": "i"}}]}
    if filter == "active":
        query["completed"] = False
    elif filter == "completed":
        query["completed"] = True
    docs = get_documents(COLL, query)
    # Sort by created_at desc if present
    docs.sort(key=lambda d: d.get("created_at", datetime.now(timezone.utc)), reverse=True)
    return [serialize_task(d) for d in docs]

@app.post("/api/tasks", response_model=TaskOut)
async def create_task(payload: TaskCreate):
    data = payload.model_dump()
    data.setdefault("completed", False)
    data["created_at"] = datetime.now(timezone.utc)
    data["updated_at"] = datetime.now(timezone.utc)
    inserted_id = create_document(COLL, data)
    doc = db[COLL].find_one({"_id": ObjectId(inserted_id)})
    return serialize_task(doc)

@app.patch("/api/tasks/{task_id}", response_model=TaskOut)
async def update_task(task_id: str, payload: TaskUpdate):
    try:
        oid = ObjectId(task_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid task id")
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    update["updated_at"] = datetime.now(timezone.utc)
    res = db[COLL].find_one_and_update({"_id": oid}, {"$set": update}, return_document=True)
    doc = db[COLL].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    return serialize_task(doc)

@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    try:
        oid = ObjectId(task_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid task id")
    res = db[COLL].delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
