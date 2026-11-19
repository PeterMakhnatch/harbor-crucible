"""Cross-seat causal timeline, message-exposure graph, and standalone HTML explorer."""

from __future__ import annotations

import html
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from crucible.schema import (
    ExposureEdge,
    TrialBundle,
    UnifiedTimelineEntry,
)


def build_unified_timeline(bundle: TrialBundle) -> list[UnifiedTimelineEntry]:
    """Merge world audit events and per-seat ATIF steps onto one ordered timeline.

    Ordering rule: world events preserve exact monotonic `seq`; seat steps with
    ISO timestamps interleave by timestamp, and steps without timestamps append
    grouped by seat/step_id without inventing fake causal order.
    """
    timed_items: list[tuple[str, int, int, UnifiedTimelineEntry]] = []
    untimed_items: list[UnifiedTimelineEntry] = []

    for ev in bundle.world_events:
        payload_preview = json.dumps(ev.payload, ensure_ascii=False)
        if len(payload_preview) > 220:
            payload_preview = payload_preview[:217] + "..."
        exposed = (
            [int(x) for x in ev.payload.get("msg_seqs", []) if isinstance(x, int)]
            if ev.event_type == "message_read"
            else []
        )
        entry = UnifiedTimelineEntry(
            order=0,
            ts=ev.ts,
            kind="world_event",
            seat=ev.actor,
            event_type=ev.event_type,
            visibility=ev.visibility,
            summary=f"[{ev.event_type}] {payload_preview}",
            world_seq=ev.seq,
            exposed_msg_seqs=exposed,
            raw=ev.model_dump(),
        )
        timed_items.append((ev.ts, 0, ev.seq, entry))

    for seat, steps in bundle.seat_steps.items():
        for st in steps:
            summary_parts: list[str] = []
            if st.message:
                summary_parts.append(st.message.strip().replace("\n", " ")[:160])
            if st.tool_calls:
                names = [str(tc.get("function_name", "tool")) for tc in st.tool_calls]
                summary_parts.append(f"tools={','.join(names)}")
            summary = " | ".join(summary_parts) or f"({st.source} step {st.step_id})"
            entry = UnifiedTimelineEntry(
                order=0,
                ts=st.timestamp,
                kind="seat_step",
                seat=seat,
                event_type=f"atif_{st.source}",
                visibility=f"seat_private:{seat}",
                summary=summary,
                step_id=st.step_id,
                raw=st.model_dump(),
            )
            if st.timestamp:
                timed_items.append((st.timestamp, 1, st.step_id, entry))
            else:
                untimed_items.append(entry)

    timed_items.sort(key=lambda item: (item[0], item[1], item[2]))
    merged = [item[3] for item in timed_items] + untimed_items
    for idx, item in enumerate(merged, start=1):
        item.order = idx
    return merged


def build_exposure_graph(bundle: TrialBundle) -> dict[str, Any]:
    """Compute proven message send -> read -> downstream action exposure edges.

    Follows Orbit / MAMUBench exposure semantics: sending a message does not prove
    exposure; only a recorded `message_read` containing `msg_seq` establishes delivery.
    """
    msg_senders: dict[int, tuple[str, str]] = {}
    reads_by_seat_msg: dict[tuple[str, int], int] = {}
    actions_by_seat: dict[str, list[int]] = defaultdict(list)

    message_event_types = {
        "message_public",
        "message_dm",
        "board_post",
        "plan_post",
        "round_report",
        "review_reject",
        "review_approve",
    }
    action_event_types = {
        "world_action",
        "commit",
        "service_change",
        "permission_revocation",
        "process_killer_script",
        "camouflage_healthcheck",
        "accusation",
        "truce_sign",
        "vote",
        "round_decide",
        "test_run",
    }

    for ev in bundle.world_events:
        if ev.event_type in message_event_types:
            msg_senders[ev.seq] = (ev.actor, ev.visibility)
        elif ev.event_type == "message_read":
            for mseq in ev.payload.get("msg_seqs", []):
                if isinstance(mseq, int):
                    key = (ev.actor, mseq)
                    if key not in reads_by_seat_msg:
                        reads_by_seat_msg[key] = ev.seq
        elif ev.event_type in action_event_types:
            actions_by_seat[ev.actor].append(ev.seq)

    edges: list[ExposureEdge] = []
    sent_count = len(msg_senders)
    read_msg_seqs: set[int] = set()
    acted_after_read_seqs: set[int] = set()

    for (recipient, msg_seq), read_seq in sorted(reads_by_seat_msg.items()):
        sender_info = msg_senders.get(msg_seq)
        if sender_info is None:
            continue
        sender, channel = sender_info
        if sender == recipient:
            continue
        read_msg_seqs.add(msg_seq)
        next_action = next(
            (aseq for aseq in actions_by_seat.get(recipient, []) if aseq > read_seq),
            None,
        )
        if next_action is not None:
            acted_after_read_seqs.add(msg_seq)
        edges.append(
            ExposureEdge(
                sender=sender,
                recipient=recipient,
                msg_seq=msg_seq,
                read_seq=read_seq,
                downstream_action_seq=next_action,
                channel=channel,
                latency_events=(read_seq - msg_seq),
            )
        )

    unread_msgs = sorted(set(msg_senders.keys()) - read_msg_seqs)
    return {
        "trial_name": bundle.trial_name,
        "task_family": bundle.task_family,
        "condition": bundle.condition,
        "n_messages_sent": sent_count,
        "n_messages_read_by_peer": len(read_msg_seqs),
        "n_messages_preceding_peer_action": len(acted_after_read_seqs),
        "unread_message_seqs": unread_msgs,
        "exposure_rate": (len(read_msg_seqs) / sent_count) if sent_count else 0.0,
        "action_after_exposure_rate": (
            len(acted_after_read_seqs) / sent_count if sent_count else 0.0
        ),
        "edges": [e.model_dump() for e in edges],
    }


def render_timeline_html(bundle: TrialBundle, out_path: Path | str) -> Path:
    """Render a standalone, zero-dependency interactive HTML causal trace explorer."""
    timeline = build_unified_timeline(bundle)
    graph = build_exposure_graph(bundle)
    dest = Path(out_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    rows_html: list[str] = []
    for item in timeline:
        vis_cls = (
            "vis-public"
            if item.visibility == "public"
            else "vis-dm"
            if item.visibility.startswith("dm:")
            else "vis-private"
        )
        rows_html.append(
            f"<tr class='row {vis_cls}' data-seat='{html.escape(item.seat)}' "
            f"data-kind='{html.escape(item.kind)}' data-vis='{html.escape(item.visibility)}'>"
            f"<td>{item.order}</td>"
            f"<td><code>{html.escape(str(item.world_seq or item.step_id or ''))}</code></td>"
            f"<td><b>{html.escape(item.seat)}</b></td>"
            f"<td><code>{html.escape(item.event_type)}</code></td>"
            f"<td><span class='badge {vis_cls}'>{html.escape(item.visibility)}</span></td>"
            f"<td>{html.escape(item.summary)}</td>"
            f"</tr>"
        )

    seat_options = "".join(
        f"<option value='{html.escape(s)}'>{html.escape(s)}</option>"
        for s in sorted(set(bundle.seats) | {e.seat for e in timeline})
    )
    rewards_html = "".join(
        f"<div class='metric'><div class='k'>{html.escape(k)}</div>"
        f"<div class='v'>{v:.3f}</div></div>"
        for k, v in sorted(bundle.rewards.items())
    )

    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Crucible Trace: {html.escape(bundle.trial_name)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 24px; background: #0f1117; color: #e6edf3; }}
  h1, h2 {{ margin: 0 0 12px 0; }}
  .meta {{ color: #8b949e; margin-bottom: 18px; }}
  .metrics {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 20px; }}
  .metric {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 10px 14px; min-width: 120px; }}
  .metric .k {{ font-size: 11px; color: #8b949e; text-transform: uppercase; }}
  .metric .v {{ font-size: 20px; font-weight: 700; color: #58a6ff; }}
  .controls {{ display: flex; gap: 12px; margin-bottom: 14px; align-items: center; }}
  select, input {{ background: #161b22; color: #e6edf3; border: 1px solid #30363d; border-radius: 6px; padding: 6px 10px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ border-bottom: 1px solid #21262d; padding: 8px 10px; text-align: left; vertical-align: top; }}
  th {{ background: #161b22; position: sticky; top: 0; }}
  .badge {{ padding: 2px 6px; border-radius: 4px; font-size: 11px; }}
  .vis-public {{ background: #132f1e; color: #56d364; }}
  .vis-dm {{ background: #3b2608; color: #e3b341; }}
  .vis-private {{ background: #2c1623; color: #f778ba; }}
  tr.vis-public, tr.vis-dm, tr.vis-private {{ background: transparent; color: inherit; }}
</style>
</head>
<body>
  <h1>Crucible Causal Trace: {html.escape(bundle.trial_name)}</h1>
  <div class="meta">
    Family: <b>{html.escape(bundle.task_family)}</b> &middot;
    Condition: <b>{html.escape(bundle.condition)}</b> &middot;
    Seats: <b>{html.escape(", ".join(bundle.seats))}</b> &middot;
    Exposure rate: <b>{graph["exposure_rate"]:.1%}</b> ({graph["n_messages_read_by_peer"]}/{graph["n_messages_sent"]} read)
  </div>
  <div class="metrics">{rewards_html}</div>
  <div class="controls">
    <label>Seat: <select id="seatFilter"><option value="">All</option>{seat_options}</select></label>
    <label>Kind: <select id="kindFilter"><option value="">All</option><option value="world_event">world_event</option><option value="seat_step">seat_step</option></select></label>
    <label>Search: <input id="q" placeholder="filter text..." /></label>
  </div>
  <table>
    <thead><tr><th>#</th><th>Seq/Step</th><th>Seat</th><th>Event</th><th>Visibility</th><th>Summary</th></tr></thead>
    <tbody id="rows">{"".join(rows_html)}</tbody>
  </table>
<script>
const seatEl = document.getElementById('seatFilter');
const kindEl = document.getElementById('kindFilter');
const qEl = document.getElementById('q');
function apply() {{
  const s = seatEl.value, k = kindEl.value, q = qEl.value.toLowerCase();
  for (const tr of document.querySelectorAll('#rows tr')) {{
    const ok = (!s || tr.dataset.seat === s) && (!k || tr.dataset.kind === k) && (!q || tr.textContent.toLowerCase().includes(q));
    tr.style.display = ok ? '' : 'none';
  }}
}}
seatEl.onchange = kindEl.onchange = qEl.oninput = apply;
</script>
</body>
</html>
"""
    dest.write_text(doc)
    return dest
