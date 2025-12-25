import json
import os
from time import sleep
from typing import Callable, Generator

from flask import request
from flask import url_for as _url_for
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import check_password_hash

from wyzebridge.config import HASS_TOKEN, IMG_PATH, IMG_TYPE, TOKEN_PATH
from wyzebridge.auth import WbAuth
from wyzebridge.logging import logger

auth = HTTPBasicAuth()

API_ENDPOINTS = "/api", "/img", "/snapshot", "/thumb", "/photo"

@auth.verify_password
def verify_password(username, password):
    if HASS_TOKEN and request.remote_addr == "172.30.32.2":
        return True
    if WbAuth.api in (request.args.get("api"), request.headers.get("api")):
        return request.path.startswith(API_ENDPOINTS)
    if username == WbAuth.username:
        return check_password_hash(WbAuth.hashed_password(), password)
    return not WbAuth.enabled

@auth.error_handler
def unauthorized():
    return {"error": "Unauthorized"}, 401

def url_for(endpoint, **values):
    proxy = (
        request.headers.get("X-Ingress-Path")
        or request.headers.get("X-Forwarded-Prefix")
        or ""
    ).rstrip("/")
    return proxy + _url_for(endpoint, **values)

def sse_generator(sse_status: Callable) -> Generator[str, str, str]:
    """Generator to return the status for enabled cameras."""
    cameras = {}
    while True:
        if cameras != (cameras := sse_status()):
            yield f"data: {json.dumps(cameras)}\n\n"
        sleep(1)

def mfa_generator(mfa_req: Callable) -> Generator[str, str, str]:
    if mfa_req():
        yield f"event: mfa\ndata: {mfa_req()}\n\n"
        while mfa_req():
            sleep(1)
    while True:
        yield "event: mfa\ndata: clear\n\n"
        sleep(30)

def set_mfa(mfa_code: str) -> bool:
    """Set MFA code from WebUI."""
    mfa_file = f"{TOKEN_PATH}mfa_token.txt"
    try:
        with open(mfa_file, "w") as f:
            f.write(mfa_code)
        while os.path.getsize(mfa_file) != 0:
            sleep(1)
        return True
    except Exception as ex:
        logger.error(ex)
        return False
