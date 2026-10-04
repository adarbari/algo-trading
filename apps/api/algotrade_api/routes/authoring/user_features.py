"""``POST /features/user``: save a named user expression feature (checked before saving)."""

from fastapi import APIRouter

from algotrade.services.authoring import user_features
from algotrade_api.deps import User, Writer
from algotrade_api.schemas.authoring.user_features import SavedFeature, UserFeatureBody

router = APIRouter(prefix="/features", tags=["features"])


@router.post("/user", status_code=201)
def save_user_feature(writer: Writer, user: User, body: UserFeatureBody) -> SavedFeature:
    definition = body.model_dump(exclude={"name", "theme"}, exclude_none=True)
    saved = user_features.save_user_feature(writer, user, body.name, definition, body.theme)
    return SavedFeature.model_validate(saved)
