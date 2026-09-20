import hashlib
import json
import time
from pathlib import Path
from . import native
from .models import Signal, Result


def signal(detector, kind, title, confidence, weight, evidence, explanation, limitation):
    identity = json.dumps([detector, kind, evidence], sort_keys=True)
    return Signal(hashlib.sha256(identity.encode()).hexdigest()[:16], detector, title,
                  confidence, weight, evidence, explanation, limitation)


class Detector:
    name = "Detector"
    scope = ""

    def scan(self, context):
        raise NotImplementedError

    def close(self):
        pass


class ProcessDetector(Detector):
    name, scope = "ProcessDetector", "processes"

    def __init__(self):
        self.rules = json.loads((Path(__file__).with_name("rules.json")).read_text())

    def scan(self, context):
        procs = native.processes()
        signals = []
        for p in procs:
            pname = p["name"].casefold().removesuffix(".exe")
            meta = p.get("metadata") or {}
            orig = meta.get("OriginalFilename", "").casefold().removesuffix(".exe")
            desc = meta.get("FileDescription", "").casefold()
            prod = meta.get("ProductName", "").casefold()

            for rule in self.rules:
                rule_names = set(rule["names"])
                if pname in rule_names:
                    signals.append(signal(
                        self.name, "name_match", "Application name matches a review rule",
                        0.65, rule["weight"], {"process": pname, "category": rule["category"]},
                        "An application with this executable name is running.",
                        "Name-only match: it can be renamed, spoofed, or used for an agreed accommodation. "
                        "Presence does not demonstrate use during this interview."
                    ))
                elif orig and orig in rule_names:
                    signals.append(signal(
                        self.name, "renamed_match", "Renamed application matches a review rule",
                        0.80, rule["weight"],
                        {"process": pname, "original_filename": orig, "category": rule["category"]},
                        f"A running application '{pname}' has an internal binary filename '{orig}' matching review rules.",
                        "The binary metadata matches despite being renamed. Presence does not establish active interview interaction."
                    ))
                elif any(rn in desc or rn in prod for rn in rule_names):
                    matched_kw = next((rn for rn in rule_names if rn in desc or rn in prod), "")
                    matched_label = prod if matched_kw in prod else desc
                    signals.append(signal(
                        self.name, "metadata_match", "Application metadata matches a review rule",
                        0.75, rule["weight"],
                        {"process": pname, "matched_product": matched_label[:50], "category": rule["category"]},
                        "The application's embedded file description or product metadata matches a review keyword.",
                        "Metadata reflects vendor package descriptions; presence does not demonstrate interview interference."
                    ))
        deduped = list({s.id: s for s in signals}.values())
        return Result(self.name, "partial", "Executable names and binary metadata; no paths or arguments retained.", deduped)



class OverlayDetector(Detector):
    name, scope = "OverlayDetector", "windows"

    def __init__(self):
        self.previous = None
        self.transitions = []

    def scan(self, context):
        rows = native.windows()
        signals = []
        overlay_ids = set()
        for row in rows:
            combo = row["topmost"] and (row["layered"] or row["clickthrough"])
            if combo:
                overlay_ids.add(row["id"])
                # Window handles stay transient. Evidence contains only properties.
                ev = {k: row[k] for k in ("topmost", "layered", "clickthrough", "alpha")}
                signals.append(signal(self.name, "overlay", "Overlay-style window observed", .8, .5, ev,
                    "A visible window combines elevated stacking and overlay-like attributes.",
                    "Captions, accessibility tools, meeting controls and notifications can look identical."))
            if row["affinity"] in (1, 0x11):
                signals.append(signal(self.name, "capture_affinity", "Capture-restricted window observed",
                    .95, .65, {"affinity": row["affinity"]},
                    "The OS returned a capture-protection setting for a visible window.",
                    "A protection flag is legitimate for many applications. Query failures are unknown."))
        now = time.monotonic()
        if self.previous is not None and self.previous != overlay_ids:
            self.transitions.append(now)
        self.previous = overlay_ids
        self.transitions = [t for t in self.transitions if now - t < 60]
        if len(self.transitions) >= 4:
            signals.append(signal(self.name, "transitions", "Repeated overlay changes", .7, .45,
                {"window_seconds": 60, "threshold": 4}, "Overlay membership changed in at least four samples.",
                "Polling can miss changes between samples; ordinary UI changes cause this too."))
        signals = list({s.id: s for s in signals}.values())
        return Result(self.name, "partial", "Public window metadata; GPU-only overlays are not observable.",
                      signals, {"capture_affinity_observable": any(r["affinity"] is not None for r in rows)})


class AudioCaptureDetector(Detector):
    name, scope = "AudioCaptureDetector", "audio_devices"

    def scan(self, context):
        devices = native.audio_devices()
        signals = []
        for d in devices:
            if any(word in d["name"].casefold() for word in
                   ("blackhole", "soundflower", "loopback", "cable output", "stereo mix")):
                signals.append(signal(self.name, "routing_device", "Audio routing device available",
                    .7, .2, {"device": d["name"]}, "An input device name suggests loopback or routing support.",
                    "Installed does not mean active. No audio is captured; listener conflicts and STT use are unknown."))
        return Result(self.name, "partial", "Input-device inventory only. Per-app audio capture is unsupported.",
                      signals, {"capture_conflicts": None, "audio_recorded": False})


class VirtualDisplayDetector(Detector):
    name, scope = "VirtualDisplayDetector", "displays"

    def scan(self, context):
        devices = native.displays()
        signals = [signal(self.name, "virtual_hint", "Display adapter reports a virtual-display hint",
                    .6, .4, {"label": d["label"]}, "An attached adapter has a mirror flag or matching device name.",
                    "This is a driver hint, not proof of a hidden monitor; legitimate remote desktop tools match.")
                   for d in devices if d["virtual_hint"]]
        return Result(self.name, "partial", "Active display metadata only; concealed hardware is not detectable.",
                      signals, {"active_displays": len(devices)})


class BrowserExtensionDetector(Detector):
    name, scope = "BrowserExtensionDetector", "extensions"

    def scan(self, context):
        inventory = context.get("extensions")
        if inventory is None:
            return Result(self.name, "disabled", "Import a candidate-reviewed companion inventory to enable.")
        signals = []
        for entry in inventory:
            if entry["enabled"] and any(x in entry["name"].casefold()
                                         for x in ("interview", "transcrib", "transcript", "overlay")):
                signals.append(signal(self.name, "extension_name", "Extension name matches a review keyword",
                    .5, .4, {"extension": entry["name"], "source": "candidate_import"},
                    "A candidate-supplied enabled extension name matches a broad keyword.",
                    "Inventory is self-reported, may be stale or incomplete, and covers one browser profile."))
        return Result(self.name, "partial", "Candidate-supplied inventory; no browser profiles are read.", signals)


def registry():
    from .gaze import GazeDetector
    from .probes import NativeProbe
    return [NativeProbe(OverlayDetector), NativeProbe(ProcessDetector),
            NativeProbe(AudioCaptureDetector), GazeDetector(),
            NativeProbe(VirtualDisplayDetector), BrowserExtensionDetector()]
