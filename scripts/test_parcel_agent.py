#!/usr/bin/env python
"""Run the three ParcelBook AI milestone queries."""

from parcelbook_ai.service import ask_parcels

QUERIES = [
    "Find older houses on big lots in Sedro-Woolley that haven’t sold recently.",
    "Find ADU candidates in Mount Vernon.",
    "Which zones allow restaurants?",
]

if __name__ == "__main__":
    for query in QUERIES:
        print("\n===", query)
        print(ask_parcels(query))
