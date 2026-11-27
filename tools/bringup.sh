#!/usr/bin/env bash
# E.D.I.T.H. glasses bring-up, host side (WS-G; PLAN §5.3 D13a; docs/bringup/TESTS.md).
#
#   tools/bringup.sh [--tier g0|all]        T0–T4 + install + provision (default tier g0)
#   tools/bringup.sh --pull-only            pull results.json (+ gfxinfo) after the APK tests
#   tools/bringup.sh --install-only         install / reinstall only (T3)
#   tools/bringup.sh --dry-run --tier g0    everything against docs/bringup/fake-adb;
#                                           writes docs/bringup/dryrun.json (schema-validated)
# Options: --serial S, --apk PATH, --peer ws://ip:7400/v1/selftest, --peer-ip IP, --port N,
#          --token T, --wifi IP (T2 via that IP), --sample-apk PATH (vendor sample for T3),
#          --out FILE (record path).
# Peer: start `./edith glasses selftest --serve` first; this script reads runs/bringup/peer.json
# for the port and token. Records go to runs/bringup/<ts>/bringup.json.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PKG="edith.selftest"
ACT="$PKG/.SelfTestActivity"
REMOTE_RESULTS="/sdcard/Android/data/$PKG/files/results"
TIER="g0" DRY=0 SERIAL="" APK="" PEER="" PEER_IP="" PORT=7400 TOKEN="" WIFI="" SAMPLE_APK="" OUT=""
MODE="full"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tier) TIER="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    --serial) SERIAL="$2"; shift 2 ;;
    --apk) APK="$2"; shift 2 ;;
    --peer) PEER="$2"; shift 2 ;;
    --peer-ip) PEER_IP="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    --wifi) WIFI="$2"; shift 2 ;;
    --sample-apk) SAMPLE_APK="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --pull-only) MODE="pull"; shift ;;
    --install-only) MODE="install"; shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "bringup: unknown argument $1" >&2; exit 2 ;;
  esac
done
[[ "$TIER" == "g0" || "$TIER" == "all" ]] || { echo "bringup: --tier g0|all" >&2; exit 2; }

TS="$(date -u +%Y%m%dT%H%M%SZ)"
STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [[ $DRY -eq 1 ]]; then
  ADB="$ROOT/docs/bringup/fake-adb"
  RUN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/bringup-dry.XXXXXX")"
  export FAKE_ADB_STATE="$RUN_DIR/fake-state" FAKE_ADB_LOG="$RUN_DIR/fake-adb.log"
  OUT="${OUT:-$ROOT/docs/bringup/dryrun.json}"
else
  ADB="$(command -v adb || true)"
  for c in "${ANDROID_HOME:-}" "${ANDROID_SDK_ROOT:-}" "$HOME/Library/Android/sdk" "$HOME/Android/Sdk" /opt/android-sdk; do
    [[ -z "$ADB" && -n "$c" && -x "$c/platform-tools/adb" ]] && ADB="$c/platform-tools/adb"
  done
  [[ -n "$ADB" ]] || { echo "bringup: adb not found — see docs/bringup/INSTALL.md §1" >&2; exit 1; }
  RUN_DIR="$ROOT/runs/bringup/$TS"
  OUT="${OUT:-$RUN_DIR/bringup.json}"
fi
mkdir -p "$RUN_DIR"
STEPS="$RUN_DIR/steps.tsv"; : > "$STEPS"
PROV_CMD="" PULL_DEST="" PULL_OK=0 APK_SHA=""

say() { printf '\033[1m%s\033[0m\n' "$*"; }
# step ID NAME STATUS DETAIL [DATA_JSON]
step() {
  local d="${4//$'\t'/ }"; d="${d//$'\n'/ | }"
  printf '%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$d" "${5:-}" >> "$STEPS"
  printf '  %-5s %-9s %s\n' "$3" "$1" "$d"
}
adb_() { if [[ -n "$SERIAL" ]]; then "$ADB" -s "$SERIAL" "$@"; else "$ADB" "$@"; fi; }
sh_() { adb_ shell "$@" 2>&1 | tr -d '\r'; }
sha() { if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }
jstr() { python3 -I -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"; }

finish() {
  local ok=1
  grep -q $'\tfail\t' "$STEPS" && ok=0
  python3 -I - "$STEPS" "$OUT" <<PY
import json, sys
steps = []
for line in open(sys.argv[1]):
    sid, name, status, detail, data = (line.rstrip("\n").split("\t") + [""] * 5)[:5]
    s = {"id": sid, "name": name, "status": status, "detail": detail}
    if data:
        s["data"] = json.loads(data)
    steps.append(s)
doc = {
  "schema": "edith.bringup.host/v1", "dry_run": bool($DRY), "tier": "$TIER",
  "started_at": "$STARTED", "ended_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "adb": $(jstr "$( [[ $DRY -eq 1 ]] && echo docs/bringup/fake-adb || echo "$ADB")"),
  "serial": $( [[ -n "$SERIAL" ]] && jstr "$SERIAL" || echo None),
  "package": "$PKG",
  "apk": {"path": $( [[ -n "$APK" ]] && jstr "${APK#$ROOT/}" || echo None), "sha256": $( [[ -n "$APK_SHA" ]] && jstr "$APK_SHA" || echo None)},
  "steps": steps,
  "provisioning": {"peer": $( [[ -n "$PEER" ]] && jstr "$PEER" || echo None), "command": $( [[ -n "$PROV_CMD" ]] && jstr "$PROV_CMD" || echo None), "token_set": bool($( [[ -n "$TOKEN" ]] && echo 1 || echo 0))},
  "pull": {"dest": $( [[ -n "$PULL_DEST" ]] && jstr "$PULL_DEST" || echo None), "ok": bool($PULL_OK)},
  "ok": bool($ok),
}
json.dump(doc, open(sys.argv[2], "w"), indent=2)
open(sys.argv[2], "a").write("\n")
PY
  say "bringup: wrote ${OUT#$ROOT/}"
  if [[ $DRY -eq 1 ]]; then
    local py="python3"; [[ -x "$ROOT/.venv/bin/python" ]] && py="$ROOT/.venv/bin/python"
    PYTHONPATH="$ROOT/tools" EDITH_ROOT="$ROOT" "$py" -m edith_tools.commands.g glasses validate \
      --schema "$ROOT/docs/bringup/bringup.schema.json" "$OUT" || exit 1
    rm -rf "$RUN_DIR"
  fi
  [[ $ok -eq 1 ]]
}

# ---- T1: device over USB ------------------------------------------------------------------
t1() {
  say "T1  ADB (USB)"
  local list; list="$("$ADB" devices 2>&1 | tr -d '\r')"
  if [[ -z "$SERIAL" ]]; then SERIAL="$(awk 'NR>1 && $2=="device" {print $1; exit}' <<<"$list")"; fi
  if [[ -n "$SERIAL" ]] && grep -q "^$SERIAL"$'\t'"device" <<<"$list"; then
    step T1 "ADB (USB)" pass "device $SERIAL listed"
  else
    step T1 "ADB (USB)" fail "no device in 'adb devices' (unauthorized/offline?). Enable developer mode: INSTALL.md §2" \
      "{\"adb_devices\": $(jstr "$list")}"
    return 1
  fi
}

# ---- T0: identity -------------------------------------------------------------------------
t0() {
  say "T0  Identity"
  local props=(ro.build.version.release ro.build.version.sdk ro.product.manufacturer ro.product.model ro.product.board ro.product.device ro.build.fingerprint ro.serialno)
  local json="{" p v
  for p in "${props[@]}"; do v="$(sh_ getprop "$p")"; json+="$(jstr "$p"): $(jstr "$v"),"; echo "$p=$v" >> "$RUN_DIR/getprop.txt"; done
  sh_ dumpsys sensorservice > "$RUN_DIR/sensorservice.txt" || true
  local sdk; sdk="$(sh_ getprop ro.build.version.sdk)"
  json+="\"sensorservice_file\": \"sensorservice.txt\", \"sensor_lines\": $(grep -c ') ' "$RUN_DIR/sensorservice.txt" || echo 0)}"
  if [[ "$sdk" == "31" || "$sdk" == "32" ]]; then step T0 Identity pass "API $sdk confirmed (31–32 expected)" "$json"
  else step T0 Identity warn "API '$sdk' is outside 31–32: FLAG to the lead (PLAN assumption)" "$json"; fi
}

# ---- T2: adb over Wi-Fi -------------------------------------------------------------------
t2() {
  say "T2  ADB (Wi-Fi)"
  local ip="$WIFI"
  [[ -n "$ip" ]] || ip="$(sh_ ip -f inet addr show wlan0 | awk '/inet /{sub(/\/.*/,"",$2); print $2; exit}')"
  if [[ -z "$ip" ]]; then step T2 "ADB (Wi-Fi)" warn "no wlan0 IP; USB-only noted"; return 0; fi
  adb_ tcpip 5555 >/dev/null 2>&1; sleep $(( DRY ? 0 : 3 ))
  local out; out="$("$ADB" connect "$ip:5555" 2>&1 | tr -d '\r')"
  if grep -q "connected" <<<"$out"; then step T2 "ADB (Wi-Fi)" pass "adb connect $ip:5555 ok (USB serial kept for the rest)" "{\"ip\": $(jstr "$ip")}"
  else step T2 "ADB (Wi-Fi)" warn "adb connect $ip:5555 failed: $out — USB-only noted"; fi
}

# ---- T3: install (debug-key mismatch → uninstall, reinstall, re-provision; C106) ----------
install_apk() {
  say "T3  Install"
  if [[ -z "$APK" ]]; then
    for c in "$ROOT/dist/edith-selftest-rayneo-debug.apk" "$ROOT/glasses/selftest/build/outputs/apk/rayneo/debug/selftest-rayneo-debug.apk"; do
      [[ -f "$c" ]] && { APK="$c"; break; }
    done
  fi
  if [[ $DRY -eq 1 && ( -z "$APK" || ! -f "$APK" ) ]]; then
    APK="$RUN_DIR/fake.apk"; echo "fake apk for dry-run" > "$APK"
  fi
  [[ -n "$APK" && -f "$APK" ]] || { step install "Install selftest APK" fail "no APK: run ./edith glasses dist --selftest or pass --apk"; return 1; }
  APK_SHA="$(sha "$APK")"
  local out; out="$(adb_ install -r -g "$APK" 2>&1 | tr -d '\r')"
  if grep -q "INSTALL_FAILED_UPDATE_INCOMPATIBLE" <<<"$out"; then
    step install "Install selftest APK" info "INSTALL_FAILED_UPDATE_INCOMPATIBLE (debug key from another machine): uninstall + reinstall + re-provision"
    adb_ uninstall "$PKG" >/dev/null 2>&1
    out="$(adb_ install -r -g "$APK" 2>&1 | tr -d '\r')"
  fi
  if grep -q "Success" <<<"$out" && sh_ pm list packages "$PKG" | grep -q "package:$PKG"; then
    step install "Install selftest APK" pass "installed $PKG (sha256 ${APK_SHA:0:12}…), runtime permissions granted (-g)"
  else
    step install "Install selftest APK" fail "install failed: $out"; return 1
  fi
  if [[ -n "$SAMPLE_APK" ]]; then
    out="$(adb_ install -r -g "$SAMPLE_APK" 2>&1 | tr -d '\r')"
    grep -q Success <<<"$out" && step T3 Install pass "vendor sample + selftest installed; now check both in the launcher, no crash for 5 min (manual)" \
      || step T3 Install fail "vendor sample install failed: $out"
  else
    step T3 Install info "selftest installed; vendor sample not given (--sample-apk). Check: launcher icon, no crash for 5 min (manual)"
  fi
}

# ---- T4: screen mirror --------------------------------------------------------------------
t4() {
  say "T4  Screen mirror"
  if command -v scrcpy >/dev/null 2>&1; then
    step T4 "Screen mirror" info "run: scrcpy --display 0   (one eye only: scrcpy --crop 640:480:0:0); if black, set multi-pass"
  else
    step T4 "Screen mirror" info "scrcpy not installed (INSTALL.md §5). Then: scrcpy --display 0, or --crop 640:480:0:0 for one eye"
  fi
}

# ---- host-side helpers for T5 / T6 --------------------------------------------------------
host_t5_t6() {
  local size dens disp
  size="$(sh_ wm size)"; dens="$(sh_ wm density)"; disp="$(sh_ dumpsys display | grep -m3 -E 'mBaseDisplayInfo|DisplayDeviceInfo' || true)"
  step T5-host "wm size / density" info "$size; $dens" "{\"wm_size\": $(jstr "$size"), \"wm_density\": $(jstr "$dens"), \"display\": $(jstr "$disp")}"
  local nat=""
  for ns in system secure global; do nat+="$(sh_ settings list $ns | grep -iE 'natural|slide|tp_|temple' | sed "s/^/$ns./")"$'\n'; done
  step T6-host "natural-mode settings" info "$(echo "$nat" | grep -c . || true) matching settings" "{\"settings\": $(jstr "$nat")}"
}

# ---- provisioning -------------------------------------------------------------------------
provision() {
  say "Provision"
  local pj="$ROOT/runs/bringup/peer.json"
  if [[ -z "$PEER" && -f "$pj" && $DRY -eq 0 ]]; then
    PORT="$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["port"])' "$pj")"
    [[ -n "$TOKEN" ]] || TOKEN="$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["token"] or "")' "$pj")"
    [[ -n "$PEER_IP" ]] || PEER_IP="$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["ips"][0])' "$pj")"
  fi
  if [[ -z "$PEER" ]]; then
    if [[ -z "$PEER_IP" ]]; then
      if [[ $DRY -eq 1 ]]; then PEER_IP="192.0.2.10"; TOKEN="${TOKEN:-dryruntoken}"
      elif command -v ip >/dev/null; then PEER_IP="$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
      else PEER_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"; fi
    fi
    [[ -n "$PEER_IP" ]] && PEER="ws://$PEER_IP:$PORT/v1/selftest"
  fi
  local extras=()
  [[ -n "$PEER" ]] && extras+=(--es peer "$PEER")
  [[ -n "$TOKEN" ]] && extras+=(--es token "$TOKEN")
  PROV_CMD="adb shell am start -n $ACT ${extras[*]}"
  local out; out="$(sh_ am start -n "$ACT" "${extras[@]}")"
  if grep -qiE "error|exception" <<<"$out"; then step provision Provision fail "$out"; return 1; fi
  if [[ -z "$PEER" ]]; then step provision Provision warn "launched without a peer (T9 local only, T11/T13 skipped): start ./edith glasses selftest --serve"
  else step provision Provision pass "launched with peer $PEER${TOKEN:+ and token}"; fi
}

# ---- pull ---------------------------------------------------------------------------------
pull() {
  say "Pull results"
  PULL_DEST="$RUN_DIR/glasses"; mkdir -p "$PULL_DEST"
  sh_ dumpsys gfxinfo "$PKG" > "$RUN_DIR/gfxinfo.txt" || true
  local jank; jank="$(grep -m1 'Janky frames' "$RUN_DIR/gfxinfo.txt" || true)"
  local out; out="$(adb_ pull "$REMOTE_RESULTS" "$PULL_DEST" 2>&1 | tr -d '\r')"
  local n; n="$(find "$PULL_DEST" -name results.json | wc -l | tr -d ' ')"
  if [[ "$n" -gt 0 ]]; then
    PULL_OK=1
    step pull "Pull results" pass "$n results.json pulled to ${PULL_DEST#$ROOT/}; gfxinfo: ${jank:-n/a}" "{\"gfxinfo_janky\": $(jstr "$jank")}"
    local py="python3"; [[ -x "$ROOT/.venv/bin/python" ]] && py="$ROOT/.venv/bin/python"
    find "$PULL_DEST" -name results.json -print0 | xargs -0 env PYTHONPATH="$ROOT/tools" EDITH_ROOT="$ROOT" \
      "$py" -m edith_tools.commands.g glasses validate --schema "$ROOT/docs/bringup/results.schema.json" || true
  else
    step pull "Pull results" fail "nothing pulled from $REMOTE_RESULTS: $out"
  fi
}

say "E.D.I.T.H. bring-up — tier $TIER$( [[ $DRY -eq 1 ]] && echo ' (DRY RUN, fake adb)')"
case "$MODE" in
  pull) t1 && pull; finish; exit $? ;;
  install) t1 && install_apk && provision; finish; exit $? ;;
esac
t1 || { finish; exit 1; }
t0
if [[ "$TIER" == "all" || -n "$WIFI" ]]; then t2; fi
install_apk || { finish; exit 1; }
t4
host_t5_t6
provision
if [[ $DRY -eq 1 ]]; then pull; else
  say "Next: run the tests on the glasses (TAP = next, 2×TAP = back), then: tools/bringup.sh --pull-only"
fi
finish
