#!/usr/bin/env python3
"""Split an engine-based motion HTML into small editable parts, and assemble them back.

Editing a 600-line HTML with exact-match string edits is slow and error-prone, so the work happens in parts:

  assemble.py split <engine-or-built.html> <parts-dir>   # write parts/*.{html,js} + parts/_shell.html
  assemble.py build <parts-dir> <out.html>               # splice parts back into the shell, syntax-check the script

Parts (each is the text between `@@name` and `@@/name` markers in the shell):
  head.html     <title>, description, og/twitter meta, theme-color
  config.js     const CFG = {...}
  copy.js       I18N.<lang> = {...} blocks (delete a language's block for single-language output)
  style.js      the film's frame: drawBg(t), overlay(t), hud(t, sc), transition(sc, lt) — rewritten per topic
  geometry.js   shared precomputed shapes (TITLE, TRACES, ...) used by scenes
  scenes.js     S.<id> = { draw(lt, d), cues(d) } for every scene
  plan.js       const PLAN = [[id, beats, code], ...]
  ready.js      calls that must run after web fonts load (e.g. buildDots())

`split` on the pristine engine starts a new piece: `split "$SKILL_DIR/assets/engine.html" parts`.
`split` on a finished HTML resumes editing it later. The shell keeps everything else (player, audio, helpers) untouched.
"""
import pathlib
import argparse
import hashlib
import html
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal

PARTS = {"head": "html", "config": "js", "copy": "js", "style": "js", "geometry": "js", "scenes": "js", "plan": "js", "ready": "js"}

DESIGN_ROOT = pathlib.Path("/Users/dongchanyoon/Documents/Work/Projects/15.design_base")
SKILL_ROOT = pathlib.Path(__file__).resolve().parent.parent
# These are renderer capabilities, not copies of the catalogue's prompts.
TEMPLATES = {
    "text-built-route": ("typography", "route"),
    "risograph-information-poster": ("typography", "poster"),
    "quiet-intro-mask": ("typography", "mask"),
    "workflow-shape-ribbon": ("flow", "ribbon"),
    "data-to-decision-path": ("flow", "decision"),
    "recursive-card-explainer": ("flow", "recursive"),
    "milestone-map": ("flow", "milestone"),
    "paper-evidence-notes": ("flow", "notes"),
    "handdrawn-concept-build": ("flow", "drawing"),
    "quantity-stack": ("data", "stack"),
    "signal-to-label": ("data", "signal"),
}
FIELDS = {
    "route": ["title", "phrases (exactly three)", "verb"],
    "poster": ["title", "facts (label/detail/source)"],
    "mask": ["title", "phrases", "line_art (owned point pairs)"],
    "ribbon": ["title", "steps (label/detail: transition condition)"],
    "decision": ["title", "steps (label/detail)", "input_source", "verification_step"],
    "recursive": ["title", "levels (label/detail)", "stop_condition"],
    "milestone": ["title", "events (label/date/source)"],
    "notes": ["title", "product", "verified_result", "notes (label/detail/source)"],
    "drawing": ["title", "drawings (label/points)", "relations (from/to/label)"],
    "stack": ["title", "numbers (label/value/unit/source; same unit)"],
    "signal": ["title", "signal_data", "meaning_labels", "signal_source", "signal_kind (observed/synthetic)"],
}


def fail(message):
    raise ValueError(message)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        fail(f"Cannot read JSON {path}: {error}")


def js_json(value):
    # JSON is embedded inside an HTML script, where </script> ends JS even in a string.
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def catalogue(root):
    path = root / "catalogs/prompt-motion/catalog.json"
    items = read_json(path)
    if not isinstance(items, list) or not items:
        fail("Malformed catalogue: expected nonempty recipe array")
    ids = []
    for item in items:
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k] for k in ("slug", "name_ko", "category", "prompt_ko")) or not isinstance(item.get("inputs"), list) or not item["inputs"] or any(not isinstance(x, str) or not x.strip() for x in item["inputs"]):
            fail("Malformed catalogue: recipe fields missing")
        ids.append(item["slug"])
    if len(set(ids)) != len(ids):
        fail("Malformed catalogue: duplicate recipe slug")
    return items, path


def theme_tokens(root, theme):
    if not re.fullmatch(r"[a-z][a-z0-9-]*", theme):
        fail("Invalid theme name")
    path = root / "tokens/builds" / (theme + ".tokens.json")
    raw = read_json(path)
    tokens = raw.get("tokens", {}) if isinstance(raw, dict) else {}
    roles = ["surface", "surface-soft", "ink", "ink-strong", "muted", "hairline", "brand", "success", "warning", "danger"]
    for role in roles:
        value = tokens.get("--color-" + role)
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            fail(f"Theme lacks resolved --color-{role}")
    for role in ["sans", "mono"]:
        if not isinstance(tokens.get("--font-family-" + role), str):
            fail(f"Theme lacks --font-family-{role}")
    return tokens, path


def rank(items, brief):
    words = re.findall(r"[\w-]+", brief.casefold())
    def score(item):
        text = " ".join([item["slug"], item["name_ko"], item["category"], item["prompt_ko"], *item.get("signals", [])]).casefold()
        return sum(4 if w in item["slug"].casefold() or w in item["name_ko"] else 1 for w in words if w in text)
    return sorted(items, key=lambda x: (-score(x), x["slug"]))


def packet(args, supported_only=False):
    root = pathlib.Path(args.catalog_root).expanduser()
    items, path = catalogue(root)
    if args.recipe:
        item = next((x for x in items if x["slug"] == args.recipe), None)
        if item is None:
            fail(f"Unknown recipe: {args.recipe}")
        reason = "explicit recipe"
    else:
        if not args.brief.strip():
            fail("A brief or explicit recipe is required")
        item = rank(items, args.brief)[0]
        reason = "brief match: " + args.brief
    tokens, token_path = theme_tokens(root, args.theme)
    library_path = root / "catalogs/prompt-motion/source-skills/cinetic/skills/cinetic/assets/library/techniques.json"
    license_path = root / "catalogs/prompt-motion/source-skills/cinetic/LICENSE"
    license_notice = license_path.read_text(encoding="utf-8")
    if "MIT License" not in license_notice or "Permission is hereby granted" not in license_notice:
        fail("Cinetic MIT permission notice missing")
    library = read_json(library_path)
    techniques = library.get("techniques") if isinstance(library, dict) else None
    if not isinstance(techniques, list) or not techniques or any(not isinstance(x, dict) or any(not isinstance(x.get(k), str) for k in ["id", "name", "category", "recipe", "timing"]) for x in techniques):
        fail("Malformed technique library")
    family, variant = TEMPLATES.get(item["slug"], (None, None))
    categories = {"typography": ["typography_motion", "pacing_structure", "camera"], "flow": ["ui_choreography", "transition", "camera"], "data": ["data_and_numbers", "typography_motion", "camera"]}.get(family, ["opening_hook", "transition", "camera"])
    selected = [next((x for x in techniques if x["category"] == c), None) for c in categories]
    if any(x is None for x in selected):
        fail("Technique library lacks required categories")
    return {
        "recipe": item, "reason": reason, "theme": args.theme,
        "template_support": {"supported": bool(family), "family": family, "variant": variant, "renderer_inputs": FIELDS.get(variant, []), "boundary": "Ready for the listed structured inputs" if family else "Custom authoring required; this renderer does not synthesize missing media, models, audio or product evidence"},
        "recommended_techniques": selected,
        "license_notice": license_notice,
        "sources": {"catalog": {"path": str(path), "sha256": sha(path)}, "techniques": {"path": str(library_path), "sha256": sha(library_path)}, "license": {"path": str(license_path), "sha256": sha(license_path)}, "tokens": {"path": str(token_path), "sha256": sha(token_path)}},
        "resolved_tokens": tokens,
    }


def source_inputs(raw, variant, theme):
    """Translate documented renderer inputs to their catalogue names without inventing data."""
    common = {"theme": theme}
    if "duration" in raw:
        common.update({"duration": raw["duration"], "총 길이": raw["duration"]})
    def members(key):
        return raw[key] if isinstance(raw.get(key), list) else []
    mapping = {
        "route": {"직접 쓴 세 문장": raw.get("phrases"), "핵심 동사": raw.get("verb")},
        "poster": {"headline": raw.get("title"), "facts": raw.get("facts")},
        "mask": {"새 핵심어": raw.get("title"), "자체 제작 선화": raw.get("line_art"), "짧은 원고": raw.get("phrases")},
        "ribbon": {"상태명 목록": raw.get("steps"), "전환 조건": [x.get("detail") for x in members("steps") if isinstance(x, dict)], "가로 비율": "16:9"},
        "decision": {"workflow_steps": raw.get("steps"), "sample_input": raw.get("sample_input"), "verification_step": raw.get("verification_step")},
        "recursive": {"검증된 개념 원고": raw.get("title"), "반복 예시": raw.get("levels"), "종료 조건": raw.get("stop_condition")},
        "milestone": {"검증된 사건 목록": raw.get("events"), "날짜와 출처": raw.get("events"), "관계 유형": raw.get("relation_type")},
        "notes": {"product": raw.get("product"), "verified_result": raw.get("verified_result"), "evidence": raw.get("notes")},
        "drawing": {"owned_drawings": raw.get("drawings"), "concepts": [x.get("label") for x in members("drawings") if isinstance(x, dict)], "relations": raw.get("relations")},
        "stack": {"검증된 단계별 양": raw.get("numbers"), "단위": [x.get("unit") for x in members("numbers") if isinstance(x, dict)], "누적 대상": raw.get("title")},
        "signal": {"signal_data": raw.get("signal_data"), "meaning_labels": raw.get("meaning_labels")},
    }.get(variant, {})
    return {**common, **mapping, **raw, **raw.get("source_inputs", {}), "theme": theme}


def input_gate(info, raw):
    if raw is None:
        info["missing_inputs"] = [x for x in info["recipe"]["inputs"] if x != "theme"]
        info["input_status"] = "not_provided"
        info["render_ready"] = False
        return
    if not isinstance(raw, dict) or ("source_inputs" in raw and not isinstance(raw["source_inputs"], dict)):
        fail("Inputs must be a JSON object; source_inputs, when present, must be an object")
    values = source_inputs(raw, info["template_support"]["variant"], info["theme"])
    def empty(value):
        return value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, (list, dict)) and len(value) == 0)
    missing = [x for x in info["recipe"]["inputs"] if empty(values.get(x))]
    info["missing_inputs"] = missing
    info["input_status"] = "missing" if missing else "authoring_ready"
    info["render_ready"] = False
    variant = info["template_support"]["variant"]
    if not missing and variant and "title" in raw and any(k.split(" (")[0] in raw for k in FIELDS[variant] if k not in ["title", "duration"]):
        normalize_input(raw, variant)
        info["input_status"] = "renderer_validated"
        info["render_ready"] = True


def text(value, name, maximum=100):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        fail(f"Invalid {name}: required text, at most {maximum} characters")
    return value.strip()


def rows(value, name, fields, minimum=2, maximum=5):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        fail(f"Invalid {name}: expected {minimum}–{maximum} rows")
    output = []
    for i, row in enumerate(value):
        if not isinstance(row, dict):
            fail(f"Invalid {name}[{i}]")
        output.append({k: text(row.get(k), f"{name}[{i}].{k}", 140 if k == "source" else 80) for k in fields})
    return output


def points(value, name):
    if not isinstance(value, list) or not 2 <= len(value) <= 100:
        fail(f"Invalid {name}: expected 2–100 normalized point pairs")
    if any(not isinstance(p, list) or len(p) != 2 or any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in p) for p in value):
        fail(f"Invalid {name}: points must be finite values in [0, 1]")
    return value


def normalize_input(raw, variant):
    if not isinstance(raw, dict):
        fail("Inputs must be a JSON object")
    out = {"title": text(raw.get("title"), "title", 80), "subtitle": raw.get("subtitle", "")}
    if not isinstance(out["subtitle"], str) or len(out["subtitle"]) > 100:
        fail("Invalid subtitle")
    for k, default, low, high in [("duration", 12, 8, 60), ("bpm", 120, 90, 180)]:
        v = raw.get(k, default)
        if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
            fail(f"Invalid {k}: expected {low}–{high}")
        out[k] = v
    out["language"] = raw.get("language", "ko")
    if out["language"] not in ["ko", "en"]:
        fail("Supported template languages: ko, en; custom copy authoring supports other languages")
    if variant in ["route", "mask"]:
        a = raw.get("phrases")
        if not isinstance(a, list) or (variant == "route" and len(a) != 3) or not 2 <= len(a) <= 4:
            fail("Phrases require three lines for text-built-route, or 2–4 for a mask")
        out["phrases"] = [text(x, "phrase", 65) for x in a]
        if variant == "route":
            out["verb"] = text(raw.get("verb"), "verb", 30)
            if not any(out["verb"] in x for x in out["phrases"]):
                fail("The key verb must appear in the supplied phrases")
        else:
            out["line_art"] = points(raw.get("line_art"), "owned line_art")
    elif variant in ["ribbon", "decision"]:
        out["steps"] = rows(raw.get("steps"), "steps", ["label", "detail"])
        if variant == "decision":
            out["input_source"] = text(raw.get("input_source"), "input_source")
            out["verification_step"] = text(raw.get("verification_step"), "verification_step")
            if not any(out["verification_step"] in x["label"] for x in out["steps"]):
                fail("verification_step must match a supplied step label")
    elif variant == "recursive":
        out["steps"] = rows(raw.get("levels"), "levels", ["label", "detail"], 2, 4)
        out["stop_condition"] = text(raw.get("stop_condition"), "stop_condition")
    elif variant == "milestone":
        out["steps"] = rows(raw.get("events"), "events", ["label", "date", "source"])
    elif variant in ["notes", "poster"]:
        out["steps"] = rows(raw.get("notes" if variant == "notes" else "facts"), "notes/facts", ["label", "detail", "source"], 2, 4)
        if variant == "notes":
            out["product"] = text(raw.get("product"), "product")
            out["verified_result"] = text(raw.get("verified_result"), "verified_result")
    elif variant == "drawing":
        a = raw.get("drawings")
        if not isinstance(a, list) or not 2 <= len(a) <= 4:
            fail("drawings must contain 2–4 owned drawings")
        out["drawings"] = [{"label": text(x.get("label"), "drawing label"), "points": points(x.get("points"), "owned drawing points")} for x in a if isinstance(x, dict)]
        if len(out["drawings"]) != len(a):
            fail("Invalid drawing")
        links = raw.get("relations")
        if not isinstance(links, list) or not links or len(links) > 6:
            fail("relations must contain 1–6 explicit links")
        for x in links:
            if not isinstance(x, dict) or any(type(x.get(k)) is not int or not 0 <= x[k] < len(a) for k in ["from", "to"]):
                fail("Invalid relation endpoint")
            text(x.get("label"), "relation label", 60)
        out["relations"] = links
    elif variant == "stack":
        a = raw.get("numbers")
        out["numbers"] = rows(a, "numbers", ["label", "unit", "source"])
        for src, dst in zip(a, out["numbers"]):
            value = src.get("value")
            if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
                fail("Numbers must be finite nonnegative values; missing values are never replaced")
            dst["value"] = value
        if len({x["unit"] for x in out["numbers"]}) != 1:
            fail("Stack quantities require one unit")
        total = format(sum(Decimal(str(x["value"])) for x in out["numbers"]), "f")
        out["total_display"] = total.rstrip("0").rstrip(".") if "." in total else total
    elif variant == "signal":
        a = raw.get("signal_data")
        if not isinstance(a, list) or not 8 <= len(a) <= 256 or any(type(x) not in (int, float) or not math.isfinite(x) for x in a) or max(a) == min(a):
            fail("signal_data requires 8–256 finite, varying samples")
        out["signal_data"] = a
        out["steps"] = rows(raw.get("meaning_labels"), "meaning_labels", ["label", "detail"], 2, 4)
        out["signal_source"] = text(raw.get("signal_source"), "signal_source")
        out["signal_kind"] = raw.get("signal_kind")
        if out["signal_kind"] not in ["observed", "synthetic"]:
            fail("signal_kind must explicitly be observed or synthetic")
    return out


def selected_parts(parts, info, data):
    family = info["template_support"]["family"]
    variant = info["template_support"]["variant"]
    tokens = info["resolved_tokens"]
    color_roles = {"bg": "surface", "panel": "surface-soft", "line": "hairline", "grid": "hairline", "ink": "ink", "strong": "ink-strong", "dim": "muted", "acc": "brand", "accHi": "brand", "alt": "brand", "bad": "danger"}
    colors = {k: tokens["--color-" + v] for k, v in color_roles.items()}
    fonts = {"sans": tokens["--font-family-sans"], "display": tokens["--font-family-sans"], "mono": tokens["--font-family-mono"]}
    cfg = {"bpm": data["bpm"], "colors": colors, "fonts": fonts, "textSplit": False, "hudTitle": "", "cta": {"href": "", "newTab": True}, "endCta": None, "endCtaBeat": 0, "posterT": 0, "watchKey": "prompt-motion-" + info["recipe"]["slug"], "music": {"groove": "soft", "liteScenes": [], "arpScenes": [], "tailBeats": data["duration"] * data["bpm"] / 60 / 3}}
    parts["config"] = "const CFG = " + js_json(cfg) + ";\nCFG.hudMeta = () => '';\n"
    title = html.escape(data["title"], quote=True)
    parts["head"] = f'<meta charset="UTF-8">\n<title>{title}</title>\n<meta name="description" content="{title}">\n<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">\n' + '''<style>
/* Keep the existing play/replay button in the existing dock, outside all film copy. */
#dock #start{position:static;transform:none;width:max-content;max-width:100%;box-sizing:border-box;min-height:44px;font-size:14px;gap:8px;padding:10px 14px}
#dock #start .tri{border-left-width:12px;border-top-width:8px;border-bottom-width:8px}
#dock #start small{font-size:12px}
#dock #start>span:last-child{min-width:0}
</style>
'''
    language = data["language"]
    ui = {"title": data["title"], "play": "사운드와 함께 재생" if language == "ko" else "Play with sound", "playsub": "클릭 또는 스페이스" if language == "ko" else "click or press Space", "playsubtouch": "탭해서 재생" if language == "ko" else "tap to play", "replay": "다시 재생" if language == "ko" else "Replay", "rotate": "가로로 돌리면 크게 볼 수 있어요" if language == "ko" else "Rotate for a bigger view", "fullscreen": "전체 화면" if language == "ko" else "Full screen", "scrub": "재생 위치" if language == "ko" else "Playback position", "canvas": data["title"], "ctaLab": "", "ctaSub": "", "ctaGo": "", "endTag": "", "lang": ""}
    parts["copy"] = "I18N." + language + " = " + js_json({"ui": ui}) + ";\n"
    template = (SKILL_ROOT / "assets/prompt-motion-scenes.js").read_text()
    blocks = {}
    for name in ["pm-style", "pm-common", "pm-" + family]:
        match = block_re(name).search(template)
        if not match:
            fail(f"Renderer template block missing: {name}")
        blocks[name] = match.group("body")
    timing = info["recommended_techniques"][0]["timing"]
    match = re.search(r"\b(\d{1,3}) f\b", timing)
    arrival = max(.2, min(1.2, int(match.group(1)) / 60)) if match else .45
    # The full selected prompt goes into the actual editable scene input; originals remain in 15.
    pm = {"family": family, "variant": variant, "input": data, "arrivalSeconds": arrival, "authoring": {"prompt_ko": info["recipe"]["prompt_ko"], "required_inputs": info["recipe"]["inputs"], "originality_changes": info["recipe"].get("originality_changes", []), "reason": info["reason"], "sources": info["sources"], "techniques": info["recommended_techniques"], "license_notice": info["license_notice"]}}
    parts["geometry"] = "const PM = " + js_json(pm) + ";\n"
    parts["style"] = blocks["pm-style"]
    # Sound events come from the same absolute-time entrances used by the renderer.
    count = len(data.get("phrases", data.get("steps", data.get("numbers", data.get("drawings", [])))))
    if variant == "route":
        events = [data["duration"] * i / (count + 1) for i in range(count)] + [data["duration"] * 2 / 3 + i for i in range(count)]
    elif variant in ["ribbon", "decision"]:
        events = [data["duration"] * i / count for i in range(count) if i / count < 2 / 3] + [data["duration"] * 2 / 3] + [data["duration"] * 2 / 3 + 60 / data["bpm"] + i for i in range(count)]
    elif variant == "stack":
        events = [data["duration"] * i / (count + 1) for i in range(count)] + [data["duration"] * 2 / 3]
    else:
        events = [data["duration"] * i / max(1, count + 1) for i in range(max(1, count))]
    scene_code = []
    for name, offset in [("intro", 0), ("detail", 1), ("close", 2)]:
        start = offset * data["duration"] / 3
        cues = [[0, "pad", [220, 261.63, 329.63], data["duration"] / 3, .11]]
        cues += [[t - start, "blip", 440 + i * 110, .08] for i, t in enumerate(events) if start <= t < start + data["duration"] / 3]
        scene_code.append(f"S.{name} = {{ draw(lt,d){{ pmDraw{family.title()}(({offset} + lt/d)/3, lt, d); }}, cues: d => " + js_json(cues) + " };")
    parts["scenes"] = blocks["pm-common"] + "\n" + blocks["pm-" + family] + "\n" + "\n".join(scene_code) + "\n"
    beats = data["duration"] * data["bpm"] / 60 / 3
    parts["plan"] = "const PLAN = " + js_json([["intro", beats, ""], ["detail", beats, ""], ["close", beats, ""]]) + ";\n"
    parts["ready"] = "// Preserve the engine button and its handlers; place it outside the film.\ndocument.getElementById('dock').prepend(document.getElementById('start'));\ndocument.documentElement.style.setProperty('--sans', CFG.fonts.sans);\n"
    return parts


def block_re(name: str) -> re.Pattern:
    # opening marker line, body, closing marker line (JS `// @@x` or HTML `<!-- @@x -->`), indentation allowed
    return re.compile(
        r"(?P<open>^[ \t]*(?://|<!--) @@" + name + r"(?: -->)?[ \t]*\n)(?P<body>.*?)(?P<close>^[ \t]*(?://|<!--) @@/" + name + r"(?: -->)?[ \t]*$)",
        re.S | re.M,
    )


def split(src: pathlib.Path, out: pathlib.Path) -> None:
    write_parts(src, out)


def write_parts(src, out, info=None, data=None):
    if out.exists():
        fail(f"Parts destination already exists: {out}; choose a fresh directory to preserve edits")
    text = src.read_text(encoding="utf-8")
    content = {}
    for name, ext in PARTS.items():
        m = block_re(name).search(text)
        if not m:
            fail(f"marker @@{name} not found in {src} — is it built on assets/engine.html?")
        content[name] = m.group("body")
    if info:
        content = selected_parts(content, info, data)
        text = assembled(text, content)
        syntax_check(text)
    out.mkdir(parents=True, exist_ok=False)
    for name, ext in PARTS.items():
        (out / f"{name}.{ext}").write_text(content[name], encoding="utf-8")
    (out / "_shell.html").write_text(text, encoding="utf-8")
    print(f"split {src.name} → {out}/ : " + ", ".join(f"{n}.{e}" for n, e in PARTS.items()) + " (+ _shell.html, do not edit)")
    if info:
        (out / "recipe-input.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n")
        print(f"recipe {info['recipe']['slug']} → {info['template_support']['family']}/{info['template_support']['variant']}; source inputs complete")


def assembled(shell, content):
    for name, body in content.items():
        if body and not body.endswith("\n"):
            body += "\n"
        shell, count = block_re(name).subn(lambda m: m.group("open") + body + m.group("close"), shell, count=1)
        if count != 1:
            fail(f"marker @@{name} not found in shell")
    return shell


def syntax_check(text):
    script = re.search(r"<script>(.*)</script>", text, re.S)
    node = shutil.which("node")
    if script and node:
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8") as tf:
            tf.write(script.group(1))
            tf.flush()
            result = subprocess.run([node, "--check", tf.name], capture_output=True, text=True)
            if result.returncode:
                fail("script syntax error:\n" + result.stderr.replace(tf.name, "script"))
    return bool(script and node)


def build(parts: pathlib.Path, dst: pathlib.Path) -> None:
    shell = parts / "_shell.html"
    if not shell.exists():
        sys.exit(f"{shell} missing — run `assemble.py split` first")
    content = {}
    for name, ext in PARTS.items():
        f = parts / f"{name}.{ext}"
        if not f.exists():
            continue
        content[name] = f.read_text(encoding="utf-8")
    text = assembled(shell.read_text(encoding="utf-8"), content)
    checked = syntax_check(text)
    dst.write_text(text, encoding="utf-8")
    print(f"built {dst} ({len(text.splitlines())} lines){' · syntax ok' if checked else ''}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ["split", "build", "info", "recipes"]:
        p = actions.add_parser(action)
        if action in ["split", "build"]:
            p.add_argument("source", type=pathlib.Path)
            p.add_argument("destination", type=pathlib.Path)
        if action != "build":
            p.add_argument("--recipe", default="")
            p.add_argument("--brief", default="")
            p.add_argument("--theme", default="npl")
            p.add_argument("--inputs", type=pathlib.Path)
            p.add_argument("--catalog-root", default=str(DESIGN_ROOT))
    args = parser.parse_args()
    try:
        if args.action == "build":
            build(args.source.expanduser(), args.destination.expanduser())
        elif args.action == "recipes":
            items, _ = catalogue(pathlib.Path(args.catalog_root))
            print(json.dumps([{"slug": x["slug"], "name_ko": x["name_ko"], "category": x["category"], "required_inputs": x["inputs"], "template": TEMPLATES.get(x["slug"]), "authoring": "info --recipe " + x["slug"]} for x in rank(items, args.brief)], ensure_ascii=False, indent=2))
        elif args.action == "info":
            result = packet(args)
            input_gate(result, read_json(args.inputs) if args.inputs else None)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if args.inputs and result["missing_inputs"]:
                sys.exit(2)
        elif not (args.recipe or args.brief or args.inputs):
            split(args.source.expanduser(), args.destination.expanduser())
        else:
            result = packet(args, supported_only=True)
            if not result["template_support"]["supported"]:
                fail(f"Recipe {result['recipe']['slug']} needs custom authoring: {result['template_support']['boundary']}; required inputs: {result['recipe']['inputs']}. Use info, then author the existing parts; no generic substitution was made.")
            if not args.inputs:
                fail("Template generation requires --inputs JSON; no numbers, claims or brand are invented")
            raw = read_json(args.inputs)
            input_gate(result, raw)
            if result["missing_inputs"]:
                fail("Missing source inputs: " + ", ".join(result["missing_inputs"]))
            data = normalize_input(raw, result["template_support"]["variant"])
            result["render_ready"] = True
            result["input_status"] = "renderer_validated"
            write_parts(args.source.expanduser(), args.destination.expanduser(), result, data)
    except (ValueError, OSError) as error:
        print(f"assemble: {error}", file=sys.stderr)
        sys.exit(2)
