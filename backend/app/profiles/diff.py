"""Change-level diff between two profile versions, and partial acceptance.

Each change has a stable id so the profile-review view can accept or reject it on its own:
  basics.<field>                     scalar fields (name, headline, email, phone)
  <list>+<value> / <list>-<value>    string lists (skills, links, summary_facts, certifications)
  <section>:<id>                     whole role/project/education added or removed
  <section>:<id>.<field>             scalar field of a role/project/education edited
  <section>:<id>/<bullet_id>         bullet added, removed, or edited
  <section>:<id>.notes               education notes list edited
  preferences.<field>                preference edited
"""

from copy import deepcopy
from typing import Any, Literal, TypedDict

Op = Literal["add", "remove", "edit"]

BASICS = ("name", "headline", "email", "phone")
STRING_LISTS = ("skills", "links", "summary_facts", "certifications")
SECTIONS = ("roles", "projects", "education")


class Change(TypedDict):
    id: str
    section: str
    op: Op
    before: Any
    after: Any


def _index(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(i["id"]): i for i in items}


def diff_profiles(
    before: dict[str, Any] | None,
    after: dict[str, Any],
    prefs_before: dict[str, Any] | None = None,
    prefs_after: dict[str, Any] | None = None,
) -> list[Change]:
    b = before or {}
    out: list[Change] = []
    for f in BASICS:
        if b.get(f) != after.get(f):
            out.append(Change(id=f"basics.{f}", section="basics", op="edit",
                              before=b.get(f), after=after.get(f)))
    for lst in STRING_LISTS:
        old, new = [str(x) for x in b.get(lst, [])], [str(x) for x in after.get(lst, [])]
        out += [Change(id=f"{lst}+{v}", section=lst, op="add", before=None, after=v)
                for v in new if v not in old]
        out += [Change(id=f"{lst}-{v}", section=lst, op="remove", before=v, after=None)
                for v in old if v not in new]
    for sec in SECTIONS:
        old_items, new_items = _index(b.get(sec, [])), _index(after.get(sec, []))
        for item_id, item in new_items.items():
            if item_id not in old_items:
                out.append(Change(id=f"{sec}:{item_id}", section=sec, op="add",
                                  before=None, after=item))
                continue
            prev = old_items[item_id]
            for field in sorted(set(item) | set(prev)):
                if field in ("id", "bullets"):
                    continue
                if item.get(field) != prev.get(field):
                    out.append(Change(id=f"{sec}:{item_id}.{field}", section=sec, op="edit",
                                      before=prev.get(field), after=item.get(field)))
            ob, nb = _index(prev.get("bullets", [])), _index(item.get("bullets", []))
            for bid, bullet in nb.items():
                if bid not in ob:
                    out.append(Change(id=f"{sec}:{item_id}/{bid}", section=sec, op="add",
                                      before=None, after=bullet))
                elif ob[bid] != bullet:
                    out.append(Change(id=f"{sec}:{item_id}/{bid}", section=sec, op="edit",
                                      before=ob[bid], after=bullet))
            out += [Change(id=f"{sec}:{item_id}/{bid}", section=sec, op="remove",
                           before=bullet, after=None) for bid, bullet in ob.items() if bid not in nb]
        out += [Change(id=f"{sec}:{iid}", section=sec, op="remove", before=item, after=None)
                for iid, item in old_items.items() if iid not in new_items]
    if prefs_after is not None:
        pb = prefs_before or {}
        for field in sorted(set(pb) | set(prefs_after)):
            if pb.get(field) != prefs_after.get(field):
                out.append(Change(id=f"preferences.{field}", section="preferences", op="edit",
                                  before=pb.get(field), after=prefs_after.get(field)))
    return out


def _revert(profile: dict[str, Any], prefs: dict[str, Any] | None, ch: Change) -> None:
    cid, sec, op = ch["id"], ch["section"], ch["op"]
    if sec == "basics":
        profile[cid.split(".", 1)[1]] = ch["before"]
    elif sec in STRING_LISTS:
        items = profile.setdefault(sec, [])
        if op == "add":
            profile[sec] = [x for x in items if str(x) != ch["after"]]
        else:
            items.append(ch["before"])
    elif sec == "preferences":
        if prefs is not None:
            prefs[cid.split(".", 1)[1]] = ch["before"]
    else:
        items = profile.setdefault(sec, [])
        ref = cid.split(":", 1)[1]
        if "/" in ref:  # bullet-level
            item_id, bid = ref.split("/", 1)
            parent = next((i for i in items if str(i["id"]) == item_id), None)
            if parent is None:
                return
            bullets = parent.setdefault("bullets", [])
            if op == "add":
                parent["bullets"] = [x for x in bullets if x["id"] != bid]
            elif op == "remove":
                bullets.append(ch["before"])
            else:
                parent["bullets"] = [ch["before"] if x["id"] == bid else x for x in bullets]
        elif "." in ref:  # field-level edit
            item_id, field = ref.split(".", 1)
            for i in items:
                if str(i["id"]) == item_id:
                    i[field] = ch["before"]
        elif op == "add":
            profile[sec] = [i for i in items if str(i["id"]) != ref]
        else:
            items.append(ch["before"])


def apply_partial(
    proposed: dict[str, Any],
    proposed_prefs: dict[str, Any],
    changes: list[Change],
    rejected_ids: set[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The proposed profile with every rejected change reverted to its previous value."""
    profile, prefs = deepcopy(proposed), deepcopy(proposed_prefs)
    for ch in changes:
        if ch["id"] in rejected_ids:
            _revert(profile, prefs, ch)
    return profile, prefs
