"""Export final results list (list of dicts) to CSV."""
import pandas as pd

from exporter.schema import OUTPUT_COLUMNS


def export_csv(results: list, output_path: str) -> str:
    df = pd.DataFrame(results)
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[OUTPUT_COLUMNS]
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path
