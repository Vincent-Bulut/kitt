import pandas as pd

def convert_to_timestamp(dte_ref):
    if dte_ref is None:
        return None
    return pd.Timestamp(dte_ref).normalize()

