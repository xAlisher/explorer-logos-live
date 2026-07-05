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
    h, scanned, fresh = tip, 0, {}
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
                    ch = p.get("channel_id")
                    # first-seen walking tip→back is this channel's newest op in the range
                    if ch and ch not in fresh and p.get("inscription"):
                        fresh[ch] = {"inscription": p.get("inscription"),
                                     "parent": p.get("parent"),
                                     "signer": p.get("signer"),
                                     "slot": slot, "block": h}
        scanned += 1
        parent = hdr.get("parent_block")
        if not parent or parent == h:
            break
        h = parent
    channels = dict(old); channels.update(fresh)   # fresh (newer) overrides
    out = {"_meta": {"tip": tip, "tip_slot": tip_slot, "scanned_blocks": scanned,
                     "node": NODE, "channels": len(channels), "updated_this_run": len(fresh)},
           "channels": channels}
    json.dump(out, open(OUT, "w"), indent=0, sort_keys=True)
    print(f"scanned {scanned} new blocks → {len(fresh)} channels updated, {len(channels)} total (tip slot {tip_slot})")
    for ch, v in sorted(fresh.items(), key=lambda kv: -(kv[1]['slot'] or 0)):
        print(f"  updated {ch[:16]}… slot {v['slot']} inscription {len(v['inscription'] or '')//2}B")

if __name__ == "__main__":
    main()
