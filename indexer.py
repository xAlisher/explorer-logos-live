#!/usr/bin/env python3
"""
logos-live#14 — content-decode indexer for explorer.logos.live.

The node has no channel/op index (no block-by-slot, no /channel/{id}/messages;
/cryptarchia/headers is a fixed ~121-block window). So a browser can only reach
inscriptions within ~400 blocks of the tip before the walk gets too slow. This
script walks the parent_block chain once, records each channel's most-recent
ChannelInscribe op (opcode 17), and writes a static channels.json the explorer
reads directly — instant, any depth, no per-visit walk.

Usage:  NODE=http://100.108.127.3:8080 ./indexer.py [max_blocks]
Re-run (e.g. cron) to pick up new inscriptions; it always walks from the tip.
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
    max_blocks = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    info = get("/cryptarchia/info").get("cryptarchia_info", {})
    h = info.get("tip")
    tip_slot = info.get("slot")
    channels, scanned = {}, 0
    while h and scanned < max_blocks:
        blk = get("/cryptarchia/blocks/" + h)
        hdr = blk.get("header", {}) or {}
        slot = hdr.get("slot")
        for tx in (blk.get("transactions") or []):
            for op in (((tx.get("mantle_tx") or {}).get("ops")) or []):
                if str(op.get("opcode")) == "17":
                    p = op.get("payload") or {}
                    ch = p.get("channel_id")
                    # keep the most-recent op per channel (first seen walking tip→back)
                    if ch and ch not in channels and p.get("inscription"):
                        channels[ch] = {"inscription": p.get("inscription"),
                                        "parent": p.get("parent"),
                                        "signer": p.get("signer"),
                                        "slot": slot, "block": h}
        scanned += 1
        parent = hdr.get("parent_block")
        if not parent or parent == h:
            break
        h = parent
    out = {"_meta": {"tip": info.get("tip"), "tip_slot": tip_slot,
                     "scanned_blocks": scanned, "node": NODE,
                     "channels": len(channels)},
           "channels": channels}
    json.dump(out, open(OUT, "w"), indent=0, sort_keys=True)
    print(f"indexed {len(channels)} channels over {scanned} blocks (tip slot {tip_slot}) → {OUT}")
    for ch, v in sorted(channels.items(), key=lambda kv: -(kv[1]['slot'] or 0)):
        n = len(v["inscription"] or "") // 2
        print(f"  {ch[:16]}… slot {v['slot']} inscription {n}B")

if __name__ == "__main__":
    main()
