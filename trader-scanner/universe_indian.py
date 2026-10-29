#!/usr/bin/env python3
"""Indian Stock Universe Builder for trader-scanner. Standard library only.

Builds trader/universe.txt containing the top liquid Indian market universe:
1. Core Benchmark Indices: NIFTY 50 (^NSEI), BANK NIFTY (^NSEBANK), BSE SENSEX (^BSESN)
2. NIFTY 100 & High-Beta F&O Liquid Equities (active intraday & swing momentum stocks).

Format: SYMBOL.NS|Company Name
"""

import os
import sys

# ~100 High-liquidity, high-volume NSE cash & F&O stocks across sectors
INDIAN_STOCKS = [
    # --- Top Index Giants ---
    ("RELIANCE.NS", "Reliance Industries Ltd"),
    ("HDFCBANK.NS", "HDFC Bank Ltd"),
    ("ICICIBANK.NS", "ICICI Bank Ltd"),
    ("INFY.NS", "Infosys Ltd"),
    ("TCS.NS", "Tata Consultancy Services Ltd"),
    ("ITC.NS", "ITC Ltd"),
    ("LT.NS", "Larsen & Toubro Ltd"),
    ("SBIN.NS", "State Bank of India"),
    ("BHARTIARTL.NS", "Bharti Airtel Ltd"),
    ("KOTAKBANK.NS", "Kotak Mahindra Bank Ltd"),
    ("AXISBANK.NS", "Axis Bank Ltd"),
    ("HINDUNILVR.NS", "Hindustan Unilever Ltd"),
    ("BAJFINANCE.NS", "Bajaj Finance Ltd"),
    ("MARUTI.NS", "Maruti Suzuki India Ltd"),
    ("TATAMOTORS.NS", "Tata Motors Ltd"),
    ("SUNPHARMA.NS", "Sun Pharmaceutical Industries Ltd"),
    ("TITAN.NS", "Titan Company Ltd"),
    ("NTPC.NS", "NTPC Ltd"),
    ("POWERGRID.NS", "Power Grid Corporation of India Ltd"),
    ("TATASTEEL.NS", "Tata Steel Ltd"),
    ("ASIANPAINT.NS", "Asian Paints Ltd"),
    ("M&M.NS", "Mahindra & Mahindra Ltd"),
    ("ADANIENT.NS", "Adani Enterprises Ltd"),
    ("ADANIPORTS.NS", "Adani Ports and SEZ Ltd"),
    ("COALINDIA.NS", "Coal India Ltd"),
    ("BAJAJFINSV.NS", "Bajaj Finserv Ltd"),
    ("ONGC.NS", "Oil & Natural Gas Corporation Ltd"),
    ("JSWSTEEL.NS", "JSW Steel Ltd"),
    ("WIPRO.NS", "Wipro Ltd"),
    ("HCLTECH.NS", "HCL Technologies Ltd"),

    # --- High-Beta & Top Intraday Momentum Stocks ---
    ("BEL.NS", "Bharat Electronics Ltd"),
    ("HAL.NS", "Hindustan Aeronautics Ltd"),
    ("MCX.NS", "Multi Commodity Exchange of India Ltd"),
    ("TRENT.NS", "Trent Ltd"),
    ("DIXON.NS", "Dixon Technologies India Ltd"),
    ("TATAPOWER.NS", "Tata Power Co Ltd"),
    ("BHEL.NS", "Bharat Heavy Electricals Ltd"),
    ("PFC.NS", "Power Finance Corporation Ltd"),
    ("RECLTD.NS", "REC Ltd"),
    ("VEDL.NS", "Vedanta Ltd"),
    ("CANBK.NS", "Canara Bank"),
    ("PNB.NS", "Punjab National Bank"),
    ("BANKBARODA.NS", "Bank of Baroda"),
    ("INDUSINDBK.NS", "IndusInd Bank Ltd"),
    ("CHOLAFIN.NS", "Cholamandalam Investment and Finance"),
    ("SHRIRAMFIN.NS", "Shriram Finance Ltd"),
    ("DLF.NS", "DLF Ltd"),
    ("GODREJPROP.NS", "Godrej Properties Ltd"),
    ("POLYCAB.NS", "Polycab India Ltd"),
    ("HAVELLS.NS", "Havells India Ltd"),
    ("SIEMENS.NS", "Siemens Ltd"),
    ("ABB.NS", "ABB India Ltd"),
    ("CUMMINSIND.NS", "Cummins India Ltd"),
    ("COFORGE.NS", "Coforge Ltd"),
    ("PERSISTENT.NS", "Persistent Systems Ltd"),
    ("LTIM.NS", "LTIMindtree Ltd"),
    ("TECHM.NS", "Tech Mahindra Ltd"),
    ("JINDALSTEL.NS", "Jindal Steel & Power Ltd"),
    ("NMDC.NS", "NMDC Ltd"),
    ("HINDALCO.NS", "Hindalco Industries Ltd"),
    ("NATIONALUM.NS", "National Aluminium Co Ltd"),
    ("SAIL.NS", "Steel Authority of India Ltd"),
    ("IOC.NS", "Indian Oil Corporation Ltd"),
    ("BPCL.NS", "Bharat Petroleum Corporation Ltd"),
    ("GAIL.NS", "GAIL (India) Ltd"),
    ("DRREDDY.NS", "Dr. Reddy's Laboratories Ltd"),
    ("CIPLA.NS", "Cipla Ltd"),
    ("DIVISLAB.NS", "Divi's Laboratories Ltd"),
    ("APOLLOHOSP.NS", "Apollo Hospitals Enterprise Ltd"),
    ("LUPIN.NS", "Lupin Ltd"),
    ("ZYDUSLIFE.NS", "Zydus Lifesciences Ltd"),
    ("MANAPPURAM.NS", "Manappuram Finance Ltd"),
    ("MUTHOOTFIN.NS", "Muthoot Finance Ltd"),
    ("FEDERALBNK.NS", "Federal Bank Ltd"),
    ("IDFCFIRSTB.NS", "IDFC First Bank Ltd"),
    ("AUROPHARMA.NS", "Aurobindo Pharma Ltd"),
    ("ASHOKLEY.NS", "Ashok Leyland Ltd"),
    ("TVSMOTOR.NS", "TVS Motor Company Ltd"),
    ("EICHERMOT.NS", "Eicher Motors Ltd"),
    ("HEROMOTOCO.NS", "Hero MotoCorp Ltd"),
    ("BHARATFORG.NS", "Bharat Forge Ltd"),
    ("EXIDEIND.NS", "Exide Industries Ltd"),
    ("AMBUJACEM.NS", "Ambuja Cements Ltd"),
    ("ULTRACEMCO.NS", "UltraTech Cement Ltd"),
    ("GRASIM.NS", "Grasim Industries Ltd"),
    ("PIDILITIND.NS", "Pidilite Industries Ltd"),
    ("BERGEPAINT.NS", "Berger Paints India Ltd"),
    ("DABUR.NS", "Dabur India Ltd"),
    ("BRITANNIA.NS", "Britannia Industries Ltd"),
    ("NESTLEIND.NS", "Nestle India Ltd"),
    ("COLPAL.NS", "Colgate-Palmolive (India) Ltd"),
    ("VBL.NS", "Varun Beverages Ltd"),
    ("ZOMATO.NS", "Zomato Ltd"),
    ("NAUKRI.NS", "Info Edge (India) Ltd"),
    ("IRCTC.NS", "Indian Railway Catering and Tourism Corp"),
    ("IRFC.NS", "Indian Railway Finance Corporation Ltd"),
    ("RVNL.NS", "Rail Vikas Nigam Ltd"),
    ("MAZDOCK.NS", "Mazagon Dock Shipbuilders Ltd"),
    ("COCHINSHIP.NS", "Cochin Shipyard Ltd"),
    ("BDL.NS", "Bharat Dynamics Ltd")
]

def build_universe(out_path="trader/universe.txt"):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for sym, name in INDIAN_STOCKS:
            f.write(f"{sym}|{name}\n")
    print(f"✅ Generated Indian trading universe with {len(INDIAN_STOCKS)} liquid F&O stocks at: {out_path}")

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "trader/universe.txt"
    build_universe(out)
