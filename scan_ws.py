#scan_ws.py 

import os
import asyncio
import time, random
import logging
from decimal import Decimal, InvalidOperation
from termcolor import colored
from paradex_py.environment import PROD
from paradex_py.common.console_logging import console_logger
from paradex_py.api.ws_client import ParadexWebsocketChannel
from paradex_py import ParadexSubkey

from dotenv import load_dotenv
load_dotenv()

L2_SUBKEY = os.getenv("L2_SUBKEY")
L2_ADDRESS = os.getenv("L2_ADDRESS")

logger = console_logger


# Keep YOUR prints, quiet down libs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)
# paradex_py still emits ERROR lines; set to CRITICAL to hide those too (demo mode)
logging.getLogger("paradex_py").setLevel(logging.CRITICAL)
logger.info("Simple PERP BBO Feed Starting...")

paradex = ParadexSubkey(
    env=PROD,
    l2_private_key=L2_SUBKEY,
    l2_address=L2_ADDRESS,
    logger=logger,
)

print("[INIT] ParadexSubkey initialized.")
#print("SDK Derived L2:", hex(paradex.account.l2_address))

# === TUNABLES (READABILITY) ===
PRINT_EVERY_SEC = 7.0         # slower so you can actually read
MAX_ROWS = 250                # fewer lines per refresh
STALE_SEC = 20.0              # hide markets that haven't updated recently
CLEAR_SCREEN = True           # set False if you prefer scrolling logs
ORDER_MODE = "random"         # "random" or "funding" ---> (abs_funding = biggest |funding| first) 

SHOW_ONLY_PERPS = True        # True = only *-PERP

def unwrap_ws_message(message: dict):
    """
    Paradex WS subscription payloads typically:
      {"jsonrpc":"2.0","method":"subscription","params":{"channel":"bbo.BTC-USD-PERP","data":{...}}}
    Returns (channel_str, data_dict).
    """
    if not isinstance(message, dict):
        return "unknown", {}

    params = message.get("params") or {}
    if isinstance(params, dict) and "data" in params:
        channel = params.get("channel") or message.get("channel") or "unknown"
        data = params.get("data") or {}
        return channel, data if isinstance(data, dict) else {}

    channel = message.get("channel") or "unknown"
    data = message.get("data") or {}
    return channel, data if isinstance(data, dict) else {}

def to_decimal(x):
    if x is None:
        return None
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None

def fmt_dec(x: Decimal, places=2):
    if x is None:
        return "None"
    q = Decimal(10) ** -places
    try:
        return str(x.quantize(q))
    except Exception:
        return str(x)

def price_dp(px: Decimal) -> int:
    """
    Dynamic decimal places so low-priced markets don't print as $0.00.
    """
    if px is None:
        return 1
    if px >= Decimal("1000"):
        return 1
    if px >= Decimal("1"):
        return 2
    if px >= Decimal("0.1"):
        return 3
    if px >= Decimal("0.01"):
        return 3
    return 3

def funding_to_pct_str(fr: Decimal):
    """
    Funding sometimes arrives as fraction (0.000085 => 0.0085%)
    Sometimes already as percent.
    We'll assume:
      abs(fr) <= 1 => fraction -> *100
      abs(fr) > 1  => already percent
    """
    if fr is None:
        return "None", None

    ax = abs(fr)
    pct = (fr * Decimal("100")) if ax <= 1 else fr
    # Return both string and numeric pct for coloring
    try:
        return f"{pct:.3f}%", pct
    except Exception:
        return f"{pct}%", pct

def display_channel(ch: str) -> str:
    if not ch:
        return "unknown"
    chl = ch.lower()

    if chl.startswith("bbo."):
        sym = ch.split(".", 1)[1]  # e.g. "ETH-USD-PERP"
        if sym.endswith("-PERP") and "-USD-" in sym:
            base = sym.split("-", 1)[0]  # "ETH"
            return f"bbo.{base}-PERP"
        return f"bbo.{sym}"

    if "markets_summary" in chl:
        return "markets_summary"

    return ch

def color_channel(ch: str):
    chl = (ch or "").lower()
    if chl.startswith("bbo."):
        return colored(ch, "cyan")
    if "markets_summary" in chl:
        return colored(ch, "magenta")
    if chl.startswith("trades."):
        return colored(ch, "yellow")
    if "funding" in chl:
        return colored(ch, "blue")
    return colored(ch, "white")

def color_market(mkt: str):
    # You can tweak these if you want categories
    return colored(mkt, "cyan")

def color_funding(pct: Decimal, text: str):
    
    if pct is None:
        return colored(text, "white")

    near = Decimal("0.0020")    # 0.0020% ~ "near zero"
    strong = Decimal("0.0500")  # 0.05% = strong signal (either direction)

    ap = abs(pct)
    if ap < near:
        return colored(text, "yellow")

    if pct < 0:
        return colored(text, "red")
    else:
        return colored(text, "green")

async def main():
    logger.info("PERP WS Scanner starting...")

    # Discover markets via REST so "ALL markets" is not hardcoded
    logger.info("Fetching markets list via REST...")
    mkts = paradex.api_client.fetch_markets()
    symbols = []
    for m in mkts.get("results", []):
        sym = m.get("symbol")
        if not sym:
            continue
        if SHOW_ONLY_PERPS:
            if sym.endswith("-PERP"):
                symbols.append(sym)
        else:
            symbols.append(sym)

    symbols = sorted(set(symbols))
    if not symbols:
        raise RuntimeError("No markets found from fetch_markets()")

    print(colored(f"[INIT] discovered {len(symbols)} markets (PERPs={SHOW_ONLY_PERPS})", "green"))

    # Cache latest per market
    state = {
        sym: {
            "bid": None,
            "ask": None,
            "bbo_ts": 0.0,
            "mark": None,
            "funding": None,      # raw decimal from WS
            "summary_ts": 0.0,
            "last_channel": None,
        }
        for sym in symbols
    }

    last_msg_ts = time.time()

    def pick_market(data: dict):
        return data.get("market") or data.get("symbol")

    def extract_mark(data: dict):
        return to_decimal(data.get("mark_price") or data.get("markPrice") or data.get("mark"))

    def extract_funding(data: dict):
        return to_decimal(data.get("funding_rate") or data.get("fundingRate") or data.get("funding"))

    async def on_msg(ws_channel, message):
        nonlocal last_msg_ts
        last_msg_ts = time.time()

        channel, data = unwrap_ws_message(message)
        mkt = pick_market(data)
        if not mkt or mkt not in state:
            return

        state[mkt]["last_channel"] = channel

        # BBO update
        if channel.startswith("bbo.") or "bbo." in channel:
            state[mkt]["bid"] = to_decimal(data.get("bid"))
            state[mkt]["ask"] = to_decimal(data.get("ask"))
            state[mkt]["bbo_ts"] = time.time()
            return

        # markets_summary update (funding often lives here)
        if "markets_summary" in channel:
            mk = extract_mark(data)
            fr = extract_funding(data)
            if mk is not None:
                state[mkt]["mark"] = mk
            if fr is not None:
                state[mkt]["funding"] = fr
            state[mkt]["summary_ts"] = time.time()
            return

        # funding channels (optional)
        if "funding" in (channel or "").lower():
            fr = extract_funding(data)
            if fr is not None:
                state[mkt]["funding"] = fr
                state[mkt]["summary_ts"] = time.time()

    # Connect once
    await paradex.ws_client.connect()
    print(colored("[WS] connected + authenticated", "green"))

    # Subscribe summary ALL (this is where you already saw funding show up)
    await paradex.ws_client.subscribe(
        channel=ParadexWebsocketChannel.MARKETS_SUMMARY,
        params={"market": "ALL"},
        callback=on_msg,
    )
    print(colored("[WS] subscribed: MARKETS_SUMMARY market=ALL", "magenta"))

    # Subscribe BBO for ALL discovered markets
    for sym in symbols:
        await paradex.ws_client.subscribe(
            channel=ParadexWebsocketChannel.BBO,
            params={"market": sym},
            callback=on_msg,
        )
    print(colored(f"[WS] subscribed: BBO for {len(symbols)} markets", "cyan"))

    print(colored("[WS] listening... (Ctrl+C to stop)", "white"))

    try:
        while True:
            await asyncio.sleep(PRINT_EVERY_SEC)
            now = time.time()

            if CLEAR_SCREEN:
                os.system("clear")

            age = now - last_msg_ts
            hb = f"[HEARTBEAT] last_msg_age={age:.2f}s | markets={len(symbols)} | print_every={PRINT_EVERY_SEC}s | sort={ORDER_MODE}"
            print(colored(hb, "white"))
            print("")
            print(colored("====== PERP SNAPSHOT ======", "cyan"))
            print(colored(f"(showing up to {MAX_ROWS} rows; stale>{STALE_SEC}s hidden)\n", "white"))

            # --- WATCHDOG: reconnect if feed goes quiet ---
            if age > 45:
                print(colored(f"[WS] quiet for {age:.1f}s → reconnecting...", "yellow"))

                # Try a clean disconnect
                try:
                    await paradex.ws_client.disconnect()
                except Exception:
                    pass

                # Small backoff
                await asyncio.sleep(2)

                # Reconnect + resubscribe
                try:
                    await paradex.ws_client.connect()

                    await paradex.ws_client.subscribe(
                        channel=ParadexWebsocketChannel.MARKETS_SUMMARY,
                        params={"market": "ALL"},
                        callback=on_msg,
                    )

                    for sym in symbols:
                        await paradex.ws_client.subscribe(
                            channel=ParadexWebsocketChannel.BBO,
                            params={"market": sym},
                            callback=on_msg,
                        )

                    last_msg_ts = time.time()
                    print(colored("[WS] reconnected + resubscribed", "green"))

                except Exception as e:
                    print(colored(f"[WS] reconnect failed: {e}", "red"))

                continue
            # --- end watchdog ---


            rows = []
            for sym, s in state.items():
                freshest = max(s["bbo_ts"], s["summary_ts"])
                if freshest <= 0:
                    continue
                if (now - freshest) > STALE_SEC:
                    continue

                # compute funding pct for sorting
                f_str, f_pct = funding_to_pct_str(s["funding"])
                abs_f = abs(f_pct) if f_pct is not None else Decimal("0")

                rows.append((freshest, abs_f, sym, s, f_str, f_pct))

            if ORDER_MODE == "random":
                random.shuffle(rows)
            else:
                # funding leaderboard (highest |funding| first)
                rows.sort(key=lambda x: x[1], reverse=True)

            shown = 0
            for freshest, abs_f, sym, s, f_str, f_pct in rows:
                if shown >= MAX_ROWS:
                    break
                shown += 1

                ch = s["last_channel"] or "unknown"
                bid = s["bid"]
                ask = s["ask"]
                mark = s["mark"]

                parts = []
                parts.append("ch=" + color_channel(display_channel(ch)))

                parts.append("mkt=" + color_market(sym))

                if bid is not None and ask is not None:
                    dp = price_dp(bid if bid is not None else ask)

                    bid_txt = colored(f"bid=${fmt_dec(bid, dp)}", "green") if bid is not None else colored("bid=$None", "white")
                    ask_txt = colored(f"ask=${fmt_dec(ask, dp)}", "red") if ask is not None else colored("ask=$None", "white")

                    parts.append(f"{bid_txt} {ask_txt}")
                    
                if mark is not None:
                    dp_m = price_dp(mark)
                    parts.append(colored(f"mark=${fmt_dec(mark, dp_m)}", "yellow"))

                if s["funding"] is not None:
                    parts.append("funding=" + color_funding(f_pct, f_str))

                print(" | ".join(parts))

            if shown == 0:
                print(colored("(no recent market data yet — waiting on WS streams...)", "yellow"))

    except KeyboardInterrupt:
        print(colored("\n[EXIT] Ctrl+C received. Disconnecting WS...", "yellow"))
    finally:
        try:
            await paradex.ws_client.disconnect()
        except Exception:
            pass
        print(colored("[EXIT] Disconnected.", "yellow"))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
