"""The ASGI app uvicorn serves (``algotrade_api.app:app``), configured from the environment."""

from algotrade_api.deps import ApiSettings
from algotrade_api.main import create_app

app = create_app(ApiSettings.from_env())
