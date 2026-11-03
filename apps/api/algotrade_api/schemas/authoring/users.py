"""``POST /users``: onboard a trader (ID5): the request and what is left to do at the identity
provider."""

from pydantic import BaseModel, Field

from algotrade_api.schemas.health import Schema


class OnboardBody(BaseModel):
    user_id: str = Field(description="the new user's id: 1-64 of a-z, 0-9, '_' and '-'")
    email: str = Field(description="the address they sign in with (the admin adds it at Supabase)")
    name: str = Field("", description="a display name (optional)")


class ProviderStep(Schema):
    email: str = Field(description="the address to add at the identity provider")
    instruction: str = Field(
        description="a fixed id of the remaining step; the web maps it to its Guide entry"
    )


class Onboarded(Schema):
    user_id: str = Field(description="the declared user's id")
    role: str = Field(description="always 'trader': admin and licences change by PR")
    pending_provider: bool = Field(
        description="true until the user's provider account is pinned (it is not created here)"
    )
    provider_step: ProviderStep = Field(description="the one step the admin still does by hand")
