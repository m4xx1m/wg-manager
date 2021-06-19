from logger import setup_logging
setup_logging()

import const
from uvicorn_loguru_integration import run_uvicorn_loguru

import time
from starlette.middleware.base import BaseHTTPMiddleware

import middleware

from routers.v1 import user, server, peer, wg
import script.wireguard_startup
import pkg_resources
import uvicorn as uvicorn
from fastapi.staticfiles import StaticFiles

from starlette.responses import FileResponse
from fastapi import Depends, FastAPI
import database.util

app = FastAPI()
app.add_middleware(BaseHTTPMiddleware, dispatch=middleware.db_session_middleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=middleware.logging_middleware)

app.include_router(
    user.router,
    prefix="/api/v1",
    tags=["user"],
    dependencies=[],
    responses={404: {"description": "Not found"}}
)


app.include_router(
    server.router,
    prefix="/api/v1/server",
    tags=["server"],
    dependencies=[Depends(middleware.auth)],
    responses={404: {"description": "Not found"}}
)


app.include_router(
    peer.router,
    prefix="/api/v1/peer",
    tags=["peer"],
    dependencies=[Depends(middleware.auth)],
    responses={404: {"description": "Not found"}}
)


app.include_router(
    wg.router,
    prefix="/api/v1/wg",
    tags=["wg"],
    dependencies=[Depends(middleware.auth)],
    responses={404: {"description": "Not found"}}
)


@app.get("/", include_in_schema=True)
def root():
    return FileResponse('build/index.html')


app.mount("/", StaticFiles(directory=pkg_resources.resource_filename(__name__, 'build')), name="static")


def main():
    # Sleep the wait timer.
    time.sleep(const.INIT_SLEEP)

    # Ensure database existence
    database.util.setup_initial_database()

    # Perform Migrations
    database.util.perform_migrations()

    # Configure wireguard
    script.wireguard_startup.setup_on_start()


@app.on_event("startup")
async def startup():
    if __name__ != "__main__":
        main()


@app.on_event("shutdown")
async def shutdown():
    pass


if __name__ == "__main__":

    main()

    run_uvicorn_loguru(
        uvicorn.Config(
            "__main__:app",
            host="0.0.0.0",
            port=8000,
            log_level="warning",
            reload=True,
            workers=1
        )
    )
