"""WS-G unit tests: registry generation, T13 stats, JPEG fallback, peer, bringup dry-run (D13a)."""

from __future__ import annotations

import asyncio
import io
import json
import struct
import subprocess
import sys

import pytest
from edith_tools.commands import g

ROOT = g.ROOT


def test_registry_19_tests_g0_tags_and_up_to_date():
    reg = g.build_registry()
    assert reg["count"] == 19
    assert [t["id"] for t in reg["tests"]] == [f"T{i}" for i in range(19)]
    assert {t["id"] for t in reg["tests"] if "g0" in t["tags"]} == g.G0_EXPECTED
    assert all(t["pass"] and t["owners"] for t in reg["tests"])
    assert g.cmd_registry(["--check"]) == 0, "run ./edith glasses registry"


def test_t13_stats_latency_definition():
    sent = {i: i * 0.1 for i in range(100)}
    echoes = {i: (i * 0.1 + 0.050, 10.0) for i in range(99)}  # RTT 50 ms incl. 10 ms decode
    s = g.t13_stats(sent, echoes, 15, 10.0)
    assert s["dropped"] == 1 and s["drop_pct"] == 1.0
    assert s["rtt_ms_p95"] == pytest.approx(50.0, abs=0.01)
    assert s["latency_ms_p95"] == pytest.approx((50 - 10) / 2 + 10, abs=0.01)
    assert s["pass"] is False  # decode p95 10 ms is not < 10


def test_pure_jpeg_encoder_decodes():
    Image = pytest.importorskip("PIL.Image")
    data = g.encode_jpeg_pure(64, 32, lambda x, y: ((x * 4) % 256, (y * 8) % 256, 100))
    im = Image.open(io.BytesIO(data))
    im.load()
    assert im.size == (64, 32)
    r, gg, b = im.getpixel((10, 10))
    assert abs(r - 40) < 12 and abs(gg - 80) < 12 and abs(b - 100) < 12


def test_peer_t9_t13_roundtrip(tmp_path):
    aiohttp = pytest.importorskip("aiohttp")
    from aiohttp import web

    async def run():
        peer = g.Peer(tmp_path / "run", "tok", quiet=True)
        runner = web.AppRunner(g.make_app(peer))
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}/v1/selftest"
        async with aiohttp.ClientSession() as s:
            r = await s.get(f"{base}?test=t9&token=bad")
            assert r.status == 401
            async with s.ws_connect(f"{base}?test=t9&token=tok") as ws:
                assert (await ws.receive_json())["type"] == "hello"
                await ws.send_json({"type": "t9.start", "segment": "a b", "source": "MIC", "rate": 16000, "channels": 1})
                await ws.send_bytes(struct.pack("<4h", 1000, -1000, 1000, -1000))
                await ws.send_json({"type": "t9.end", "segment": "a b"})
                saved = await ws.receive_json()
                assert saved["samples"] == 4 and saved["path"].endswith("t9_a_b.wav")
            async with s.ws_connect(f"{base}?test=t13&token=tok") as ws:
                await ws.receive_json()
                await ws.send_json({"type": "t13.start", "fps": 15, "seconds": 1})
                while True:
                    m = await ws.receive()
                    if m.type == aiohttp.WSMsgType.BINARY:
                        fid = struct.unpack(">I", m.data[1:5])[0]
                        assert m.data[0] == 0x0D and m.data[5:7] == b"\xff\xd8"
                        await ws.send_json({"type": "t13.echo", "frame_id": fid, "recv_to_decoded_ms": 1.0})
                    else:
                        res = json.loads(m.data)
                        if res["type"] == "t13.result":
                            break
                assert res["sent"] == 15 and res["dropped"] == 0
            r = await s.get(f"{base}/t11/down?bytes=1000&token=tok")
            assert len(await r.read()) == 1000
        await runner.cleanup()

    asyncio.run(run())
    assert (tmp_path / "run" / "t9_a_b.wav").stat().st_size == 44 + 8


@pytest.mark.parametrize("tier", ["g0", "all"])
def test_bringup_dry_run_validates(tmp_path, tier):
    out = tmp_path / "dry.json"
    p = subprocess.run(["bash", str(ROOT / "tools/bringup.sh"), "--dry-run", "--tier", tier, "--out", str(out)],
                       capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == 0, p.stdout + p.stderr
    assert g.validate_file(ROOT / "docs/bringup/bringup.schema.json", out) == []
    doc = json.loads(out.read_text())
    ids = [s["id"] for s in doc["steps"]]
    assert {"T0", "T1", "T3", "T4", "install", "provision", "pull"} <= set(ids)
    assert ("T2" in ids) == (tier == "all")
    assert any("INSTALL_FAILED_UPDATE_INCOMPATIBLE" in s["detail"] for s in doc["steps"])
    assert doc["ok"] is True


def test_committed_dryrun_json_validates():
    assert g.validate_file(ROOT / "docs/bringup/bringup.schema.json", ROOT / "docs/bringup/dryrun.json") == []


def test_main_routes_with_and_without_glasses_prefix(capsys):
    assert g.main(["glasses", "registry", "--check"]) == 0
    assert g.main(["registry", "--check"]) == 0
    assert g.main(["glasses", "nope"]) == 2


def test_standalone_module_runs():
    p = subprocess.run([sys.executable, "-m", "edith_tools.commands.g", "--help"], capture_output=True, text=True,
                       cwd=ROOT, env={"PYTHONPATH": str(ROOT / "tools"), "PATH": "/usr/bin:/bin"})
    assert p.returncode == 0 and "selftest --serve" in p.stdout
