#!/usr/bin/env python3
"""
logos-live#14 — content-decode indexer for explorer.logos.live.

The node has no channel/op index (no block-by-slot, no /channel/{id}/messages;
/cryptarchia/headers is a fixed ~121-block window). So a browser can only reach
inscriptions within ~400 blocks of the tip before the walk gets too slow. This
script walks the parent_block chain, records each channel's most-recent
ChannelInscribe op (opcode 17), and writes a static channels.json the explorer
reads directly — instant, any depth, no per-visit walk.

INCREMENTAL: on re-run it walks only from the current tip down to the previously
indexed tip (stored in _meta.tip), merging new/updated channels over the old
index. First run (or no channels.json) walks up to max_blocks. Block hashes are
canonical, so the index is node-agnostic (Sneg-local and Paradox agree).

Usage:  NODE=http://127.0.0.1:8080 ./indexer.py [max_blocks]
"""
import urllib.request, json, sys, os

NODE = os.environ.get("NODE", "https://logos-testnet.paradox.computer").rstrip("/")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(HERE, "channels.json")

def get(path):
    req = urllib.request.Request(NODE + path,
                                 headers={"accept": "application/json",
                                          "User-Agent": "logos-live-indexer/1"})
    return json.load(urllib.request.urlopen(req, timeout=25))

def user_obj(insc_hex):
    """Decode a user inscription to its JSON object, or None. User inscriptions decode to
    JSON with our markers; LEZ sequencer ops are binary → skipped (keeps the index to real
    content and stops constant-churn commits from L2 sequencer channels)."""
    try:
        raw = bytes.fromhex(insc_hex).decode("utf-8")
        a, b = raw.find("{"), raw.rfind("}")
        if a < 0 or b <= a:
            return None
        obj = json.loads(raw[a:b + 1])
        if isinstance(obj, dict) and any(k in obj for k in ("type", "cid", "label", "files")):
            return obj
    except Exception:
        pass
    return None

def is_user_inscription(insc_hex):
    return user_obj(insc_hex) is not None

def insc_cid(insc_hex):
    """The per-inscription key = the payload's `cid` — that IS 'what was inscribed', and it is
    the field a per-item deep-link (#<channel>/<cid>, beacon#55) resolves against."""
    obj = user_obj(insc_hex)
    return (obj or {}).get("cid") or ""

def main():
    max_blocks = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    # load existing index → incremental frontier
    old, prev_tip = {}, None
    if os.path.exists(OUT):
        try:
            prev = json.load(open(OUT))
            old = prev.get("channels", {}) or {}
            prev_tip = (prev.get("_meta") or {}).get("tip")
        except Exception:
            pass
    info = get("/cryptarchia/info").get("cryptarchia_info", {})
    tip, tip_slot = info.get("tip"), info.get("slot")
    # fresh[ch]        = channel's NEWEST inscription (top-level, drives the #<channel> view)
    # fresh_bycid[ch]  = {cid → inscription} for EVERY inscription seen this run, so a per-item
    #                    deep-link (#<channel>/<cid>) resolves to the exact item, not just the tip.
    h, scanned, fresh, fresh_bycid = tip, 0, {}, {}
    while h and scanned < max_blocks:
        if prev_tip and h == prev_tip:          # reached already-indexed frontier
            break
        blk = get("/cryptarchia/blocks/" + h)
        hdr = blk.get("header", {}) or {}
        slot = hdr.get("slot")
        for tx in (blk.get("transactions") or []):
            for op in (((tx.get("mantle_tx") or {}).get("ops")) or []):
                if str(op.get("opcode")) == "17":
                    p = op.get("payload") or {}
                    ch, insc = p.get("channel_id"), p.get("inscription")
                    if not (ch and insc and is_user_inscription(insc)):
                        continue
                    # first-seen walking tip→back is this channel's newest op in the range
                    if ch not in fresh:
                        fresh[ch] = {"inscription": insc,
                                     "parent": p.get("parent"),
                                     "signer": p.get("signer"),
                                     "slot": slot, "block": h}
                    # record EVERY inscription, keyed by its cid (first-seen = newest per cid wins)
                    cid = insc_cid(insc)
                    if cid:
                        fresh_bycid.setdefault(ch, {}).setdefault(
                            cid, {"inscription": insc, "slot": slot, "block": h})
        scanned += 1
        parent = hdr.get("parent_block")
        if not parent or parent == h:
            break
        h = parent
    # Merge. fresh (newer) overrides the top-level newest inscription, but the per-cid
    # `inscriptions` map must ACCUMULATE across runs: a channel getting a new item must NOT
    # drop its previously-indexed items (they're usually older than this incremental run's
    # walk window, so they won't be re-seen — a plain overwrite would lose them and break
    # their deep-links). Carry the old map forward, then layer this run's finds on top.
    channels = {ch: dict(v) for ch, v in old.items()}
    for ch, v in fresh.items():
        carried = (channels.get(ch) or {}).get("inscriptions") or {}
        channels[ch] = dict(v)
        channels[ch]["inscriptions"] = dict(carried)
    # prune LEZ sequencer / non-user channels (constant churn, not content)
    channels = {ch: v for ch, v in channels.items() if is_user_inscription(v.get("inscription", ""))}
    for ch, v in channels.items():
        ins = dict(v.get("inscriptions") or {})
        # ensure the channel's newest (top-level) is always addressable — covers both legacy
        # entries (no map yet) and a just-updated channel whose new tip must be keyed too.
        cidN = insc_cid(v.get("inscription", ""))
        if cidN and cidN not in ins:
            ins[cidN] = {"inscription": v.get("inscription"),
                         "slot": v.get("slot"), "block": v.get("block")}
        ins.update(fresh_bycid.get(ch, {}))     # this run's finds (newest per cid wins)
        v["inscriptions"] = ins
    out = {"_meta": {"tip": tip, "tip_slot": tip_slot, "scanned_blocks": scanned,
                     "node": NODE, "channels": len(channels), "updated_this_run": len(fresh)},
           "channels": channels}
    json.dump(out, open(OUT, "w"), indent=0, sort_keys=True)
    print(f"scanned {scanned} new blocks → {len(fresh)} channels updated, {len(channels)} total (tip slot {tip_slot})")
    for ch, v in sorted(fresh.items(), key=lambda kv: -(kv[1]['slot'] or 0)):
        print(f"  updated {ch[:16]}… slot {v['slot']} inscription {len(v['inscription'] or '')//2}B")

if __name__ == "__main__":
    main()
