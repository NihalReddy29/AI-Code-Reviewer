from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.reviews import router as reviews_router
from app.api.webhook import router as webhook_router

app = FastAPI(title='Agentic Code Reviewer', version='0.1.0')

app.include_router(health_router)
app.include_router(reviews_router, prefix='/api')
app.include_router(webhook_router, prefix='/api')


@app.get('/')
def read_root() -> dict[str, str]:
    return {'message': 'Agentic Code Reviewer backend is running.'}
