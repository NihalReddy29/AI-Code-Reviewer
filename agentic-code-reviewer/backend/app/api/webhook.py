from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix='/webhooks', tags=['webhooks'])


@router.post('/github')
async def github_webhook(request: Request) -> dict[str, str]:
    payload = await request.json()
    if not payload:
        raise HTTPException(status_code=400, detail='Empty payload')
    return {'status': 'received', 'event': payload.get('action', 'unknown')}
