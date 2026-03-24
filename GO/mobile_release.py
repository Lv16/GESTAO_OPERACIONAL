import os
import re
from glob import glob


MOBILE_UA_RE = re.compile(
    r"Mobile|Android|iPhone|iPad|iPod|Opera Mini|IEMobile|WPDesktop",
    re.I,
)


def _env_bool(varname, default=False):
    raw = (os.environ.get(varname) or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in ("1", "true", "yes", "on")


def request_is_mobile(request):
    try:
        for source in (getattr(request, "GET", None), getattr(request, "POST", None)):
            if source is None:
                continue
            for key in ("mobile", "force_mobile"):
                raw_value = source.get(key)
                if str(raw_value or "").strip().lower() in ("1", "true", "yes", "on"):
                    return True
        ua = ""
        try:
            ua = request.META.get("HTTP_USER_AGENT", "") or ""
        except Exception:
            ua = ""
        return bool(ua and MOBILE_UA_RE.search(ua))
    except Exception:
        return False


def extract_version_name_from_text(raw_value):
    text = str(raw_value or "").strip()
    if not text:
        return ""
    match = re.search(r"v(\d+\.\d+\.\d+(?:[+-][A-Za-z0-9._-]+)?)", text)
    if not match:
        return ""
    version_name = str(match.group(1) or "").strip()
    lowered = version_name.lower()
    if lowered.endswith(".apk") or lowered.endswith(".aab"):
        version_name = version_name[:-4]
    return version_name


def extract_build_number(*raw_values):
    for raw in raw_values:
        value = str(raw or "").strip()
        if not value:
            continue

        if "+" in value:
            suffix = value.rsplit("+", 1)[-1].strip()
            try:
                return int(suffix)
            except Exception:
                pass

        match = re.search(r"build[^\d]*(\d+)", value, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except Exception:
                pass

        match_digits = re.search(r"(\d+)(?!.*\d)", value)
        if match_digits:
            try:
                return int(match_digits.group(1))
            except Exception:
                pass
    return None


def discover_latest_android_release():
    globs_to_scan = []
    custom_glob = (os.environ.get("MOBILE_APP_ANDROID_RELEASE_GLOB") or "").strip()
    if custom_glob:
        globs_to_scan.append(custom_glob)

    globs_to_scan.extend(
        [
            "/var/www/html/GESTAO_OPERACIONAL/static/mobile/releases/ambipar-synchro-v*.apk",
            "/var/www/mobile/rdo_offline_app/dist/android/*/ambipar-synchro-v*.apk",
        ]
    )

    best = None
    for pattern in globs_to_scan:
        try:
            candidates = glob(pattern)
        except Exception:
            candidates = []

        for apk_path in candidates:
            filename = os.path.basename(apk_path)
            lowered = filename.lower()
            if not lowered.endswith(".apk"):
                continue
            if "-hml-" in lowered or "homolog" in lowered or "uml" in lowered:
                continue

            version_name = extract_version_name_from_text(filename)
            if not version_name:
                continue
            build_number = extract_build_number(version_name, filename)
            if build_number is None:
                continue
            try:
                mtime = float(os.path.getmtime(apk_path))
            except Exception:
                mtime = 0.0

            candidate = {
                "version_name": version_name,
                "build_number": int(build_number),
                "apk_path": apk_path,
                "_mtime": mtime,
            }

            if best is None:
                best = candidate
                continue
            if int(candidate["build_number"]) > int(best["build_number"]):
                best = candidate
                continue
            if (
                int(candidate["build_number"]) == int(best["build_number"])
                and candidate["_mtime"] > best["_mtime"]
            ):
                best = candidate

    if best is None:
        return None
    best.pop("_mtime", None)
    return best


def android_release_download_url(request, apk_path=""):
    base_static_dir = "/var/www/html/GESTAO_OPERACIONAL/static/mobile/releases"
    filename = os.path.basename(str(apk_path or "").strip())
    if filename:
        static_filename_path = os.path.join(base_static_dir, filename)
        if os.path.exists(static_filename_path):
            return request.build_absolute_uri(f"/static/mobile/releases/{filename}")

    latest_alias = os.path.join(base_static_dir, "ambipar-synchro-latest.apk")
    if os.path.exists(latest_alias):
        return request.build_absolute_uri("/static/mobile/releases/ambipar-synchro-latest.apk")
    return ""


def resolve_mobile_release_context(request):
    discovered_android_release = discover_latest_android_release() or {}

    discovered_android_url = android_release_download_url(
        request,
        discovered_android_release.get("apk_path"),
    )

    env_android_url = (os.environ.get("MOBILE_APP_ANDROID_URL") or "").strip()
    env_android_lower = env_android_url.lower()
    env_android_is_official = bool(
        env_android_url
        and "hml" not in env_android_lower
        and "homolog" not in env_android_lower
        and "uml" not in env_android_lower
    )

    android_url = discovered_android_url or (env_android_url if env_android_is_official else "")
    android_version_name = str(
        discovered_android_release.get("version_name")
        or (os.environ.get("MOBILE_APP_ANDROID_VERSION_NAME") or "").strip()
        or extract_version_name_from_text(android_url)
    ).strip()
    android_build_number = extract_build_number(
        discovered_android_release.get("build_number"),
        android_version_name,
        android_url,
    )
    if android_build_number is None:
        android_build_number = 0

    ios_url = (os.environ.get("MOBILE_APP_IOS_URL") or "").strip()
    enabled = _env_bool("MOBILE_APP_DOWNLOAD_ENABLED", False) or bool(android_url or ios_url)

    return {
        "mobile_app_download_enabled": enabled,
        "mobile_app_android_url": android_url,
        "mobile_app_android_version_name": android_version_name,
        "mobile_app_android_build_number": int(android_build_number or 0),
        "mobile_app_ios_url": ios_url,
    }
