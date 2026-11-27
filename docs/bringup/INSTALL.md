# Installing the selftest APK on the RayNeo X3 Pro (no Android experience needed)

Owner: WS-G. Read this once before session 1. You need: the glasses, their USB-C cable, a laptop
on the **same Wi-Fi** as the glasses, and the two files you were handed:
`edith-selftest-rayneo-debug.apk` and `SHA256SUMS`. You do **not** need Android Studio or Gradle.

Anything about the device marked UNVERIFIED is a guess until we have the glasses; the selftest
exists to find out. If a step does not match what you see, write down what you see.

## 1. Install adb (the Android command-line tool)

`adb` talks to Android devices over USB or Wi-Fi.

| OS | Install | Check |
|---|---|---|
| **macOS** | `brew install --cask android-platform-tools` (install Homebrew first from brew.sh) | `adb version` |
| **Windows** | Download "SDK Platform-Tools for Windows" from developer.android.com/tools/releases/platform-tools, unzip to `C:\platform-tools`, then in PowerShell: `setx PATH "$env:PATH;C:\platform-tools"` and open a new terminal | `adb version` |
| **Linux** | Debian/Ubuntu: `sudo apt install adb`; Fedora: `sudo dnf install android-tools` | `adb version` |

Windows users: run `tools/bringup.sh` from **Git Bash** or **WSL**; every step below also works as a
plain `adb` command in PowerShell.

## 2. Turn on developer mode on the glasses (T1)

On the glasses: **Settings → General → About Device**, then **swipe left on the temple 10 times**
(the glasses' version of "tap Build number 7 times"; UNVERIFIED for this firmware). Enable
**App Lab** / USB debugging if offered. Plug in USB-C, then on the laptop:

```bash
adb devices
```

You should see one line ending in `device`. If it says `unauthorized`, look at the glasses and
accept the "Allow USB debugging?" prompt. If nothing appears, try another cable (some are
charge-only) and run `adb kill-server && adb devices`.

## 3. Check the APK is the one we built (SHA256SUMS)

Put both files in one folder, open a terminal there, and run:

| OS | Command | Expected |
|---|---|---|
| macOS | `shasum -a 256 -c SHA256SUMS` | `edith-selftest-rayneo-debug.apk: OK` |
| Linux | `sha256sum -c SHA256SUMS` | `edith-selftest-rayneo-debug.apk: OK` |
| Windows (PowerShell) | `(Get-FileHash edith-selftest-rayneo-debug.apk -Algorithm SHA256).Hash.ToLower()` | the same 64 characters as the first word in `SHA256SUMS` (`Get-Content SHA256SUMS`) |

If it does not match, do not install it; ask for the files again.

## 4. Start the laptop peer, install, provision

The peer is a small server on your laptop that the glasses stream mic audio (T9) and video frames
(T13) to. From the repo root (`git clone`, then `uv sync` once):

```bash
./edith glasses selftest --serve          # leave this running; Ctrl-C to stop
```

It prints the laptop IP, port 7400, a random token and the exact provisioning command. Do not run
the companion at the same time. Allow incoming connections if your firewall asks. Then, in a
second terminal:

```bash
tools/bringup.sh --tier g0 --apk path/to/edith-selftest-rayneo-debug.apk
```

This runs T0–T1 (identity, USB), installs with `adb install -r -g` (`-g` grants mic and camera),
handles the "signatures do not match" error (an APK built on another laptop) by uninstalling and
reinstalling, prints the T4 scrcpy hint, records `wm size`, and starts the app with the peer
address and token. Use `--tier all` to add T2 (adb over Wi-Fi).

Without the repo, the same by hand:

```bash
adb install -r -g edith-selftest-rayneo-debug.apk
# if that prints INSTALL_FAILED_UPDATE_INCOMPATIBLE:
adb uninstall edith.selftest && adb install -r -g edith-selftest-rayneo-debug.apk
adb shell am start -n edith.selftest/.SelfTestActivity \
    --es peer ws://<laptop-ip>:7400/v1/selftest --es token <token-printed-by-the-peer>
```

## 5. Run the tests on the glasses

The app shows its screens in both eyes: **TAP = start / next, DOUBLE-TAP = back, SLIDE forward =
skip, SLIDE back = previous**. Inside T5/T6/T7 gestures are test input; each screen says what to
do. If the temple does not respond (possible on the first day), drive it from the laptop:

```bash
adb shell input keyevent ENTER        # = tap
adb shell input keyevent DEL          # = double-tap (back)
adb shell input keyevent DPAD_RIGHT   # = slide forward (skip)
adb shell am start -n edith.selftest/.SelfTestActivity --es goto T13 --ez start true
```

Order for session 1 (g0): T5 binocular → T6 touch → T7 PTT → T9 mic → T13 inset → T14 battery.
Follow [CHECKLIST.md](CHECKLIST.md) and tick boxes as you go. Mirror the screen with
`scrcpy --display 0` (one eye: `scrcpy --crop 640:480:0:0`); install scrcpy with
`brew install scrcpy`, `sudo apt install scrcpy` or from github.com/Genymobile/scrcpy.

## 6. Get the results

```bash
tools/bringup.sh --pull-only
```

| What | Where (laptop) |
|---|---|
| Host-side T0–T4 record | `runs/bringup/<ts>/bringup.json` (+ `getprop.txt`, `sensorservice.txt`, `gfxinfo.txt`) |
| APK results (T5–T14) | `runs/bringup/<ts>/glasses/results/<run_id>/results.json`, plus `t6_raw.jsonl`, `t7_raw.jsonl`, `battery.jsonl`, `t9/*.wav` |
| Peer files (T9 WAVs, T11, T13 per-frame RTT) | `runs/bringup/<peer-ts>/` (`t9_*.wav`, `t9.jsonl`, `t11.jsonl`, `t13.jsonl`, `peer.log`) |

On the glasses the results live in `/sdcard/Android/data/edith.selftest/files/results/`.
`results.json` follows [`results.schema.json`](results.schema.json); `bringup.sh` validates it
after pulling. Send the whole `runs/bringup/` folder to Arjun (WS-G owner).
