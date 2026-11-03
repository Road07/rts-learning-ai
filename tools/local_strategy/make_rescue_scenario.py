"""Build a separate local-only scripted test package, preserving installed files."""
import hashlib
from pathlib import Path
import shutil
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "release"))
from audit_package import pck_entries
sys.path.insert(0, str(HERE.parent / "audio"))
from bigread import Mount


def pack(entries):
    header_size = 104
    blobs = bytearray()
    directory = bytearray(struct.pack("<I", len(entries)))
    for name, content in entries:
        path = name.encode() + b"\0"
        path += b"\0" * (-len(path) % 4)
        directory += struct.pack("<I", len(path)) + path
        directory += struct.pack("<QQ", len(blobs), len(content))
        directory += hashlib.md5(content).digest() + struct.pack("<I", 0)
        blobs += content
    return (b"GDPC" + struct.pack("<5I", 4, 4, 7, 2, 2)
            + struct.pack("<QQ", header_size, header_size + len(blobs))
            + b"\0" * 64 + blobs + directory)


def main():
    dest = ROOT / "AI-3v3-Test"
    dest.mkdir(exist_ok=True)
    entries = dict(pck_entries((ROOT / "OpenBFME.pck").read_bytes()))
    source = entries["scripts/game.gd"].decode("utf-8")
    marker = "func _process(delta: float) -> void:\n"
    assert source.count(marker) == 1
    source = source.replace(marker, marker +
        '\tif not has_meta("rescue_driver"):\n'
        '\t\tvar driver = load("res://scripts/rescue_scenario.gd").new()\n'
        '\t\tadd_child(driver)\n\t\tdriver.setup(self)\n'
        '\t\tset_meta("rescue_driver", driver)\n'
        '\tget_meta("rescue_driver").tick()\n')
    # The headless verification can use the existing --auto lobby flow.
    before = '\tvar spec := {\n\t\t"map": _map_key,\n\t\t"slots": slots,\n\t}'
    assert source.count(before) == 1
    source = source.replace(before,
        '\tif OS.get_cmdline_user_args().has("--rescue-auto"):\n'
        '\t\tslots = [{"slot": 0, "faction": "FactionMen", "team": 1, "start_pos": 3},\n'
        '\t\t\t{"slot": 1, "state": 4, "faction": "FactionMen", "team": 0, "start_pos": 0},\n'
        '\t\t\t{"slot": 2, "state": 4, "faction": "FactionMen", "team": 0, "start_pos": 1},\n'
        '\t\t\t{"slot": 3, "state": 4, "faction": "FactionElves", "team": 0, "start_pos": 2},\n'
        '\t\t\t{"slot": 4, "state": 4, "faction": "FactionWild", "team": 1, "start_pos": 4},\n'
        '\t\t\t{"slot": 5, "state": 4, "faction": "FactionWild", "team": 1, "start_pos": 5}]\n' + before)
    entries["scripts/game.gd"] = source.encode()
    entries["scripts/rescue_scenario.gd"] = (HERE / "rescue_scenario.gd").read_bytes()
    entries["scripts/rescue_order_policy.gd"] = (HERE / "rescue_order_policy.gd").read_bytes()
    entries["scripts/ai_diagnostics.gd"] = (HERE / "ai_diagnostics.gd").read_bytes()
    packed = pack(list(entries.items()))
    assert dict(pck_entries(packed)) == entries
    (dest / "OpenBFME.pck").write_bytes(packed)
    for name in ["OpenBFME.exe", "OpenBFME.console.exe", "openbfme.windows.template_debug.x86_64.dll"]:
        if not (dest / name).exists():
            shutil.copy2(ROOT / name, dest / name)
    mount = Mount("D:/Games/RotWK", "D:/Games/BFME2")
    ai = mount.get(r"data\ini\default\skirmishaidata.ini").decode("latin1")
    import re
    ai, n = re.subn(r"(DisableTacticalAI\s*=\s*)No", r"\g<1>Yes", ai, flags=re.I)
    assert n == 1
    ai, n = re.subn(r"(DisableTeamBuilding\s*=\s*)No", r"\g<1>Yes", ai, flags=re.I)
    assert n == 1, "Disable original idle dispatch as well as tactical plans"
    mod = dest / "scenario-mod" / "data" / "ini" / "default"
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "skirmishaidata.ini").write_bytes(ai.encode("latin1"))
    print("Created", dest)
    cache = mount.get(r"maps\mapcache.ini").decode("latin1").replace("\r", "")
    for block in re.split(r"(?im)^MapCache\s+", cache)[1:]:
        if re.search(r"(?im)^\s*numPlayers\s*=\s*6\b", block):
            print("SIX_PLAYER_MAP", block.splitlines()[0])


if __name__ == "__main__":
    main()
