#!/usr/bin/env python
from parcelbook.data.parcel_search_builder import OpenSkagitParcelSearchBuilder

if __name__ == "__main__":
    OpenSkagitParcelSearchBuilder.from_env().run_all()
