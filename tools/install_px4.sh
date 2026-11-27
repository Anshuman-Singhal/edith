#!/usr/bin/env bash
# tools/install_px4.sh — install PX4 v1.18 SIH (Tier A, D15). WS-D.
#
#   *** APPROVAL-GATED (PLAN L14, D15) ***
#   Never run by CI or by an agent. Run only on a team laptop after the user explicitly
#   approves installing PX4. Requires sudo for `apt-get install ./px4*.deb`.
#
# Pins (PLAN §4.2): 1.18.0~rc2 .deb, sha256-verified; switch to the final 1.18 release if it is
# out by Dec 12. PX4_DEB_SHA256 below MUST be filled in from the release page's asset digest
# (it was not reachable from the build sandbox, 2026-11-26) — the script refuses to install
# while it is empty or on any mismatch.
set -euo pipefail

PX4_VERSION="${PX4_VERSION:-1.18.0-rc2}"
PX4_DEB_URL="${PX4_DEB_URL:-https://github.com/PX4/PX4-Autopilot/releases/download/v${PX4_VERSION}/px4_sih_${PX4_VERSION}_amd64.deb}"  # asset name UNVERIFIED
PX4_DEB_SHA256="${PX4_DEB_SHA256:-}"   # TODO(D15): pin the 64-hex digest here

DEST="${DEST:-dist/px4}"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

if [[ "${EDITH_PX4_APPROVED:-}" != "yes" ]]; then
  echo "install_px4.sh: PX4 install is approval-gated (L14). Re-run with EDITH_PX4_APPROVED=yes" >&2
  echo "after the user has approved it, on a team laptop." >&2
  exit 3
fi
if [[ ! "$PX4_DEB_SHA256" =~ ^[0-9a-f]{64}$ ]]; then
  echo "install_px4.sh: PX4_DEB_SHA256 is not pinned; refusing to install an unverified .deb" >&2
  exit 4
fi

mkdir -p "$DEST"
deb="$DEST/$(basename "$PX4_DEB_URL")"
if [[ $DRY_RUN == 1 ]]; then
  echo "would download $PX4_DEB_URL -> $deb, verify sha256 $PX4_DEB_SHA256, apt-get install it"
  exit 0
fi
[[ -f "$deb" ]] || curl -fL --retry 3 -o "$deb" "$PX4_DEB_URL"
echo "$PX4_DEB_SHA256  $deb" | sha256sum -c -
sudo apt-get install -y "./$deb"
echo "PX4 ${PX4_VERSION} installed. Next: ./edith sim record-px4 (applies sim/profiles/quad_sim.yaml after boot, reads back)."
