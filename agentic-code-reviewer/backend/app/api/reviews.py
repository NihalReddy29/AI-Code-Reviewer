from fastapi import APIRouter

router = APIRouter(prefix='/reviews', tags=['reviews'])


@router.get('/')
def list_reviews() -> dict[str, list[str]]:
    return {'reviews': []}


@router.get('/{review_id}')
def get_review(review_id: str) -> dict[str, str]:
    return {'review_id': review_id, 'status': 'pending'}
