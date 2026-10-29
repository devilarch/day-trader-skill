#!/usr/bin/env python3
"""Order tickets and the decision log for trader-broker (Zerodha Kite MCP). Standard library only.

This tool never talks to a broker and never places anything. It does its
work around the one moment that matters, your yes:

  show      renders each proposed order as a plain-English ticket plus the
            exact JSON Claude will send to Zerodha Kite MCP's place_order tool.
            A bracket order shows its stop-loss, take-profit and the max loss
            at the stop. An order is READY only if trader-risk passed THIS
            exact order today (matched by fingerprint) and nobody has decided
            on it yet.
  approve   records your explicit yes for ONE order, with your reply word for
            word. It refuses "yes to all", "sure", "ok", a yes that names a
            different stock or amount, and any order that is not READY.
  decline   records a no.
  result    records what happened after the Allow once / Deny card:
            placed (with the broker's order id), denied, or failed.
  fill      records a fill in trader/portfolio.json (cash and shares).
  flatten   builds a sell ticket that closes a symbol's open position by
            flat_by (default: 15:15 IST before broker RMS auto-square-off).
            It still goes through trader-risk and your yes.
  log       prints today's decisions.

    python3 ticket.py show                    # every order, READY or not
    python3 ticket.py show --index 1 --json   # one ticket as JSON
    python3 ticket.py approve --index 1 --reply "yes"
    python3 ticket.py result --index 1 --status placed --broker-id 2410280001...
    python3 ticket.py fill --symbol RELIANCE --side buy --qty 10 --price 2850.20
    python3 ticket.py flatten --symbol RELIANCE --qty 10
    python3 ticket.py log

Everything is written to trader/state/broker.json (append only). Dates and times
are Indian Standard Time (IST, UTC+05:30); --now "2026-10-28 09:45" pins the clock.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys

# Fields used for calculating order fingerprints
ORDER_FIELDS = ("symbol", "tradingsymbol", "exchange", "side", "transaction_type", "qty",
                "quantity", "type", "order_type", "product", "time_in_force", "validity",
                "limit_price", "price", "stop_price", "trigger_price", "order_class",
                "take_profit_limit_price", "stop_loss_stop_price", "stop_loss_limit_price")

YES_WORDS = ("yes", "y", "haan", "ha")
BATCH_WORDS = {"all", "every", "everything", "rest", "remaining", "them", "both", "batch", "each"}
DOUBT_WORDS = {"no", "not", "dont", "don't", "wait", "cancel", "stop", "but", "maybe", "later",
               "hold", "unless", "if", "nahi"}

IST_OFFSET_MINUTES = 330  # UTC+05:30 (Fixed, no Daylight Saving Time in India)


class TicketError(Exception):
    pass


# ---------------------------------------------------------------- time (IST)

def to_ist(utc):
    """UTC naive datetime -> IST naive datetime."""
    return utc.replace(tzinfo=None) + datetime.timedelta(minutes=IST_OFFSET_MINUTES)


def ist_to_utc(ist_dt):
    """IST naive datetime -> UTC naive datetime."""
    return ist_dt.replace(tzinfo=None) - datetime.timedelta(minutes=IST_OFFSET_MINUTES)


def parse_now(text):
    """ISO time -> naive UTC. A time without an offset is taken as IST."""
    if not text:
        return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    t = text.strip().replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(t)
    except ValueError:
        raise TicketError('--now wants a time like "2026-10-28 09:45" (IST) or ...Z (UTC)')
    if dt.tzinfo is None:
        return ist_to_utc(dt)
    return (dt - dt.utcoffset()).replace(tzinfo=None)


def ist_iso(now_utc):
    """naive UTC -> "2026-10-28T09:45:00+05:30" (IST wall clock with offset)."""
    return "%s+05:30" % to_ist(now_utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------- files

def read_json(path, what, required=True):
    if not path or not os.path.exists(path):
        if required:
            raise TicketError("no %s at %s" % (what, path))
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        raise TicketError("%s is not valid JSON: %s" % (path, e))


def write_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def rec_day(rec):
    """The trading day a decision belongs to: its "date", else the day of "at"."""
    return str(rec.get("date") or str(rec.get("at", ""))[:10])


# ---------------------------------------------------------------- the order & symbol parsing

def parse_indian_symbol(sym):
    """Parses symbol string to (exchange, tradingsymbol).
    Examples:
      'RELIANCE.NS' -> ('NSE', 'RELIANCE')
      'TCS.BO'      -> ('BSE', 'TCS')
      'NSE:INFY'    -> ('NSE', 'INFY')
      'NIFTY24OCT2424500CE' -> ('NFO', 'NIFTY24OCT2424500CE')
    """
    s = (sym or "").strip().upper()
    if s.startswith("NSE:"):
        return "NSE", s[4:]
    if s.startswith("BSE:"):
        return "BSE", s[4:]
    if s.startswith("NFO:"):
        return "NFO", s[4:]
    if s.endswith(".NS"):
        return "NSE", s[:-3]
    if s.endswith(".BO"):
        return "BSE", s[:-3]

    # Detect Indian derivatives / index options
    if any(s.endswith(sfx) for sfx in ("CE", "PE", "FUT")):
        if "SENSEX" in s or "BANKEX" in s:
            return "BFO", s
        return "NFO", s

    return "NSE", s


def fingerprint(order):
    """Identifies the exact order for risk checks and ticket verification."""
    core = {k: order[k] for k in ORDER_FIELDS if k in order and order[k] is not None}
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _str_num(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        f = float(v)
        return str(int(f)) if f == int(f) else repr(f)
    return str(v)


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def is_bracket(order):
    oc = str(order.get("order_class") or "").lower()
    legs = order.get("take_profit_limit_price") is not None or order.get("stop_loss_stop_price") is not None
    return oc == "bracket" or (not oc and legs)


def max_loss(order):
    """(rupees, stop) lost if the stop fills exactly at the stop, or (None, stop)."""
    stop = _f(order.get("stop_loss_stop_price")) or _f((order.get("plan") or {}).get("stop"))
    q = _f(order.get("qty") or order.get("quantity"))
    if not stop or not q:
        return None, stop
    plan = order.get("plan") or {}
    if str(order.get("type", "market")).lower() == "limit" and _f(order.get("limit_price") or order.get("price")):
        entry = _f(order.get("limit_price") or order.get("price"))
    elif _f(plan.get("max_loss")) is not None:
        return round(_f(plan["max_loss"]), 2), stop
    else:
        entry = _f(plan.get("entry"))
    if not entry:
        return None, stop
    risk = abs(entry - stop)
    return round(q * int(round(risk * 100)) / 100.0, 2), stop


def tool_input(order):
    """The exact arguments for Zerodha Kite MCP place_order:
      variety: 'regular'
      exchange: 'NSE' | 'BSE' | 'NFO' | 'BFO'
      tradingsymbol: symbol name without exchange suffix
      transaction_type: 'BUY' | 'SELL'
      quantity: integer quantity
      product: 'MIS' (intraday) | 'CNC' (delivery) | 'NRML'
      order_type: 'MARKET' | 'LIMIT' | 'SL' | 'SL-M'
      price: float (for LIMIT)
      trigger_price: float (for SL)
      validity: 'DAY'
      tag: 'daytrd'
    """
    raw_sym = str(order.get("symbol") or order.get("tradingsymbol") or "")
    exchange, tradingsymbol = parse_indian_symbol(raw_sym)
    side = str(order.get("side") or order.get("transaction_type") or "BUY").upper()
    qty = int(round(_f(order.get("qty") or order.get("quantity")) or 1))

    raw_type = str(order.get("type") or order.get("order_type") or "market").lower()
    if raw_type == "limit":
        order_type = "LIMIT"
    elif raw_type in ("stop", "sl"):
        order_type = "SL"
    elif raw_type in ("stop_market", "sl_m", "sl-m"):
        order_type = "SL-M"
    else:
        order_type = "MARKET"

    prod = str(order.get("product") or "MIS").upper()
    if prod in ("DELIVERY", "CNC", "CASH"):
        product = "CNC" if exchange in ("NSE", "BSE") else "NRML"
    else:
        product = "MIS"

    payload = {
        "variety": "regular",
        "exchange": exchange,
        "tradingsymbol": tradingsymbol,
        "transaction_type": side,
        "quantity": qty,
        "product": product,
        "order_type": order_type,
        "validity": "DAY",
        "tag": "daytrd"
    }

    if order_type in ("LIMIT", "SL"):
        limit_p = _f(order.get("limit_price") or order.get("price"))
        if limit_p is not None:
            payload["price"] = round(limit_p, 2)

    if order_type in ("SL", "SL-M"):
        trig_p = _f(order.get("trigger_price") or order.get("stop_price") or order.get("stop_loss_stop_price"))
        if trig_p is not None:
            payload["trigger_price"] = round(trig_p, 2)

    if is_bracket(order):
        sl = _f(order.get("stop_loss_stop_price") or order.get("stop_loss"))
        tp = _f(order.get("take_profit_limit_price") or order.get("take_profit"))
        if sl is not None or tp is not None:
            payload["bracket_targets"] = {}
            if sl is not None:
                payload["bracket_targets"]["stop_loss"] = round(sl, 2)
            if tp is not None:
                payload["bracket_targets"]["take_profit"] = round(tp, 2)

    return payload


def _money(v):
    f = float(v)
    s = "{:,.2f}".format(f)
    return "₹" + (s[:-3] if s.endswith(".00") else s)


def _p(v):
    return "%.2f" % float(v)


def plain_parts(order):
    """The ticket in plain words, one part per line."""
    side = str(order.get("side") or order.get("transaction_type") or "").upper()
    _, sym = parse_indian_symbol(order.get("symbol") or order.get("tradingsymbol") or "?")
    typ = str(order.get("type") or order.get("order_type") or "market").upper()
    tif = "MIS (intraday, square-off 15:15 IST)" if str(order.get("product", "MIS")).upper() == "MIS" else "CNC (delivery)"

    if is_bracket(order):
        limit_p = order.get("limit_price") or order.get("price")
        how = "limit %s" % _p(limit_p) if typ == "LIMIT" and limit_p else typ
        parts = ["%s %s %s, %s, %s" % (side, _str_num(order.get("qty") or order.get("quantity")), sym, how, tif)]
        if order.get("stop_loss_stop_price") is not None:
            leg = "stop-loss %s" % _p(order["stop_loss_stop_price"])
            if order.get("stop_loss_limit_price") is not None:
                leg += " (limit %s)" % _p(order["stop_loss_limit_price"])
            parts.append(leg)
        if order.get("take_profit_limit_price") is not None:
            parts.append("take-profit %s" % _p(order["take_profit_limit_price"]))
        loss, stop = max_loss(order)
        if loss is not None:
            parts.append("max loss about %s if the stop fills at %s (can fill worse on gaps/fast market)"
                         % (_money(loss), _p(stop)))
        return parts

    q = _str_num(order.get("qty") or order.get("quantity"))
    what = "%s share%s of %s" % (q, "" if q == "1" else "s", sym)
    if typ == "LIMIT":
        how = "limit order at %s" % _money(order.get("limit_price") or order.get("price"))
    elif typ in ("STOP", "SL"):
        how = "SL order at trigger %s" % _money(order.get("trigger_price") or order.get("stop_price"))
    else:
        how = "%s order" % typ.replace("_", " ")
    return ["%s %s, %s, %s" % (side, what, how, tif)]


def plain(order):
    return " / ".join(plain_parts(order))


def amount_numbers(order):
    nums = []
    for k in ("notional", "qty", "quantity", "limit_price", "price", "stop_loss_stop_price",
              "take_profit_limit_price", "stop_loss_limit_price", "trigger_price", "stop_price"):
        if order.get(k) is not None:
            v = _f(order[k])
            if v is not None:
                nums.append(v)
    loss, _ = max_loss(order)
    if loss is not None:
        nums.append(loss)
    return nums


def parse_yes(reply, order, batch_symbols=()):
    """Is this reply an explicit yes for THIS one order? Returns (ok, why)."""
    raw = (reply or "").strip()
    if not raw:
        return False, "the reply is empty"
    if "?" in raw:
        return False, "the reply is a question, not a yes"
    words = re.findall(r"[a-z']+", raw.lower())
    if not words or words[0] not in YES_WORDS:
        return False, "only a reply that starts with \"yes\" counts (not ok, sure, go, do it)"
    if BATCH_WORDS & set(words):
        return False, "a yes covers one order at a time, not a batch"
    if DOUBT_WORDS & set(words[1:]):
        return False, "the reply has a condition or a doubt in it; ask again"
    _, sym = parse_indian_symbol(order.get("symbol") or order.get("tradingsymbol") or "")
    tokens = set(re.findall(r"[A-Z][A-Z0-9.\-]{0,20}", raw.upper()))
    others = {parse_indian_symbol(s)[1] for s in batch_symbols} - {sym}
    named = tokens & others
    if named:
        return False, "the reply names %s, but this order is for %s" % (", ".join(sorted(named)), sym)
    nums = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", raw)]
    if nums:
        want = amount_numbers(order)
        if not any(abs(n - w) < 0.05 for n in nums for w in want):
            return False, "the reply says %s, but this order is %s" % (
                ", ".join(_str_num(n) for n in nums), plain(order))
    return True, "explicit yes for %s" % plain(order)


# ---------------------------------------------------------------- state

def load_state(path):
    return read_json(path, "broker state", required=False) or {"orders": []}


def latest(state, fp, today):
    """The latest decision recorded today for this fingerprint, or None."""
    found = None
    for rec in state.get("orders", []):
        if rec.get("fingerprint") == fp and rec_day(rec) == today:
            found = rec
    return found


def risk_verdict(risk, fp, today):
    if not risk:
        return None, "trader-risk has not checked these orders (run check.py)"
    if risk.get("date") != today:
        return None, "the risk check is from %s, not today; run check.py again" % risk.get("date")
    for r in risk.get("results", []):
        if r.get("fingerprint") == fp:
            return r, None
    return None, "this exact order was not in the last risk check (it changed or is new); run check.py again"


def status_of(order, risk, state, today):
    """(ready, label, risk_result)"""
    fp = fingerprint(order)
    rv, why = risk_verdict(risk, fp, today)
    if rv is None:
        return False, "NOT READY: " + why, None
    if rv.get("verdict") != "PASS":
        return False, "BLOCKED by trader-risk: " + "; ".join(rv.get("reasons", [])), rv
    rec = latest(state, fp, today)
    if rec:
        st = rec.get("status")
        if st == "approved":
            return False, "APPROVED by you at %s, waiting for Zerodha place_order call" % rec.get("at"), rv
        return False, "DONE: %s at %s" % (st, rec.get("at")), rv
    return True, "READY: trader-risk PASS, waiting for your yes", rv


def kind_of(order, rv):
    if rv and rv.get("kind"):
        return rv["kind"]
    return "entry" if str(order.get("side") or order.get("transaction_type") or "").lower() == "buy" else "exit"


# ---------------------------------------------------------------- rendering

def render(order, idx, total, cfg, risk, state, today):
    ready, label, rv = status_of(order, risk, state, today)
    paper = cfg.get("paper", True)
    acct = "PAPER account" if paper else "LIVE ACCOUNT, REAL MONEY"
    lines = ["ORDER %d of %d, %s, Zerodha Kite" % (idx, total, acct)]
    for part in plain_parts(order):
        lines.append("  " + part)
    if order.get("why"):
        lines.append("  why: " + order["why"])
    lines.append("  " + label)
    for w in (rv or {}).get("warnings", []):
        lines.append("  note: " + w)

    lines.append("  Claude will call Zerodha MCP place_order with exactly:")
    for l in json.dumps(tool_input(order), indent=2).splitlines():
        lines.append("    " + l)
    if is_bracket(order):
        lines.append("  Zerodha places the entry as an MIS order, and logs stop-loss and take-profit targets.")
        lines.append("  (Broker RMS auto square-off occurs at 15:15 IST).")
    if ready:
        lines.append("  Reply \"yes\" to place this one order, or \"no\" to skip it.")
        lines.append("  Claude's own card then asks again: Allow once places it, Deny stops it.")
    return "\n".join(lines), ready


def ticket_json(order, idx, cfg, risk, state, today):
    ready, label, rv = status_of(order, risk, state, today)
    loss, stop = max_loss(order)
    return {
        "index": idx,
        "ready": ready,
        "status": label,
        "plain": plain(order),
        "fingerprint": fingerprint(order),
        "paper": bool(cfg.get("paper", True)),
        "broker": "zerodha",
        "tool": "place_order",
        "tool_input": tool_input(order),
        "why": order.get("why", ""),
        "bracket": is_bracket(order),
        "max_loss": loss,
        "stop": stop
    }


# ---------------------------------------------------------------- fills -> portfolio

def apply_fill(portfolio_path, cfg, symbol, side, qty, price, date):
    """Record a filled order in trader/portfolio.json: cash and shares."""
    pf = read_json(portfolio_path, "portfolio", required=False)
    if pf is None:
        budget = cfg.get("budget")
        if not budget:
            raise TicketError("no %s yet and no budget in the config to start it from" % portfolio_path)
        pf = {"cash": float(budget), "currency": "INR", "positions": []}
    _, symbol = parse_indian_symbol(symbol)
    qty, price = float(qty), float(price)
    if qty <= 0 or price <= 0:
        raise TicketError("a fill needs a positive qty and price")
    cost = round(qty * price, 2)
    pos = None
    for p in pf.setdefault("positions", []):
        if str(p.get("ticker", "")).upper() == symbol:
            pos = p
    if side.lower() == "buy":
        if pos is None:
            pos = {"ticker": symbol, "shares": 0.0, "lots": []}
            pf["positions"].append(pos)
        lots = pos.setdefault("lots", [])
        lots.append({"id": "%s-%d" % (symbol, len(lots) + 1), "date": date, "shares": qty, "cost": cost})
        pos["shares"] = round(float(pos.get("shares", 0)) + qty, 6)
        pf["cash"] = round(float(pf.get("cash", 0)) - cost, 2)
    else:
        if pos is None or float(pos.get("shares", 0)) + 1e-9 < qty:
            raise TicketError("cannot record selling %s %s: the portfolio holds %s"
                              % (_str_num(qty), symbol, pos.get("shares", 0) if pos else 0))
        left = qty
        for lot in sorted(pos.get("lots", []), key=lambda l: l.get("date", "")):
            if left <= 1e-9:
                break
            take = min(left, float(lot["shares"]))
            per = float(lot["cost"]) / float(lot["shares"]) if float(lot["shares"]) else 0
            lot["cost"] = round(float(lot["cost"]) - per * take, 2)
            lot["shares"] = round(float(lot["shares"]) - take, 6)
            left -= take
        pos["lots"] = [l for l in pos.get("lots", []) if float(l["shares"]) > 1e-9]
        pos["shares"] = round(float(pos["shares"]) - qty, 6)
        if pos["shares"] <= 1e-9:
            pf["positions"].remove(pos)
        pf["cash"] = round(float(pf.get("cash", 0)) + cost, 2)
    write_json(portfolio_path, pf)
    return pf


def log_fill(state_path, now, today, symbol, side, qty, price):
    """A fill in the log, so trader-risk can count day trades."""
    state = load_state(state_path)
    _, sym = parse_indian_symbol(symbol)
    state.setdefault("orders", []).append({
        "at": ist_iso(now), "date": today, "status": "filled", "symbol": sym, "side": side.lower(),
        "qty": _str_num(float(qty)), "price": float(price),
        "plain": "%s %s %s at %s" % (side.upper(), _str_num(float(qty)), sym, _p(price))})
    write_json(state_path, state)


# ---------------------------------------------------------------- commands

def _clock(a):
    now = parse_now(getattr(a, "now", None))
    today = getattr(a, "today", None) or to_ist(now).date().isoformat()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", today):
        raise TicketError("--today wants a date like 2026-10-28")
    return now, today


def _load(a):
    doc = read_json(a.orders, "orders file (run trader-budget, or ticket.py flatten, first)")
    orders = doc.get("orders", doc) if isinstance(doc, dict) else doc
    if not isinstance(orders, list) or not orders:
        raise TicketError("no orders in %s" % a.orders)
    cfg = read_json(a.config, "config", required=False) or {}
    risk = read_json(a.risk, "risk check", required=False)
    state = load_state(a.state)
    now, today = _clock(a)
    return orders, cfg, risk, state, today, now


def _pick(orders, index):
    if index is None:
        raise TicketError("say which order: --index N")
    if not 1 <= index <= len(orders):
        raise TicketError("there is no order %d (there are %d)" % (index, len(orders)))
    return orders[index - 1]


def cmd_show(a):
    orders, cfg, risk, state, today, now = _load(a)
    picks = [(a.index, _pick(orders, a.index))] if a.index else list(enumerate(orders, 1))
    if a.json:
        out = [ticket_json(o, i, cfg, risk, state, today) for i, o in picks]
        print(json.dumps(out[0] if a.index else out, indent=2))
        return 0 if any(t["ready"] for t in out) else 1
    blocks, any_ready = [], False
    for i, o in picks:
        text, ready = render(o, i, len(orders), cfg, risk, state, today)
        blocks.append(text)
        any_ready = any_ready or ready
    print("\n\n".join(blocks))
    print("\nOne order at a time: a yes covers one ticket, never the batch. Education and tooling, "
          "not financial advice.")
    return 0 if any_ready else 1


def cmd_approve(a):
    orders, cfg, risk, state, today, now = _load(a)
    order = _pick(orders, a.index)
    ready, label, rv = status_of(order, risk, state, today)
    if not ready:
        raise TicketError("order %d is not ready: %s" % (a.index, label))
    ok, why = parse_yes(a.reply, order, [o.get("symbol") or o.get("tradingsymbol", "") for o in orders])
    if not ok:
        print("Not recorded: %s. Ask the user again with the ticket for order %d." % (why, a.index))
        return 1
    loss, stop = max_loss(order)
    _, sym = parse_indian_symbol(order.get("symbol") or order.get("tradingsymbol", ""))
    rec = {"at": ist_iso(now), "date": today, "index": a.index, "fingerprint": fingerprint(order),
           "symbol": sym, "side": order.get("side") or order.get("transaction_type"),
           "qty": order.get("qty") or order.get("quantity"), "kind": kind_of(order, rv), "max_loss": loss, "stop": stop,
           "plain": plain(order), "status": "approved", "reply": a.reply,
           "paper": bool(cfg.get("paper", True)), "broker": "zerodha"}
    state.setdefault("orders", []).append(rec)
    write_json(a.state, state)
    print("Recorded your yes for order %d: %s." % (a.index, plain(order)))
    print("Now call Zerodha MCP place_order with exactly:")
    print(json.dumps(tool_input(order), indent=2))
    print("Claude's card shows Allow once / Deny. Then: ticket.py result --index %d --status "
          "placed|denied|failed" % a.index)
    return 0


def cmd_decline(a):
    orders, cfg, risk, state, today, now = _load(a)
    order = _pick(orders, a.index)
    _, sym = parse_indian_symbol(order.get("symbol") or order.get("tradingsymbol", ""))
    rec = {"at": ist_iso(now), "date": today, "index": a.index, "fingerprint": fingerprint(order),
           "symbol": sym, "side": order.get("side") or order.get("transaction_type"),
           "plain": plain(order), "status": "declined", "reply": a.reply or "no"}
    state.setdefault("orders", []).append(rec)
    write_json(a.state, state)
    print("Recorded: you said no to order %d (%s). Nothing was sent." % (a.index, plain(order)))
    return 0


def cmd_result(a):
    orders, cfg, risk, state, today, now = _load(a)
    order = _pick(orders, a.index)
    fp = fingerprint(order)
    rec = latest(state, fp, today)
    if not rec or rec.get("status") != "approved":
        raise TicketError("order %d has no yes recorded today; a result can only follow an approval" % a.index)
    new = {"at": ist_iso(now), "date": today, "index": a.index, "fingerprint": fp, "symbol": rec["symbol"],
           "side": rec["side"], "plain": rec["plain"], "status": a.status}
    for k in ("qty", "kind", "max_loss", "stop"):
        if rec.get(k) is not None:
            new[k] = rec[k]
    if a.broker_id:
        new["broker_order_id"] = a.broker_id
    if a.note:
        new["note"] = a.note
    state["orders"].append(new)
    write_json(a.state, state)
    print("Recorded order %d as %s." % (a.index, a.status))
    if a.status == "placed" and a.filled_qty and a.filled_price:
        apply_fill(a.portfolio, cfg, rec["symbol"], rec["side"], a.filled_qty, a.filled_price, today)
        log_fill(a.state, now, today, rec["symbol"], rec["side"], a.filled_qty, a.filled_price)
        print("Added the fill to %s." % a.portfolio)
    elif a.status == "placed":
        print("When it fills, record it: ticket.py fill --symbol %s --side %s --qty Q --price P"
              % (rec["symbol"], rec["side"]))
        if rec.get("kind") == "entry" and is_bracket(order):
            print("When the stop-loss or take-profit fills, record that sell the same way.")
    return 0


def cmd_fill(a):
    cfg = read_json(a.config, "config", required=False) or {}
    now = parse_now(a.now)
    date = a.date or to_ist(now).date().isoformat()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise TicketError("--date wants a date like 2026-10-28")
    _, sym = parse_indian_symbol(a.symbol)
    pf = apply_fill(a.portfolio, cfg, sym, a.side, a.qty, a.price, date)
    log_fill(a.state, now, date, sym, a.side, a.qty, a.price)
    print("Recorded %s %s %s at %s on %s in %s. Cash now %s." % (a.side.upper(), a.qty, sym,
                                                                _money(a.price), date, a.portfolio,
                                                                _money(pf["cash"])))
    return 0


def cmd_flatten(a):
    cfg = read_json(a.config, "config", required=False) or {}
    _, sym = parse_indian_symbol(a.symbol)
    now, today = _clock(a)
    source = "Zerodha get_positions"
    if a.qty is not None:
        qty = _f(a.qty)
        if qty is None or qty <= 0:
            raise TicketError("--qty wants the number of shares you hold, like --qty 10")
    else:
        pf = read_json(a.portfolio, "portfolio", required=False) or {}
        qty = sum(_f(p.get("shares", p.get("qty"))) or 0 for p in pf.get("positions", [])
                  if parse_indian_symbol(p.get("ticker") or p.get("symbol") or "")[1] == sym)
        source = a.portfolio
        if qty <= 1e-9:
            raise TicketError("nothing to flatten: no %s shares in %s. Check Zerodha get_positions "
                              "and pass --qty if you do hold some" % (sym, a.portfolio))
    plan = read_json(a.plan, "plan", required=False) or {}
    flat_by = (plan.get("flat_by") if parse_indian_symbol(plan.get("symbol", ""))[1] == sym else None) \
        or cfg.get("flat_by") or "15:15"
    order = {"symbol": sym, "side": "sell", "qty": int(round(qty)), "type": "market", "time_in_force": "day",
             "product": "MIS",
             "why": "flat by %s IST: closes %s intraday position before broker square-off (qty from %s)"
             % (flat_by, sym, source)}
    old = read_json(a.orders, "orders", required=False)
    replaced = len(old.get("orders", [])) if isinstance(old, dict) else 0
    doc = {"created_by": "trader-broker", "created_at": ist_iso(now), "status": "proposed",
           "paper": bool(cfg.get("paper", True)),
           "note": "Flatten ticket. Nothing is placed until trader-risk passes it and you say yes in the chat.",
           "source": "ticket.py flatten %s on %s" % (sym, today), "orders": [order]}
    write_json(a.orders, doc)
    print("Flatten %s: %s (flat by %s IST)." % (sym, plain(order), flat_by))
    print("Wrote it to %s%s." % (a.orders, (" (it replaced %d earlier proposal%s)"
                                             % (replaced, "" if replaced == 1 else "s")) if replaced else ""))
    if a.qty is None:
        print("The qty comes from %s. Check it against Zerodha get_positions before executing." % source)
    print("Next:")
    print("  1. trader-risk: check.py (a sell that only closes what you hold is never blocked).")
    print("  2. ticket.py show, then the user's explicit yes.")
    print("  3. Call Zerodha place_order tool with the generated ticket.")
    return 0


def cmd_log(a):
    state = load_state(a.state)
    now, today = _clock(a)
    rows = [r for r in state.get("orders", []) if a.all or rec_day(r) == today]
    if not rows:
        print("No decisions recorded%s." % ("" if a.all else " today"))
        return 1
    for r in rows:
        extra = (" id " + r["broker_order_id"]) if r.get("broker_order_id") else ""
        reply = (' reply "%s"' % r["reply"]) if r.get("reply") and r["status"] in ("approved", "declined") else ""
        loss = (" max loss %s" % _money(r["max_loss"])) if r.get("max_loss") is not None and r["status"] == "placed" else ""
        idx = ("#%s" % r["index"]) if r.get("index") is not None else "  "
        print("%s  %s %-9s %s%s%s%s" % (r.get("at"), idx, r.get("status"), r.get("plain"), reply, loss, extra))
    placed = sum(1 for r in rows if r.get("status") == "placed")
    print("%d placed%s." % (placed, "" if a.all else " today"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Order tickets and your yes (Zerodha Kite MCP). Never places orders.")
    sub = ap.add_subparsers(dest="cmd")

    def clock(p):
        p.add_argument("--now", help='pretend it is this IST time, e.g. "2026-10-28 09:45"')
        p.add_argument("--today", help="YYYY-MM-DD (default: today in IST)")

    def common(p):
        p.add_argument("--orders", default="trader/orders.json")
        p.add_argument("--config", default="trader/config.json")
        p.add_argument("--risk", default="trader/state/risk.json")
        p.add_argument("--state", default="trader/state/broker.json")
        clock(p)

    p_show = sub.add_parser("show", help="render the tickets, READY or not")
    common(p_show)
    p_show.add_argument("--index", type=int, help="one order only (1-based)")
    p_show.add_argument("--json", action="store_true", help="output as machine-readable JSON")

    p_app = sub.add_parser("approve", help="record the user's explicit yes for one order")
    common(p_app)
    p_app.add_argument("--index", type=int, required=True, help="which order (1-based)")
    p_app.add_argument("--reply", required=True, help="the user's exact chat reply")

    p_dec = sub.add_parser("decline", help="record a no for one order")
    common(p_dec)
    p_dec.add_argument("--index", type=int, required=True, help="which order (1-based)")
    p_dec.add_argument("--reply", help="the user's reply")

    p_res = sub.add_parser("result", help="record what happened with Zerodha Kite")
    common(p_res)
    p_res.add_argument("--index", type=int, required=True, help="which order (1-based)")
    p_res.add_argument("--status", required=True, choices=["placed", "denied", "failed"])
    p_res.add_argument("--broker-id", help="Zerodha order_id returned")
    p_res.add_argument("--filled-qty", help="shares filled")
    p_res.add_argument("--filled-price", help="fill price")
    p_res.add_argument("--note", help="optional note")
    p_res.add_argument("--portfolio", default="trader/portfolio.json")

    p_fill = sub.add_parser("fill", help="record a fill directly in trader/portfolio.json")
    p_fill.add_argument("--symbol", required=True, help="trading symbol (e.g. RELIANCE)")
    p_fill.add_argument("--side", required=True, choices=["buy", "sell"])
    p_fill.add_argument("--qty", required=True, help="shares")
    p_fill.add_argument("--price", required=True, help="price per share in ₹")
    p_fill.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p_fill.add_argument("--portfolio", default="trader/portfolio.json")
    p_fill.add_argument("--config", default="trader/config.json")
    p_fill.add_argument("--state", default="trader/state/broker.json")
    clock(p_fill)

    p_flat = sub.add_parser("flatten", help="build a sell ticket that closes an open position")
    common(p_flat)
    p_flat.add_argument("--symbol", required=True, help="symbol to close")
    p_flat.add_argument("--qty", help="shares (default: what trader/portfolio.json holds)")
    p_flat.add_argument("--portfolio", default="trader/portfolio.json")
    p_flat.add_argument("--plan", default="trader/plan.json")

    p_log = sub.add_parser("log", help="print today's decision log")
    p_log.add_argument("--state", default="trader/state/broker.json")
    p_log.add_argument("--all", action="store_true", help="all days, not just today")
    clock(p_log)

    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 2

    cmds = {
        "show": cmd_show,
        "approve": cmd_approve,
        "decline": cmd_decline,
        "result": cmd_result,
        "fill": cmd_fill,
        "flatten": cmd_flatten,
        "log": cmd_log,
    }
    try:
        return cmds[a.cmd](a)
    except TicketError as e:
        print("ticket.py error: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
