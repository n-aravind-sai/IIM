import base64
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(session_id, sequence, previous, payload):
    return hashlib.sha256(canonical([session_id, sequence, previous, payload]).encode()).hexdigest()


def verify(bundle, trusted_public_key=None):
    """Returns false on edits, reordering or truncation against the signed manifest.

    Caller must pin a separately trusted key to authenticate source identity.
    A self-contained export without pinning only proves internal consistency.
    """
    try:
        public = bundle["public_key"]
        if trusted_public_key is not None and public != trusted_public_key:
            return False
        manifest = bundle["manifest"]
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public, validate=True))
        key.verify(base64.b64decode(bundle["signature"], validate=True), canonical(manifest).encode())
        previous = "0" * 64
        for i, event in enumerate(bundle["events"], 1):
            if event["sequence"] != i or event["previous_hash"] != previous:
                return False
            expected = digest(manifest["session"]["id"], i, previous, event["payload_json"])
            if event["event_hash"] != expected:
                return False
            previous = expected
        return manifest["event_count"] == len(bundle["events"]) and manifest["head"] == previous
    except Exception:
        return False


if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    _CryptProtectData = ctypes.windll.crypt32.CryptProtectData
    _CryptProtectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DATA_BLOB),
    ]
    _CryptProtectData.restype = wintypes.BOOL

    _CryptUnprotectData = ctypes.windll.crypt32.CryptUnprotectData
    _CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DATA_BLOB),
    ]
    _CryptUnprotectData.restype = wintypes.BOOL

    _LocalFree = ctypes.windll.kernel32.LocalFree
    _LocalFree.argtypes = [ctypes.c_void_p]
    _LocalFree.restype = ctypes.c_void_p

    def dpapi_protect(data: bytes, description: str = "IIM Audit Key") -> bytes:
        in_buf = (ctypes.c_byte * len(data))(*data)
        blob_in = _DATA_BLOB(len(data), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_byte)))
        blob_out = _DATA_BLOB()
        if not _CryptProtectData(ctypes.byref(blob_in), description, None, None, None, 1, ctypes.byref(blob_out)):
            raise ctypes.WinError(ctypes.GetLastError())
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            _LocalFree(blob_out.pbData)

    def dpapi_unprotect(data: bytes) -> bytes:
        in_buf = (ctypes.c_byte * len(data))(*data)
        blob_in = _DATA_BLOB(len(data), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_byte)))
        blob_out = _DATA_BLOB()
        if not _CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 1, ctypes.byref(blob_out)):
            raise ctypes.WinError(ctypes.GetLastError())
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            _LocalFree(blob_out.pbData)
else:
    def dpapi_protect(data: bytes, description: str = "IIM Audit Key") -> bytes:
        return data

    def dpapi_unprotect(data: bytes) -> bytes:
        return data


class AuditStore:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            directory.chmod(0o700)
        self.directory = directory
        keypath = directory / "signing-key.bin"
        if not keypath.exists():
            key = Ed25519PrivateKey.generate()
            raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                    serialization.NoEncryption())
            protected = dpapi_protect(raw) if os.name == "nt" else raw
            try:
                fd = os.open(keypath, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as f:
                    f.write(protected)
            except FileExistsError:
                pass
        stored = keypath.read_bytes()
        if os.name == "nt":
            if len(stored) == 32:
                # Raw legacy key: automatically upgrade to DPAPI protection
                raw_key = stored
                try:
                    keypath.write_bytes(dpapi_protect(raw_key))
                except Exception:
                    pass
            else:
                raw_key = dpapi_unprotect(stored)
        else:
            raw_key = stored
        self.key = Ed25519PrivateKey.from_private_bytes(raw_key)
        self.db = sqlite3.connect(directory / "sessions.sqlite3", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript((Path(__file__).parent.parent / "schema.sql").read_text())
        with self.db:
            for row in self.db.execute("SELECT id FROM sessions WHERE status='active'").fetchall():
                self.append(row["id"], "interrupted", {"reason": "Worker restarted; observations may be missing"})
                self.db.execute("UPDATE sessions SET status='interrupted',ended_at=? WHERE id=?", (now(), row["id"]))
                self._seal(row["id"])
            self.db.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),))
        if os.name != "nt":
            (directory / "sessions.sqlite3").chmod(0o600)

    def create(self, session_id, consent):
        expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        with self.db:
            self.db.execute("INSERT INTO sessions VALUES(?,?,NULL,?,'active',?)",
                            (session_id, now(), expires, canonical(consent)))
            self.append(session_id, "consent", consent)

    def append(self, session_id, kind, data):
        if self.db.execute("SELECT 1 FROM seals WHERE session_id=?", (session_id,)).fetchone():
            self.export(session_id)  # Validate the previously signed checkpoint before extending it.
        tail = self.db.execute("SELECT sequence,event_hash FROM events WHERE session_id=? ORDER BY sequence DESC LIMIT 1",
                               (session_id,)).fetchone()
        sequence, previous = (tail["sequence"] + 1, tail["event_hash"]) if tail else (1, "0" * 64)
        payload = canonical({"time": now(), "kind": kind, "data": data})
        hashed = digest(session_id, sequence, previous, payload)
        with self.db:
            self.db.execute("INSERT INTO events VALUES(?,?,?,?,?)", (session_id, sequence, payload, previous, hashed))
            self._seal(session_id)

    def stop(self, session_id, reason):
        self.append(session_id, "stopped", {"reason": reason})
        with self.db:
            self.db.execute("UPDATE sessions SET status='stopped',ended_at=? WHERE id=?", (now(), session_id))
            self._seal(session_id)

    def _parts(self, session_id):
        session = self.db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if session is None:
            raise ValueError("Session not found")
        session = dict(session)
        session["consent"] = json.loads(session.pop("consent_json"))
        events = [dict(row) for row in self.db.execute(
            "SELECT sequence,payload_json,previous_hash,event_hash FROM events WHERE session_id=? ORDER BY sequence",
            (session_id,))]
        manifest = {"format": "iim.audit.v1", "session": session, "event_count": len(events),
                    "head": events[-1]["event_hash"] if events else "0" * 64}
        return manifest, events

    def _seal(self, session_id):
        manifest, _ = self._parts(session_id)
        encoded = canonical(manifest)
        public = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.db.execute("INSERT OR REPLACE INTO seals VALUES(?,?,?,?)", (session_id, encoded,
            base64.b64encode(self.key.sign(encoded.encode())).decode(), base64.b64encode(public).decode()))

    def export(self, session_id):
        computed, events = self._parts(session_id)
        seal = self.db.execute("SELECT * FROM seals WHERE session_id=?", (session_id,)).fetchone()
        if seal is None:
            raise ValueError("Audit checkpoint is missing")
        manifest = json.loads(seal["manifest_json"])
        bundle = {"manifest": manifest, "events": events, "signature": seal["signature"], "public_key": seal["public_key"]}
        if computed != manifest or not verify(bundle):
            raise ValueError("Audit verification failed; preserve the data for manual review")
        return bundle

    def delete(self, session_id):
        with self.db:
            self.db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        self.db.execute("VACUUM")

    def prune(self):
        with self.db:
            self.db.execute("DELETE FROM sessions WHERE expires_at < ? AND status != 'active'", (now(),))

    @property
    def public_key_base64(self):
        public = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return base64.b64encode(public).decode()

    def get_head(self, session_id):
        row = self.db.execute("SELECT event_hash FROM events WHERE session_id=? ORDER BY sequence DESC LIMIT 1",
                              (session_id,)).fetchone()
        return row["event_hash"] if row else ("0" * 64)

