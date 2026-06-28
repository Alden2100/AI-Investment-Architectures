"""System sandbox bootstrap — import this FIRST, before any imdata/imrouter import.

Sets the env (cache dir, DB path, router log/policy, skills dir) and puts the shared
library on sys.path, exactly as the original orchestrator did inline. Importing this
module performs the setup as a side effect and exposes HERE / LIB / DATA_DIR.
"""
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
_d, LIB = HERE, None
while _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "skills-library")):
        LIB = os.path.join(_d, "skills-library"); break
    _d = os.path.dirname(_d)


def _writable_dir(_p):
    """Use _p if writable, else a per-user cache dir (read-only plugin installs /
    OneDrive-synced trees where SQLite can't open a DB next to the code)."""
    try:
        os.makedirs(_p, exist_ok=True); _t = os.path.join(_p, ".w"); open(_t, "w").close(); os.remove(_t); return _p
    except OSError:
        _a = os.path.join(os.path.expanduser("~"), ".cache", "im-ai-skills", os.path.basename(HERE)); os.makedirs(_a, exist_ok=True); return _a


DATA_DIR = _writable_dir(os.path.join(HERE, "data"))
_envf = os.path.join(os.path.dirname(LIB), ".env")
if os.path.exists(_envf):
    for _ln in open(_envf):
        _ln = _ln.strip()
        if _ln and not _ln.startswith("#") and "=" in _ln:
            _k, _v = _ln.split("=", 1); os.environ.setdefault(_k.strip(), _v.strip().strip('"'))
os.environ.setdefault("IM_LIB_ROOT", LIB)
os.environ.setdefault("IM_SKILLS_DIR", os.path.join(HERE, ".claude", "skills"))
os.environ.setdefault("TOOLBOX_CACHE_DIR", DATA_DIR)
os.environ.setdefault("TOOLBOX_DB_PATH", os.path.join(DATA_DIR, "idea-sourcing.db"))
os.environ.setdefault("IM_ROUTER_LOG", os.path.join(DATA_DIR, "router_decisions.jsonl"))
os.environ.setdefault("IM_ROUTER_POLICY", os.path.join(HERE, "router-policy.yaml"))
for _p in ("data-fetch", "router", "web-search"):
    _sp = os.path.join(LIB, "_shared", _p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)
