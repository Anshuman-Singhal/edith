"""Pydantic v2 models for every type in interfaces §2–§4 (hand-written, contract-tested against
`schemas/v1/` on shared fixtures, C27).

Conventions
- Field order follows the spec; `model_dump_json()` emits keys in that order (canonical).
- Optional (`?`) fields default to None and are *omitted* from dumps when None. Required
  nullable fields (`conf: float|null`, `Execution.proposal_id`) are always emitted.
- Unknown keys are ignored (additive minor changes, interfaces §1 "Versioning").
- Parse wire JSON with `Model.model_validate_json(raw, strict=True)` (what `envelope.parse`
  does) so types match the schema exactly; Python construction stays lax (numpy floats etc.).
- Schema-only rule: an optional field sent as explicit `null` is rejected by the schema but
  accepted (and then omitted) by the models.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    field_validator,
    model_serializer,
    model_validator,
)

# ---------------------------------------------------------------- primitives
Id = Annotated[str, Field(min_length=1, max_length=128)]
Str1 = Annotated[str, Field(min_length=1)]
TsMs = Annotated[int, Field(ge=0)]
DurMs = Annotated[int, Field(ge=0)]
NonNegInt = Annotated[int, Field(ge=0)]
PosInt = Annotated[int, Field(ge=1)]
NonNeg = Annotated[float, Field(ge=0)]
Lat = Annotated[float, Field(ge=-90, le=90)]
Lon = Annotated[float, Field(ge=-180, le=180)]
Deg360 = Annotated[float, Field(ge=0, lt=360)]
Conf = Annotated[float, Field(ge=0, le=1)]
Pct = Annotated[float, Field(ge=0, le=100)]
CeM = Annotated[float, Field(ge=0)]
Unit = Annotated[float, Field(ge=0, le=1)]
BboxNorm = Annotated[list[Unit], Field(min_length=4, max_length=4)]
Chip = Annotated[str, Field(pattern=r"^D[1-9]$")]
Mgrs = Annotated[str, Field(pattern=r"^[0-9]{1,2}[C-HJ-NP-X][A-HJ-NP-Z]{2}([0-9]{2}){0,5}$")]
AlertLabel = Annotated[str, Field(
    pattern=r"^(PERSON|VEHICLE|GEOFENCE|TEAMMATE|TAK LINK|D[1-9] (LINK|BATT|TASK)|[1-9][0-9]? NEW)$")]

Cls = Literal["person", "vehicle", "other"]
Tier = Literal["advisory", "caution", "warning"]
LinkState = Literal["ok", "degraded", "lost"]
Affiliation = Literal["unknown", "friend", "neutral", "hostile"]
Verb = Literal["takeoff", "goto", "orbit", "observe", "search", "follow", "hold", "rtl", "land"]
ConfirmWith = Literal["voice", "touch_temple", "touch_companion"]
AlertAction = Literal["watch", "mark", "dismiss", "say_again", "details"]
InputKind = Literal["tap", "double_tap", "triple_tap", "slide_fwd", "slide_back", "slide_up",
                    "slide_down", "ptt_down", "ptt_up", "two_finger_hold", "back",
                    "bt_ptt_down", "bt_ptt_up"]
VoiceTrigger = Literal["ptt", "bt_ptt", "touch", "text"]


class Model(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        protected_namespaces=(),
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )
    _omit: ClassVar[frozenset[str]] = frozenset()

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        cls._omit = frozenset(
            (f.serialization_alias or f.alias or name)
            for name, f in cls.model_fields.items()
            if not f.is_required() and f.default is None
        )

    @model_serializer(mode="wrap")
    def _omit_absent_optionals(self, handler):
        data = handler(self)
        if isinstance(data, dict):
            for k in self._omit:
                if k in data and data[k] is None:
                    del data[k]
        return data


# ---------------------------------------------------------------- shared
class LatLon(Model):
    lat: Lat
    lon: Lon


class Pos(Model):
    lat: Lat
    lon: Lon
    alt_msl_m: float
    alt_agl_m: float


class Att(Model):
    roll_deg: float
    pitch_deg: float
    yaw_deg: float


# ---------------------------------------------------------------- §2 envelope + binary header
class Envelope(Model):
    v: Literal[1] = 1
    type: Annotated[str, Field(pattern=r"^[a-z]+(\.[a-z_]+)+$")]
    id: Annotated[str, Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")]
    ts_ms: TsMs
    src: Id
    seq: NonNegInt
    body: Any

    @field_validator("body")
    @classmethod
    def _body_is_object(cls, v: Any) -> Any:
        if not isinstance(v, dict | BaseModel):
            raise ValueError("body must be an object")
        return v


class BinaryHeader(Model):
    stream: Annotated[str, Field(pattern=(
        r"^(audio\.up|audio\.down|video\.up|video\.down/[A-Za-z0-9_.:-]+"
        r"|video\.crop/[A-Za-z0-9_.:-]+)$"))]
    seq: NonNegInt
    ts_ms: TsMs
    codec: Literal["pcm_s16le", "jpeg", "h264"]
    w: PosInt | None = None
    h: PosInt | None = None
    sr: PosInt | None = None
    ch: PosInt | None = None
    frame_id: NonNegInt | None = None
    preroll: bool | None = None


# ---------------------------------------------------------------- §3 messages
class HelloDevice(Model):
    model: str
    fingerprint: str
    sdk_int: NonNegInt


class HelloDisplay(Model):
    win_w: PosInt
    win_h: PosInt
    eye_w: PosInt
    eye_h: PosInt
    eyes: Literal["sbs", "mono"]


class HelloInput(Model):
    ptt: Literal["hold", "toggle", "bt_key"]
    temple_confirm: bool


class HelloCaps(Model):
    inference: list[str]
    camera: bool
    tts: bool


class SysHello(Model):
    role: Literal["glasses", "emulator", "fake", "companion"]
    proto: Annotated[list[PosInt], Field(min_length=1)]
    token: str | None = None
    device: HelloDevice | None = None
    display: HelloDisplay | None = None
    input: HelloInput | None = None
    caps: HelloCaps | None = None

    @model_validator(mode="after")
    def _client_fields(self):
        if self.role != "companion":
            missing = [k for k in ("token", "device", "display", "input", "caps")
                       if getattr(self, k) is None]
            if missing:
                raise ValueError(f"role {self.role} requires {missing}")
        return self


class SysPing(Model):
    t0_ms: NonNegInt
    t1_ms: NonNegInt | None = None
    t2_ms: NonNegInt | None = None


class SysPong(Model):
    t0_ms: NonNegInt
    t1_ms: NonNegInt
    t2_ms: NonNegInt


class HeadPose(Model):
    yaw_deg: float
    pitch_deg: float
    roll_deg: float
    heading_deg: Deg360
    heading_unc_deg: NonNeg
    source: Literal["rv", "fused", "game_rv", "scripted"]


class InputCtx(Model):
    proposal_id: Id | None = None
    alert_id: Id | None = None


class InputEvent(Model):
    kind: InputKind
    gesture_seq: NonNegInt
    pointer_count: NonNegInt
    held_ms: DurMs | None = None
    duration_ms: DurMs | None = None
    ctx: InputCtx | None = None

    @model_validator(mode="after")
    def _press_fields(self):
        if self.kind in ("ptt_down", "bt_ptt_down") and (self.held_ms is None or self.ctx is None):
            raise ValueError(f"{self.kind} requires held_ms and ctx (C101)")
        if self.kind == "two_finger_hold" and (self.duration_ms is None or self.ctx is None):
            raise ValueError("two_finger_hold requires duration_ms and ctx (C101)")
        return self


class VoiceSessionStart(Model):
    session_id: Id
    trigger: VoiceTrigger
    reason: str | None = None


class VoiceSessionStop(VoiceSessionStart):
    pass


class VoiceText(Model):
    session_id: Id
    text: str


class VoicePartial(Model):
    session_id: Id
    text: str
    conf: Conf | None


class VoiceFinal(VoicePartial):
    pass


class HudEvent(Model):
    kind: Literal["inset_open", "inset_close", "alert_shown", "alert_cleared", "card_shown",
                  "card_cleared"]
    ref: Id
    ts_ms: TsMs


class GlassesTelemetry(Model):
    battery_pct: Pct
    current_ua: int
    voltage_mv: NonNegInt
    temp_c: float
    thermal_status: NonNegInt
    thermal_headroom: float | None
    fps: NonNeg
    decode_ms_p95: NonNeg
    rtt_ms: NonNeg
    usb_connected: bool


# ---------------------------------------------------------------- §4 core
class AssetLink(Model):
    state: LinkState
    last_heard_ms: TsMs


class VelNed(Model):
    n_mps: float
    e_mps: float
    d_mps: float


class Failsafe(Model):
    dll_action: Literal["hold", "return", "land", "none"]
    dll_countdown_s: NonNeg | None = None


class AssetTask(Model):
    proposal_id: Id | None = None
    steps: list[Verb] | None = None
    step_idx: NonNegInt | None = None
    status: Str1 | None = None


class Sensor(Model):
    sensor_id: Id
    kind: Literal["eo", "ir"]
    hfov_deg: Annotated[float, Field(gt=0, le=180)]
    w: PosInt
    h: PosInt
    stream: Str1


class AssetState(Model):
    asset_id: Id
    callsign: Str1
    chip: Chip
    kind: Literal["quad", "fixed_wing", "vtol", "ugs"]
    link: AssetLink
    pos: Pos
    att: Att
    vel_ned: VelNed
    battery_pct: Pct
    mode: Str1
    armed: bool
    landed: bool
    failsafe: Failsafe
    task: AssetTask
    sensors: list[Sensor]


class PoseEst(Model):
    lat: Lat
    lon: Lon
    alt_msl_m: float
    alt_agl_m: float
    roll_deg: float
    pitch_deg: float
    yaw_deg: float


class Gimbal(Model):
    mode: Literal["stabilized", "body_fixed"]
    pitch_deg: float
    yaw_deg: float


class Intrinsics(Model):
    fx: Annotated[float, Field(gt=0)]
    fy: Annotated[float, Field(gt=0)]
    cx: float
    cy: float


class FrameMeta(Model):
    frame_id: NonNegInt
    t_capture_ms: TsMs
    t_sim_ms: NonNegInt
    asset_id: Id
    pose_est: PoseEst
    rel_alt_m: float
    gimbal: Gimbal
    K: Intrinsics
    w: PosInt
    h: PosInt
    pose_source: Literal["sidecar", "telemetry_interp"]
    video: Literal["on", "off"]


class TruthObject(Model):
    entity_id: Id
    cls: Str1
    bbox_norm: BboxNorm
    visible_frac: Unit
    range_m: NonNeg
    lat: Lat
    lon: Lon


class FrameTruth(Model):
    """Sim-internal; never sent to the companion."""

    frame_id: NonNegInt
    t_sim_ms: NonNegInt
    asset_id: Id
    objects: list[TruthObject]


class DetSource(Model):
    asset_id: Id
    sensor_id: Id


class Infer(Model):
    placement: Literal["companion", "glasses", "offload"]
    model: Str1
    model_sha: str
    t_capture_ms: TsMs
    t_start_ms: TsMs
    t_end_ms: TsMs


class Detection(Model):
    det_id: Id
    frame_id: NonNegInt
    frame_ts_ms: TsMs
    source: DetSource
    cls: Cls
    conf: Conf
    bbox_norm: BboxNorm
    tile: NonNegInt | None = None
    det_px_h: NonNeg
    infer: Infer


class TrackGeo(Model):
    lat: Lat
    lon: Lon
    ce_m: CeM


class VelEN(Model):
    e_mps: float
    n_mps: float


class Track(Model):
    track_id: Id
    alias: Str1
    cls: Cls
    conf: Conf
    hits: NonNegInt
    window: PosInt
    geo: TrackGeo
    vel: VelEN
    geo_quality: Literal["metric", "pseudo"]
    first_seen_ms: TsMs
    last_seen_ms: TsMs
    source_assets: list[Id]
    status: Literal["new", "confirmed", "watched", "marked", "dismissed", "lost"]
    novelty: float
    affiliation: Affiliation
    affiliation_src: Literal["machine", "human"]
    assoc_friend_uid: Str1 | None = None
    cot_uid: Str1
    det_ids: Annotated[list[Id], Field(max_length=8)]

    @model_validator(mode="after")
    def _machine_is_unknown(self):
        if self.affiliation_src == "machine" and self.affiliation != "unknown":
            raise ValueError("machine affiliation must be unknown (I6)")
        return self


class AlertRef(Model):
    track_id: Id | None = None
    asset_id: Id | None = None
    uid: Id | None = None

    @model_validator(mode="after")
    def _exactly_one(self):
        if sum(x is not None for x in (self.track_id, self.asset_id, self.uid)) != 1:
            raise ValueError("ref needs exactly one of track_id, asset_id, uid")
        return self


class AlertSignals(Model):
    conf: float
    novelty: float
    proximity: float
    closing: float
    recency: float
    class_w: float
    aoi: float


def _warning_not_gesture(tier: str, gesture_dismiss: bool) -> None:
    if tier == "warning" and gesture_dismiss:
        raise ValueError("gesture_dismiss must be false on WARNING")


class Alert(Model):
    alert_id: Id
    tier: Tier
    score: float
    kind: Literal["new_contact", "contact_close", "link_lost", "battery_low", "geofence",
                  "teammate_stale", "task_status", "tak_link"]
    label: AlertLabel
    ref: AlertRef
    bearing_deg: Deg360 | None
    range_m: NonNeg | None
    ce_m: CeM | None = None
    row2: str
    actions: list[AlertAction]
    gesture_dismiss: bool
    signals: AlertSignals
    created_ms: TsMs
    expires_ms: TsMs

    @field_validator("actions")
    @classmethod
    def _unique(cls, v):
        if len(set(v)) != len(v):
            raise ValueError("actions must be unique")
        return v

    @model_validator(mode="after")
    def _tier_rule(self):
        _warning_not_gesture(self.tier, self.gesture_dismiss)
        return self


class Offset(Model):
    dir: Str1
    dist_m: NonNeg


class Target(Model):
    kind: Literal["self", "teammate", "clock_range", "grid", "named", "relative", "track", "area"]
    uid: Str1 | None = None
    clock: Annotated[int, Field(ge=1, le=12)] | None = None
    range_m: NonNeg | None = None
    mgrs: Str1 | None = None
    name: Str1 | None = None
    track_alias: Str1 | None = None
    offset: Offset | None = None
    size_m: NonNeg | None = None


class Params(Model):
    alt_agl_m: NonNeg | None = None
    radius_m: NonNeg | None = None
    standoff_m: NonNeg | None = None


class Utterance(Model):
    text: str
    asr_conf: Conf | None
    nbest: list[str]
    engine: Str1
    model_sha: str
    norm_profile: Literal["spoken", "written"]


class Parsed(Model):
    kind: Literal["command", "safety_stop", "response", "query", "hud"]
    verb: Str1 | None = None
    asset_ref: Str1 | None = None
    stop_via: Literal["grammar", "spotting"] | None = None
    target: Target | None = None
    params: Params


class Slot(Model):
    name: Str1
    raw_tokens: list[str]
    value: Any
    conf: Conf


class ParserInfo(Model):
    method: Literal["grammar", "llm"]
    conf: Conf


class CommandIntent(Model):
    intent_id: Id
    session_id: Id
    utterance: Utterance
    heading_snapshot_deg: Deg360
    operator_pos: LatLon
    parsed: Parsed
    slots: list[Slot]
    parser: ParserInfo
    result: Literal["ok", "say_again", "rejected"]
    reject_reason: Str1 | None = None


class Step(Model):
    verb: Verb
    params: dict[str, Any]


class ResolvedTarget(Model):
    lat: Lat
    lon: Lon
    alt_agl_m: float
    mgrs: Mgrs
    label: Str1
    frozen_from_track: Id | None = None


class Readback(Model):
    rows: Annotated[list[str], Field(min_length=2, max_length=2)]
    spoken: Str1


class Check(Model):
    name: Str1
    pass_: bool = Field(alias="pass")
    msg: str


class CommandProposal(Model):
    proposal_id: Id
    intent_id: Id
    asset_id: Id
    steps: Annotated[list[Step], Field(min_length=1)]
    resolved_target: ResolvedTarget
    readback: Readback
    checks: list[Check]
    confirm_with: Annotated[list[ConfirmWith], Field(min_length=1)]
    nonce: Str1
    created_ms: TsMs
    lockout_until_ms: TsMs
    expires_ms: TsMs
    card_shown_ms: TsMs | None = None
    state: Literal["proposed", "await_confirm", "confirmed", "dispatched", "cancelled",
                   "expired", "superseded", "invalidated"]

    @field_validator("confirm_with")
    @classmethod
    def _unique(cls, v):
        if len(set(v)) != len(v):
            raise ValueError("confirm_with must be unique")
        return v


class Press(Model):
    ptt_down_recv_ms: TsMs
    held_ms: DurMs
    est_start_ms: TsMs


class ConfirmAsr(Model):
    text_norm: str
    conf: Conf | None
    closed_grammar: str | None


class Confirmation(Model):
    proposal_id: Id
    nonce: Str1
    method: Str1
    operator_id: Id
    ts_ms: TsMs
    press: Press | None = None
    asr: ConfirmAsr | None = None
    duration_ms: DurMs | None = None


class NotSent(Model):
    asset_id: Id
    reason: Literal["link_lost"]


class SafetyStop(Model):
    stop_id: Id
    scope: Id
    source: Literal["voice", "voice_spotting", "temple", "bt", "companion"]
    ts_ms: TsMs
    asset_ids: list[Id]
    not_sent: list[NotSent]
    cancelled_tasks: list[Id]


class Execution(Model):
    exec_id: Id
    proposal_id: Id | None
    stop_id: Id | None = None
    asset_id: Id
    step_idx: NonNegInt
    verb: Literal[Verb, "arm"]
    status: Literal["sent", "accepted", "rejected", "in_progress", "completed", "failed",
                    "aborted"]
    mav_result: NonNegInt | None = None
    detail: str
    ts_ms: TsMs

    @model_validator(mode="after")
    def _stop_needs_id(self):
        if self.proposal_id is None and self.stop_id is None:
            raise ValueError("proposal_id null (safety stop) requires stop_id")
        return self


class Feedback(Model):
    track_id: Id
    verb: Literal["watch", "mark", "dismiss", "undo_dismiss", "say_again", "details",
                  "reclassify"]
    affiliation: Affiliation | None = None
    operator_id: Id
    method: Str1
    alert_id: Id
    ts_ms: TsMs

    @model_validator(mode="after")
    def _reclassify_needs_affiliation(self):
        if self.verb == "reclassify" and self.affiliation is None:
            raise ValueError("reclassify requires affiliation")
        return self


class TeammatePos(Model):
    lat: Lat
    lon: Lon
    hae_m: float


class TeammatePosition(Model):
    uid: Id
    callsign: Str1
    team: str
    role: str
    pos: TeammatePos
    course_deg: Deg360
    speed_mps: NonNeg
    ts_ms: TsMs
    stale_ms: TsMs
    source: Literal["mesh", "server", "sim"]


# ---------------------------------------------------------------- HudState
class HudOperator(Model):
    lat: Lat
    lon: Lon
    heading_deg: Deg360
    heading_unc_deg: NonNeg


class HudStatus(Model):
    tak: Literal["ok", "degraded", "lost", "off"]
    gps: Literal["ok", "sim", "none"]
    companion_battery_pct: Pct | None
    data_age_ms: DurMs
    rec: bool


class HudAsset(Model):
    asset_id: Id
    chip: Chip
    mode_label: str
    battery_pct: Pct
    link: LinkState
    task_label: str
    dll_countdown_s: NonNeg | None = None


class HudEntity(Model):
    ref: Id
    kind: Literal["self", "friend", "own_drone", "unknown", "hostile", "point"]
    marked: bool
    rel_e_m: float
    rel_n_m: float
    heading_deg: Deg360 | None = None
    label: str | None = None
    age_ms: DurMs
    stale: bool


class HudCluster(Model):
    rel_e_m: float
    rel_n_m: float
    count: Annotated[int, Field(ge=2)]


class HudMinimap(Model):
    range_m: Annotated[float, Field(gt=0)]
    entities: list[HudEntity]
    clusters: list[HudCluster]


class HudCaret(Model):
    ref: Id
    bearing_deg: Deg360
    style: Literal["friend", "own_drone", "unknown", "warning", "point"]


class HudTape(Model):
    carets: list[HudCaret]


class HudAlertQueue(Model):
    count: NonNegInt
    warning: NonNegInt
    caution: NonNegInt
    advisory: NonNegInt


class HudAlert(Model):
    alert_id: Id
    tier: Tier
    label: AlertLabel
    bearing_deg: Deg360 | None
    range_m: NonNeg | None
    ce_m: CeM | None
    row2: str
    row3: str
    gesture_dismiss: bool
    shown_since_ms: TsMs
    flash_until_ms: TsMs
    queue: HudAlertQueue

    @model_validator(mode="after")
    def _tier_rule(self):
        _warning_not_gesture(self.tier, self.gesture_dismiss)
        return self


class HudProposal(Model):
    proposal_id: Id
    rows: Annotated[list[str], Field(min_length=2, max_length=2)]
    expires_in_ms: int
    lockout_in_ms: int
    confirm_with: list[ConfirmWith]
    state: Literal["await_confirm", "lockout", "sent", "acked", "no_ack", "not_sent_timeout",
                   "cancelled"]


class HudToast(Model):
    text: Str1
    tier: Tier
    until_in_ms: int


class HudUndo(Model):
    alert_id: Id
    until_in_ms: int


class HudBox(Model):
    alias: str
    cls: Cls
    bbox_norm: BboxNorm


class HudInset(Model):
    stream: Str1
    label: str
    frame_age_ms: DurMs
    pinned: bool
    boxes: list[HudBox]
    crop_stream: Str1 | None = None


class HudVoice(Model):
    state: Literal["idle", "listening", "processing", "await_confirm", "say_again", "muted",
                   "offline"]
    partial: str | None = None
    last_heard: str | None = None


class HudState(Model):
    seq: NonNegInt
    ts_ms: TsMs
    mode: Literal["day", "night"]
    declutter: Literal["full", "min", "warn"]
    quiet: bool
    operator: HudOperator
    status: HudStatus
    assets: list[HudAsset]
    minimap: HudMinimap
    tape: HudTape
    alert: HudAlert | None = None
    proposal: HudProposal | None = None
    toast: HudToast | None = None
    undo: HudUndo | None = None
    inset: HudInset | None = None
    voice: HudVoice


class PerceptionDetections(Model):
    detections: list[Detection]


class DetectionList(RootModel[list[Detection]]):
    """UDP 5800+i payload: a bare JSON array of Detection."""


# ---------------------------------------------------------------- registries
MESSAGE_MODELS: dict[str, type[BaseModel]] = {
    "sys.hello": SysHello,
    "sys.ping": SysPing,
    "sys.pong": SysPong,
    "head.pose": HeadPose,
    "input.event": InputEvent,
    "voice.session.start": VoiceSessionStart,
    "voice.session.stop": VoiceSessionStop,
    "voice.text": VoiceText,
    "voice.partial": VoicePartial,
    "voice.final": VoiceFinal,
    "hud.state": HudState,
    "hud.event": HudEvent,
    "glasses.telemetry": GlassesTelemetry,
    "perception.detections": PerceptionDetections,
}
CORE_MODELS: dict[str, type[BaseModel]] = {
    m.__name__: m
    for m in (AssetState, FrameMeta, FrameTruth, Detection, Track, Alert, CommandIntent,
              CommandProposal, Confirmation, SafetyStop, Execution, Feedback, TeammatePosition,
              HudState)
}
MODELS: dict[str, type[BaseModel]] = {
    "envelope": Envelope,
    "binary_header": BinaryHeader,
    **MESSAGE_MODELS,
    **CORE_MODELS,
    "udp.detections": DetectionList,
}


def model_for(type_: str) -> type[BaseModel]:
    try:
        return MODELS[type_]
    except KeyError:
        raise KeyError(f"no model for type {type_!r}") from None
