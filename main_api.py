from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.agent_routes import router as agent_router
from api.agent_tasks_routes import router as agent_tasks_router
from api.document_routes import router as document_router
from api.property_routes import router as property_router
from api.registry_routes import router as registry_router
from api.operations_routes import router as operations_router
from api.share_routes import router as share_router
from api.seller_lead_routes import router as seller_lead_router
from document_engine.feedback_router import router as feedback_router


app = FastAPI(title="SmartBuy AI API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(property_router)
app.include_router(registry_router)
app.include_router(operations_router)
app.include_router(document_router)
app.include_router(agent_router)
app.include_router(agent_tasks_router)
app.include_router(feedback_router)
app.include_router(share_router)
app.include_router(seller_lead_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "SmartBuy AI API", "version": app.version}
