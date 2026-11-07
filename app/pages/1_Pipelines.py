import json
from pathlib import Path

import streamlit as st

from core import fields as F, paths, wizard
from core.db import open_db
from core.registry import load_all
from core.steps import all_steps, steps_for
from core.steps.base import broken_steps, origin_of
from core.steps.custom import KINDS, reload_custom_steps, scaffold_step

paths.load_env()
st.set_page_config(page_title="Pipelines", layout="wide")
st.title("Pipelines")
con = open_db()
ss = st.session_state
ss.setdefault("pl_view", "Pipelines")
VIEWS = ["Pipelines", "Wizard", "Custom steps"]
view = st.radio("View", VIEWS, index=VIEWS.index(ss["pl_view"]), horizontal=True, label_visibility="collapsed")
ss["pl_view"] = view


def start_wizard(mode: str, data: dict, sop: dict[str, str]) -> None:
    for k in [k for k in ss if k.startswith("wzw_")]:
        del ss[k]                                       # forget old widget values so the new base config shows
    ss.update(wz=data, wz_mode=mode, wz_sop=sop, wz_page=0, pl_view="Wizard")


# =================================================================== list
if view == "Pipelines":
    loaded = load_all()
    c1, c2 = st.columns([1, 5])
    if c1.button("New pipeline", type="primary"):
        start_wizard("new", wizard.template_dict(), {})
        st.rerun()
    if not loaded:
        st.info("No pipelines yet. Press New pipeline.")
    for p in loaded:
        ok = p.config is not None
        with st.expander(f"{'OK' if ok else 'INVALID'}  {p.dir.name}" + (f" - {p.config.title}" if ok else ""), expanded=not ok):
            if not ok:
                for line in p.problems:
                    st.write(f"- {line}")
                continue
            cfg = p.config
            st.write("**Steps:** " + " > ".join(s.step + ("" if s.step not in p.step_unavailable else " (not built yet)") + (" [custom]" if origin_of(s.step) == cfg.name else "") for s in cfg.steps))
            for line in p.step_problems:
                st.error(line)
            for f in p.missing_sop:
                st.warning(f"SOP file listed but missing: {f}")
            st.write(f"**Write tab:** {cfg.output.write_tab.name} ({len(cfg.output.columns)} columns); dedupes against {', '.join(t.name for t in cfg.output.tabs)}")
            b = cfg.budget
            st.write(f"**Budget:** cap ${b.default_cycle_cap_usd:.2f} (hard max ${b.hard_max_cycle_cap_usd:.2f}), key floor ${b.min_key_balance_usd:.2f}")
            if cfg.exhausted_sources:
                st.write("**Exhausted sources (warned about before a rerun):**")
                for e in cfg.exhausted_sources:
                    st.write(f"- {e.source}: {e.note} ({e.date})")
            a, b2, c3, _ = st.columns([1, 1, 1, 4])
            if a.button("Edit", key=f"ed_{p.dir.name}"):
                start_wizard("edit", wizard.from_config(cfg), wizard.read_sop_files(cfg, p.dir))
                st.rerun()
            if b2.button("Clone", key=f"cl_{p.dir.name}"):
                d = wizard.clone_dict(cfg, f"{cfg.name}_copy")
                start_wizard("clone", d, wizard.read_sop_files(cfg, p.dir))
                st.rerun()
            busy = con.execute("SELECT COUNT(*) FROM cycles WHERE pipeline=? AND status='active'", (cfg.name,)).fetchone()[0]
            ok_arch = c3.checkbox("Allow archive", key=f"aa_{p.dir.name}", help="Archiving moves the folder to pipelines/_archived. Nothing is deleted.")
            if c3.button("Archive", key=f"ar_{p.dir.name}", disabled=not ok_arch or bool(busy)):
                dest = wizard.archive_pipeline(cfg.name)
                st.success(f"Moved to {dest}")
                st.rerun()
            if busy:
                st.caption(f"Has {busy} active cycle(s): end them on Run Cycle before archiving.")
            st.code((p.dir / "pipeline.yaml").read_text(encoding="utf-8"), language="yaml")

    st.subheader("Validate YAML")
    text = st.text_area("Paste a pipeline.yaml to check it (nothing is saved)", height=160)
    if text.strip():
        v = wizard.validate_text(text)
        if v.ok:
            st.success(f"Valid: {v.config.name} with {len(v.config.steps)} steps")
        for line in v.problems:
            st.error(line)
        for line in v.warnings:
            st.warning(line)

# =================================================================== wizard
elif view == "Wizard":
    if "wz" not in ss:
        st.info("Start from the Pipelines view: New pipeline, Edit or Clone.")
        st.stop()
    d, mode, sop = ss["wz"], ss["wz_mode"], ss["wz_sop"]
    PAGES = ["1 Basics", "2 Company profile", "3 Evidence", "4 People", "5 Steps", "6 Sheet output", "7 Budget, LLM, SOPs"]
    page = st.radio("Step", PAGES, index=ss["wz_page"], horizontal=True, label_visibility="collapsed")
    ss["wz_page"] = PAGES.index(page)
    st.caption({"new": "Creating a new pipeline", "edit": "Editing an existing pipeline (the old file is backed up on save)", "clone": "Creating a pipeline from a clone"}[mode])
    W = lambda k: f"wzw_{ss['wz_page']}_{k}"                               # widget keys are per page, per field

    if ss["wz_page"] == 0:
        d["name"] = st.text_input("Name (lowercase slug; it becomes the folder name)", d["name"], key=W("name"), disabled=(mode == "edit"))
        d["title"] = st.text_input("Title", d["title"], key=W("title"))
        if mode == "new":
            names = [p.dir.name for p in load_all() if p.config]
            if names:
                src = st.selectbox("...or start from an existing pipeline", ["(blank template)"] + names, key=W("src"))
                if src != "(blank template)" and st.button("Use it as the starting point"):
                    cfg0 = next(p for p in load_all() if p.config and p.dir.name == src)
                    start_wizard("clone", wizard.clone_dict(cfg0.config, d["name"] or f"{src}_copy"), wizard.read_sop_files(cfg0.config, cfg0.dir))
                    st.rerun()

    elif ss["wz_page"] == 1:
        d["icp"]["description"] = st.text_area("Ideal company (what qualifies)", d["icp"]["description"], key=W("desc"), height=100)
        d["icp"]["reject_company_types"] = wizard.lines(st.text_area("Reject these company types (one per line)", wizard.unlines(d["icp"]["reject_company_types"]), key=W("rct"), height=100))
        d["icp"]["reject_names"] = wizard.lines(st.text_area("Reject these names (one per line)", wizard.unlines(d["icp"]["reject_names"]), key=W("rn"), height=80))
        opts = sorted(set(wizard.COMMON_COUNTRIES) | set(d["countries"]["approved"]) | set(d["countries"]["excluded"]))
        d["countries"]["approved"] = st.multiselect("Approved countries", opts, d["countries"]["approved"], key=W("appr"))
        d["countries"]["excluded"] = st.multiselect("Excluded countries (company, team AND person)", opts, d["countries"]["excluded"], key=W("excl"))
        d["countries"]["excluded_patterns"] = wizard.lines(st.text_area("Excluded-country regexes (city names, domain suffixes; one per line)", wizard.unlines(d["countries"]["excluded_patterns"]), key=W("pat"), height=80,
                                                                         help="Matched against country, city and headline text. Example: mumbai"))

    elif ss["wz_page"] == 2:
        ev = d["evidence"]
        st.caption("Wildcards: `*` ends a word (KI-generiert*), {Brand} means a capitalised word (for {Brand}). Strong terms never match inside a longer word.")
        ev["strong_terms"] = wizard.lines(st.text_area("Strong terms: wording that shows the evidence you look for (one per line)", wizard.unlines(ev["strong_terms"]), key=W("st"), height=130))
        ev["client_cues"] = wizard.lines(st.text_area("Client cues: wording that must sit next to a strong term (one per line)", wizard.unlines(ev["client_cues"]), key=W("cc"), height=110))
        ev["false_positive_patterns"] = wizard.lines(st.text_area("False-positive regexes: if they match the sentence, it is dropped (one per line)", wizard.unlines(ev["false_positive_patterns"]), key=W("fp"), height=90))
        ev["reject_if"] = wizard.lines(st.text_area("Evidence that does NOT count (shown to reviewers and the LLM)", wizard.unlines(ev["reject_if"]), key=W("ri"), height=90))

    elif ss["wz_page"] == 3:
        pe = d["people"]
        pe["decision_titles"] = wizard.lines(st.text_area("Decision-maker titles (best first)", wizard.unlines(pe["decision_titles"]), key=W("dt"), height=130))
        pe["reject_titles"] = wizard.lines(st.text_area("Reject titles", wizard.unlines(pe["reject_titles"]), key=W("rt"), height=100))
        pe["max_per_company"] = st.number_input("Max people per company on the sheet", 1, 10, int(pe["max_per_company"]), key=W("mp"))
        pe["role_families"] = wizard.parse_families(st.text_area("Role families (one per line, like  ceo: founder, owner)", wizard.format_families(pe["role_families"]), key=W("rf"), height=100))
        pe["database_title_confidence"] = st.selectbox("Confidence for a title that comes only from a database", ["Medium", "High"], index=0 if pe["database_title_confidence"] == "Medium" else 1, key=W("dc"))

    elif ss["wz_page"] == 4:
        reg = steps_for(d["name"] if mode != "new" else None)
        st.caption("Steps run in this order. Paid, LLM and write steps always stop at the confirmation screen. Custom steps of this pipeline appear here once their file exists (Custom steps view).")
        new_steps = []
        for i, s in enumerate(d["steps"]):
            with st.expander(f"{i + 1}. {s['step']}  [{s['stage']}]", expanded=False):
                ids = sorted(reg)
                if s["step"] not in ids:          # never silently swap an unknown step for another one: keep it, and say so
                    ids = [s["step"]] + ids
                    st.error(f"'{s['step']}' is not an available step (a removed or broken custom step?). Fix its file, or choose another step here.")
                sid = st.selectbox("Step", ids, index=ids.index(s["step"]), key=W(f"s{i}"))
                stages = ["companies", "people", "review", "write"]
                stage = st.selectbox("Stage", stages, index=stages.index(s["stage"]), key=W(f"g{i}"))
                raw = st.text_area("Parameters (JSON)", json.dumps(s.get("params", {}), indent=1), key=W(f"p{i}"), height=110)
                try:
                    params = json.loads(raw or "{}")
                except ValueError as e:
                    st.error(f"parameters are not valid JSON: {e}")
                    params = s.get("params", {})
                if sid in reg:
                    st.caption(f"{reg[sid].kind}: {reg[sid].title}")
                keep = not st.checkbox("Remove this step", key=W(f"x{i}"))
                if keep:
                    new_steps.append({"step": sid, "stage": stage, "params": params})
        d["steps"] = new_steps
        c1, c2 = st.columns([2, 1])
        add = c1.selectbox("Add a step", ["(choose)"] + sorted(reg), key=W("add"))
        if add != "(choose)" and c2.button("Add"):
            d["steps"].append({"step": add, "stage": "companies", "params": {}})
            st.rerun()

    elif ss["wz_page"] == 5:
        o = d["output"]
        o["sheet_id_env"] = st.text_input("Environment variable holding the sheet ID (IDs never live in git)", o["sheet_id_env"], key=W("env"))
        wt = next(t for t in o["tabs"] if t["write"])
        wt["name"] = st.text_input("Write tab name", wt["name"], key=W("wtn"))
        cols = wizard.lines(st.text_area("Columns, in sheet order (one per line)", wizard.unlines(o["columns"]), key=W("cols"), height=200))
        o["columns"], wt["header"] = cols, list(cols)
        wt["range"] = st.text_input("Write tab range", wt["range"], key=W("wtr"), help="Example: Leads!A1:J6000. Rows are appended to this tab only.")
        others = [t for t in o["tabs"] if not t["write"]]
        txt = st.text_area("Other tabs checked for duplicates (one per line: name | range). They are never written.", "\n".join(f"{t['name']} | {t['range']}" for t in others), key=W("oth"), height=90)
        o["tabs"] = [wt] + [{"name": a.strip(), "range": b.strip(), "write": False, "header": []} for a, _, b in (ln.partition("|") for ln in wizard.lines(txt)) if a.strip() and b.strip()]
        de = o["dedupe"]
        pick = lambda label, cur, k: st.selectbox(label, cols or [cur], index=(cols.index(cur) if cur in cols else 0), key=W(k))
        de["name_field"] = pick("Name column", de["name_field"], "nf")
        de["company_field"] = pick("Company column", de["company_field"], "cf")
        de["country_field"] = pick("Country column", de["country_field"], "ctf")
        de["evidence_field"] = pick("Evidence column (must never be empty)", de["evidence_field"], "ef")
        de["url_fields"] = st.multiselect("Profile URL column(s); the first must hold a personal profile link", cols, [c for c in de["url_fields"] if c in cols], key=W("uf")) or de["url_fields"]
        de["profile_url_markers"] = wizard.lines(st.text_area("A valid profile URL contains one of (one per line)", wizard.unlines(de["profile_url_markers"]), key=W("pum"), height=70))
        de["batch_size"] = st.number_input("Rows per append batch (tabs are re-read before every batch)", 1, 10, int(de["batch_size"]), key=W("bs"))
        with st.expander("Field mapping (which of your columns holds each internal field)"):
            st.caption("The people steps fill internal fields (name, company, title, ...). If your column has a different name, map it here. Unmapped internal fields are simply left empty; "
                       "a column that is not mapped keeps its own name and is filled by hand during review.")
            fm = {}
            for internal in F.INTERNAL_FIELDS:
                cur = o["field_map"].get(internal, internal if internal in cols else "(none)")
                choice = st.selectbox(internal, ["(none)"] + cols, index=(["(none)"] + cols).index(cur) if cur in (["(none)"] + cols) else 0, key=W(f"fm_{internal}"))
                if choice not in ("(none)", internal):
                    fm[internal] = choice
            o["field_map"] = fm

    elif ss["wz_page"] == 6:
        b = d["budget"]
        b["hard_max_cycle_cap_usd"] = st.number_input("Hard maximum spend per cycle (USD)", 0.1, 1000.0, float(b["hard_max_cycle_cap_usd"]), step=0.5, key=W("hm"))
        b["default_cycle_cap_usd"] = min(st.number_input("Default spend cap per cycle (USD)", 0.1, 1000.0, float(b["default_cycle_cap_usd"]), step=0.5, key=W("dc")), b["hard_max_cycle_cap_usd"])
        b["min_key_balance_usd"] = st.number_input("Minimum key balance for a paid run (USD)", 0.0, 100.0, float(b["min_key_balance_usd"]), step=0.1, key=W("mk"))
        sr = b["stop_rules"]
        c1, c2, c3 = st.columns(3)
        sr["max_cost_per_row"] = c1.number_input("Stop: cost per row above (USD)", 0.01, 100.0, float(sr["max_cost_per_row"]), key=W("sr1"))
        sr["min_pass_rate"] = c2.number_input("Stop: pass rate below", 0.0, 1.0, float(sr["min_pass_rate"]), step=0.01, key=W("sr2"))
        sr["min_usable_credit"] = c3.number_input("Stop: usable credit below (USD)", 0.0, 1000.0, float(sr["min_usable_credit"]), key=W("sr3"))
        st.markdown("**LLM assist (optional; suggestions only)**")
        L = d["llm"]
        L["enabled"] = st.checkbox("Enable for this pipeline (the global Settings toggle and an API key are also needed)", L["enabled"], key=W("le"))
        L["provider"] = "anthropic" if L["enabled"] else "none"
        L["model"] = st.text_input("Model", L["model"] or "claude-sonnet-5-5", key=W("lm")) if L["enabled"] else L["model"]
        L["cycle_cap_usd"] = st.number_input("LLM cap per cycle (USD)", 0.0, 100.0, float(L["cycle_cap_usd"]), step=0.25, key=W("lc"))
        st.markdown("**SOP / rubric files (markdown)**")
        up = st.file_uploader("Upload .md files", type=["md"], accept_multiple_files=True, key=W("up"))
        for f in up or []:
            try:
                sop[wizard._safe_sop_name(f.name)] = f.getvalue().decode("utf-8")
            except (ValueError, UnicodeDecodeError) as e:
                st.error(f"{f.name}: {e}")
        n1, n2 = st.columns(2)
        nm, nt = n1.text_input("...or paste one: file name (e.g. rules.md)", key=W("pn")), n2.text_area("text", key=W("pt"), height=80)
        if nm and nt and st.button("Add pasted SOP"):
            try:
                sop[wizard._safe_sop_name(nm)] = nt
            except ValueError as e:
                st.error(str(e))
        have = sorted(sop)
        picks = lambda label, cur, k: [f"sop/{x}" for x in st.multiselect(label, have, [Path(c).name for c in cur if Path(c).name in have], key=W(k))]
        d["sop_files"] = picks("All SOP files of this pipeline", d["sop_files"], "sf")
        L["company_sop_files"] = picks("Used for LLM company verdicts", L["company_sop_files"], "csf")
        L["person_sop_files"] = picks("Used for LLM person drafts", L["person_sop_files"], "psf")
        if have:
            st.caption("Files: " + ", ".join(f"{x} ({len(sop[x]) // 1000 + 1} KB)" for x in have))

    # ------------------------------------------------------------ preview + save (every page)
    st.divider()
    text = wizard.to_yaml(d)
    v = wizard.validate_text(text, sop, paths.PIPELINES_DIR / d["name"] if (paths.PIPELINES_DIR / d["name"]).exists() else None)
    if v.ok:
        st.success("The configuration is valid.")
    for line in v.problems:
        st.error(line)
    for line in v.warnings:
        st.warning(line)
    with st.expander("YAML preview", expanded=False):
        st.code(text, language="yaml")
    exists = (paths.PIPELINES_DIR / d["name"] / "pipeline.yaml").exists()
    confirm = True
    if exists and mode != "edit":
        st.error(f"A pipeline named '{d['name']}' already exists: change the name.")
        confirm = False
    if mode == "edit":
        confirm = st.checkbox("I understand this replaces the saved pipeline.yaml (a backup is kept)", key="wz_ok_edit")
    if st.button("Save pipeline", type="primary", disabled=not (v.ok and confirm)):
        try:
            folder = wizard.write_pipeline(d["name"], text, sop, overwrite=(mode == "edit"))
            st.success(f"Saved to {folder}. It now appears under Pipelines and on Run Cycle.")
        except (ValueError, FileExistsError) as e:
            st.error(str(e))

# =================================================================== custom steps
else:
    st.caption("Custom steps are Python files in pipelines/<name>/steps/. They are trusted code (they run as you); the confirmation gate still applies to paid, LLM and write kinds.")
    c1, _ = st.columns([1, 4])
    if c1.button("Reload steps"):
        reload_custom_steps()
        st.rerun()
    errs = broken_steps()
    for key, msg in errs.items():
        st.error(f"**{key}** failed to load: {msg}")
    custom = [(k, v) for k, v in all_steps().items() if origin_of(k) != "builtin"]
    if custom:
        st.dataframe([{"step": k, "pipeline": origin_of(k), "kind": v.kind, "title": v.title} for k, v in custom], hide_index=True, use_container_width=True)
    elif not errs:
        st.info("No custom steps yet.")
    st.subheader("Create a custom step file")
    pls = [p.dir.name for p in load_all() if p.config]
    if pls:
        a, b, c = st.columns(3)
        pl = a.selectbox("Pipeline", pls)
        sid = b.text_input("Step id (lowercase slug)", "my_step")
        kind = c.selectbox("Kind", list(KINDS))
        if st.button("Create step file"):
            try:
                target = scaffold_step(pl, sid, kind)
                reload_custom_steps()
                st.success(f"Created {target}. Edit run() in that file, press Reload steps, then add the step in the pipeline wizard (step 5).")
            except (ValueError, FileExistsError) as e:
                st.error(str(e))
