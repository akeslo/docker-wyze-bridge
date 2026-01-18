import json
import os
import time
from functools import wraps
from pathlib import Path
from threading import Thread
from urllib.parse import quote_plus

from flask import (
    Flask,
    Response,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
)
from werkzeug.exceptions import NotFound

from wyzebridge.build_config import VERSION
from wyze_bridge import WyzeBridge
from wyzebridge import config, web_ui
from wyzebridge.auth import WbAuth
from wyzebridge.web_ui import url_for

def create_app():
    app = Flask(__name__)
    wb = WyzeBridge()
    # Start bridge initialization in background thread so Flask can start even if auth fails
    Thread(target=wb._initialize, kwargs={"fresh_data": False}, daemon=True).start()

    def auth_required(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if not wb.api.auth:
                return redirect(url_for("wyze_login"))
            return web_ui.auth.login_required(view)(*args, **kwargs)

        return wrapped_view

    @app.route("/login", methods=["GET", "POST"])
    def wyze_login():
        if wb.api.auth:
            return redirect(url_for("index"))
        if request.method == "GET":
            return render_template(
                "login.html",
                api=WbAuth.api,
                version=VERSION,
            )

        tokens = request.form.get("tokens")
        refresh = request.form.get("refresh")

        if tokens or refresh:
            wb.api.token_auth(tokens=tokens, refresh=refresh)
            return {"status": "success"}

        credentials = {
            "email": request.form.get("email"),
            "password": request.form.get("password"),
            "key_id": request.form.get("keyId"),
            "api_key": request.form.get("apiKey"),
        }

        if all(credentials.values()):
            wb.api.creds.update(**credentials)
            return {"status": "success"}

        return {"status": "missing credentials"}

    @app.route("/")
    @auth_required
    def index():
        if not (columns := request.args.get("columns")):
            columns = request.cookies.get("number_of_columns", "2")

        if not (refresh := request.args.get("refresh")):
            refresh = request.cookies.get("refresh_period", "30")

        number_of_columns = int(columns) if columns.isdigit() else 0
        refresh_period = int(refresh) if refresh.isdigit() else 0
        show_video = bool(request.cookies.get("show_video", "1"))

        if "video" in request.args:
            show_video = True
        elif "snapshot" in request.args:
            show_video = False

        # Format camera data for WebUI
        # Reload disabled cams to ensure UI is in sync with file storage
        wb.disabled_cams = wb.load_disabled_cams()
        cam_data = {
            uri: {
                "name_uri": uri,
                "nickname": cam.nickname,
                "product_model": cam.product_model,
                "model_name": cam.model_name,
                "webrtc_support": cam.webrtc_support,
                "webrtc": cam.webrtc_support,  # For template compatibility
                "enabled": True,  # go2rtc handles on-demand
                "online": cam.ip is not None,
                "connected": True,  # go2rtc handles connections
                "enabled": uri not in wb.disabled_cams,
                "img_url": f"/thumb/{uri}.jpg",
                "webrtc_url": f"/webrtc/{uri}",
                "rtsp_url": f"rtsp://{request.host.split(':')[0]}:8554/{uri}",
                "mac": cam.mac,
                "firmware_ver": cam.firmware_ver,
                "is_battery": cam.is_battery,
                "camera_info": cam.camera_info,
                "substream": False,  # No substreams in KVS mode
                "on_demand": False,  # Always available in KVS mode
            }
            for uri, cam in wb.cameras.items()
        }

        resp = make_response(
            render_template(
                "index_kvs.html",
                cam_data=cam_data,
                total_cams=len(wb.cameras),
                api=WbAuth.api,
                version=VERSION,
            )
        )

        resp.set_cookie("number_of_columns", str(number_of_columns))
        resp.set_cookie("refresh_period", str(refresh_period))
        resp.set_cookie("show_video", "1" if show_video else "")
        fullscreen = "fullscreen" in request.args or bool(
            request.cookies.get("fullscreen")
        )
        resp.set_cookie("fullscreen", "1" if fullscreen else "")
        if order := request.args.get("order"):
            resp.set_cookie("camera_order", quote_plus(order))

        return resp

    @app.route("/health")
    def health():
        """Add-on health check."""
        health_data = wb.health()
        return Response(json.dumps(health_data), mimetype="application/json")
    
    @app.route("/api/sse_status")
    @auth_required
    def sse_status():
        """Server sent event for camera status."""
        def get_status():
            return {
                uri: {"status": "online" if cam.ip else "offline", "motion": 0}
                for uri, cam in wb.cameras.items()
            }
        return Response(
            web_ui.sse_generator(get_status),
            mimetype="text/event-stream",
        )

    @app.route("/api")
    @auth_required
    def api_all_cams():
        return {
            uri: {
                "name_uri": uri,
                "nickname": cam.nickname,
                "product_model": cam.product_model,
                "webrtc_support": cam.webrtc_support,
                "online": cam.ip is not None,
            }
            for uri, cam in wb.cameras.items()
        }

    @app.route("/api/<string:cam_name>")
    @auth_required
    def api_cam(cam_name: str):
        if cam := wb.cameras.get(cam_name):
            return {
                "name_uri": cam_name,
                "nickname": cam.nickname,
                "product_model": cam.product_model,
                "webrtc_support": cam.webrtc_support,
                "webrtc_url": f"/webrtc/{cam_name}",
                "rtsp_url": f"rtsp://{request.host.split(':')[0]}:8554/{cam_name}",
                "img_url": f"/thumb/{cam_name}.jpg",
                "mac": cam.mac,
                "online": cam.ip is not None,
            }
        return {"error": f"Could not find camera [{cam_name}]"}

    @app.route("/api/<cam_name>/rtsp")
    @auth_required
    def api_rtsp_url(cam_name: str):
        return {"rtsp_url": f"rtsp://{request.host.split(':')[0]}:8554/{cam_name}"}

    @app.route("/api/<cam_name>/start", methods=["POST"])
    @auth_required
    def api_start_stream(cam_name: str):
        # go2rtc handles on-demand streaming automatically
        if cam_name in wb.cameras:
            return {"status": "started", "note": "go2rtc handles on-demand"}
        return {"error": "Camera not found"}

    @app.route("/api/<cam_name>/stop", methods=["POST"])
    @auth_required
    def api_stop_stream(cam_name: str):
        # go2rtc handles on-demand streaming automatically
        if cam_name in wb.cameras:
            return {"status": "stopped", "note": "go2rtc handles on-demand"}
        return {"error": "Camera not found"}

    @app.route("/api/<cam_name>/<cam_cmd>", methods=["GET", "PUT", "POST"])
    @app.route("/api/<cam_name>/<cam_cmd>/<path:payload>")
    @auth_required
    def api_cam_control(cam_name: str, cam_cmd: str, payload: str | dict = ""):
        """Limited camera control via cloud API only."""
        # KVS WebRTC mode: no TUTK connection, limited cloud API control
        return {"error": "Camera control not supported in WebRTC-only mode", "command": cam_cmd}

    @app.route("/signaling/<string:name>")
    @auth_required
    def webrtc_signaling(name):
        # Always use KVS WebRTC
        return wb.api.get_kvs_signal(name)

    @app.route("/webrtc/<string:name>")
    @auth_required
    def webrtc(name):
        """View WebRTC direct from camera."""
        if (webrtc := wb.api.get_kvs_signal(name)).get("result") == "ok":
            return make_response(render_template("webrtc.html", webrtc=webrtc))
        return webrtc

    @app.route("/img/<string:img_file>")
    @auth_required
    def img(img_file: str):
        """Redirect to API thumbnail."""
        return thumbnail(img_file)

    @app.route("/thumb/<string:img_file>")
    @auth_required
    def thumbnail(img_file: str):
        """Serve thumbnail with local prioritization and cloud fallback."""
        uri = Path(img_file).stem
        file_path = config.IMG_PATH + img_file
        
        # Check if local file exists and is recent (e.g., < 180s)
        is_fresh = False
        if os.path.exists(file_path):
            age = time.time() - os.path.getmtime(file_path)
            is_fresh = age < 180
        
        # If stale or missing, try to update from cloud
        if not is_fresh:
            try:
                wb.api.save_thumbnail(uri, "")
            except Exception:
                pass  # Ignore cloud errors, use local fallback

        # Serve local file if it exists (even if stale)
        if os.path.exists(file_path):
             return send_from_directory(config.IMG_PATH, img_file)

        return redirect("/static/notavailable.svg", code=307)


    @app.route("/api/camera/<string:uri>/<string:action>", methods=["POST"])
    @auth_required
    def camera_action(uri, action):
        """Enable or disable camera."""
        if action == "enable":
            wb.toggle_cam(uri, True)
        elif action == "disable":
            wb.toggle_cam(uri, False)
        return {"status": "ok", "enabled": uri not in wb.disabled_cams}

    @app.route("/favicon.ico")
    def favicon():
        """Serve favicon or return empty response to suppress 404."""
        return '', 204

    @app.route("/restart/<string:restart_cmd>")
    @auth_required
    def restart_bridge(restart_cmd: str):
        """
        Restart the wyze-bridge.

        /restart/cameras:  Refresh camera list.
        /restart/all:      Re-authenticate and refresh cameras.
        """
        if restart_cmd == "cameras" or restart_cmd == "cam_data":
            wb.refresh_cams()
            return {"result": "ok", "restart": ["cameras"]}
        elif restart_cmd == "all":
            wb.restart(fresh_data=True)
            return {"result": "ok", "restart": ["all"]}
        else:
            return {"result": "error", "message": "Invalid restart command"}


    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=False, host="0.0.0.0", port=5000)
